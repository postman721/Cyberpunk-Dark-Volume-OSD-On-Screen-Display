#!/usr/bin/env python3
import sys
import os
import threading
import subprocess
import time
from evdev import InputDevice, ecodes, categorize, list_devices
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtWidgets import (
    QApplication, QStyleFactory, QWidget, QVBoxLayout,
    QLabel, QProgressBar, QDesktopWidget
)

def find_keyboard_devices():
    devices = list_devices()
    keyboard_paths = []
    for dev_path in devices:
        dev = InputDevice(dev_path)
        if "keyboard" in dev.name.lower():
            keyboard_paths.append(dev_path)
    if keyboard_paths:
        print("[INFO] Found keyboard devices:")
        for path in keyboard_paths:
            dev = InputDevice(path)
            print(f"   {path}: {dev.name}")
        return keyboard_paths
    fallback_paths = []
    for dev_path in devices:
        dev = InputDevice(dev_path)
        caps = dev.capabilities().get(ecodes.EV_KEY, [])
        if ecodes.KEY_A in caps and ecodes.KEY_Z in caps:
            fallback_paths.append(dev_path)
    if fallback_paths:
        print("[INFO] Found devices via fallback (KEY_A..KEY_Z):")
        for path in fallback_paths:
            dev = InputDevice(path)
            print(f"   {path}: {dev.name}")
        return fallback_paths
    print("[ERROR] No suitable keyboard devices found.")
    sys.exit(1)

VOLUME_STEP = 5

CYBERPUNK_GLOBAL_STYLESHEET = """
* {
    background-color: #121212;
    color: #00ffff;
    selection-background-color: #00ffff;
    selection-color: #121212;
}
QProgressBar {
    border: 2px solid #00ffff;
    border-radius: 4px;
    background-color: #1a1a1a;
    text-align: center;
}
QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                      stop:0 #00ffff, stop:1 #005f5f);
    border-radius: 4px;
}
"""

def get_system_volume() -> int:
    try:
        output = subprocess.check_output(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
            text=True
        )
        for part in output.split():
            if part.endswith("%"):
                try:
                    vol = int(part.strip("%"))
                    return max(0, min(100, vol))
                except ValueError:
                    pass
        return 0
    except subprocess.CalledProcessError:
        return 0

def set_system_volume(volume: int):
    volume = max(0, min(100, volume))
    subprocess.run(
        ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{volume}%"],
        check=False
    )

def change_system_volume(delta: int) -> int:
    current = get_system_volume()
    new_vol = max(0, min(100, current + delta))
    set_system_volume(new_vol)
    return new_vol

def toggle_system_mute():
    subprocess.run(
        ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
        check=False
    )

def is_system_muted() -> bool:
    try:
        output = subprocess.check_output(
            ["pactl", "get-sink-mute", "@DEFAULT_SINK@"],
            text=True
        )
        return "yes" in output.lower()
    except subprocess.CalledProcessError:
        return False

class VolumeOSD(QWidget):
    def __init__(self, step=5):
        super().__init__()
        self.step = step
        self.init_ui()
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.setInterval(2000)
        self.hide_timer.timeout.connect(self.hide)
        self.update_osd_from_system()

    def init_ui(self):
        self.setWindowTitle("Volume OSD")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.resize(300, 80)
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        self.label = QLabel("Volume: ??%")
        self.label.setAlignment(Qt.AlignCenter)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setTextVisible(False)
        layout.addWidget(self.label)
        layout.addWidget(self.progress_bar)
        self.setLayout(layout)

    def center_on_screen(self):
        screen_geometry = QDesktopWidget().availableGeometry()
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) // 2
        self.move(x, y)

    def update_osd_from_system(self):
        if is_system_muted():
            self.label.setText("Muted")
            self.progress_bar.setValue(0)
        else:
            vol = get_system_volume()
            self.label.setText(f"Volume: {vol}%")
            self.progress_bar.setValue(vol)
        self.show()
        self.raise_()
        self.activateWindow()
        self.center_on_screen()
        self.hide_timer.start()

    def increase_volume(self):
        new_vol = change_system_volume(self.step)
        self.label.setText(f"Volume: {new_vol}%")
        self.progress_bar.setValue(new_vol)
        print("Increase volume triggered")
        self.show_osd_again()

    def decrease_volume(self):
        new_vol = change_system_volume(-self.step)
        self.label.setText(f"Volume: {new_vol}%")
        self.progress_bar.setValue(new_vol)
        print("Decrease volume triggered")
        self.show_osd_again()

    def toggle_mute(self):
        toggle_system_mute()
        if is_system_muted():
            self.label.setText("Muted")
            self.progress_bar.setValue(0)
        else:
            vol = get_system_volume()
            self.label.setText(f"Volume: {vol}%")
            self.progress_bar.setValue(vol)
        print("Toggle mute triggered")
        self.show_osd_again()

    def show_osd_again(self):
        self.show()
        self.raise_()
        self.activateWindow()
        self.center_on_screen()
        self.hide_timer.start()

class VolumeSignals(QObject):
    increase = pyqtSignal()
    decrease = pyqtSignal()
    mute = pyqtSignal()

def read_keyboard_events(signals: VolumeSignals, dev_path: str):
    try:
        dev = InputDevice(dev_path)
        print(f"[INFO] Listening on {dev_path} for keyboard events.")
    except Exception as e:
        print(f"[ERROR] Could not open {dev_path}: {e}")
        return
    MIN_INTERVAL = 0.1
    last_event_times = {}
    KEY_UP = ecodes.KEY_UP
    KEY_DOWN = ecodes.KEY_DOWN
    KEY_M = ecodes.KEY_M
    KEY_VOLUMEUP = ecodes.KEY_VOLUMEUP
    KEY_VOLUMEDOWN = ecodes.KEY_VOLUMEDOWN
    KEY_MUTE = ecodes.KEY_MUTE
    KEY_LEFTALT = ecodes.KEY_LEFTALT
    KEY_RIGHTALT = ecodes.KEY_RIGHTALT
    alt_pressed = False
    for event in dev.read_loop():
        if event.type != ecodes.EV_KEY:
            continue
        key_event = categorize(event)
        current_time = time.monotonic()
        last_time = last_event_times.get(key_event.scancode, 0)
        if (current_time - last_time) < MIN_INTERVAL:
            continue
        last_event_times[key_event.scancode] = current_time
        keycodes = key_event.keycode
        if isinstance(keycodes, str):
            keycodes = [keycodes]
        print(f"Detected keys: {', '.join(keycodes)} (scancode: {key_event.scancode}) state: {key_event.keystate}")
        if key_event.keystate == key_event.key_down:
            if key_event.scancode in (KEY_LEFTALT, KEY_RIGHTALT):
                alt_pressed = True
                print("Alt pressed")
            if alt_pressed:
                if key_event.scancode == KEY_UP:
                    signals.increase.emit()
                elif key_event.scancode == KEY_DOWN:
                    signals.decrease.emit()
                elif key_event.scancode == KEY_M:
                    signals.mute.emit()
            if key_event.scancode == KEY_VOLUMEUP:
                signals.increase.emit()
            elif key_event.scancode == KEY_VOLUMEDOWN:
                signals.decrease.emit()
            elif key_event.scancode == KEY_MUTE:
                signals.mute.emit()
        elif key_event.keystate == key_event.key_up:
            if key_event.scancode in (KEY_LEFTALT, KEY_RIGHTALT):
                alt_pressed = False
                print("Alt released")

def main():
    keyboard_paths = find_keyboard_devices()
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))
    cyber_palette = QPalette()
    cyber_palette.setColor(QPalette.Window, QColor("#121212"))
    cyber_palette.setColor(QPalette.AlternateBase, QColor("#1a1a1a"))
    cyber_palette.setColor(QPalette.Base, QColor("#1a1a1a"))
    cyber_palette.setColor(QPalette.WindowText, QColor("#00ffff"))
    cyber_palette.setColor(QPalette.Text, QColor("#00ffff"))
    cyber_palette.setColor(QPalette.Button, QColor("#121212"))
    cyber_palette.setColor(QPalette.ButtonText, QColor("#00ffff"))
    cyber_palette.setColor(QPalette.Highlight, QColor("#00ffff"))
    cyber_palette.setColor(QPalette.HighlightedText, QColor("#121212"))
    app.setPalette(cyber_palette)
    app.setStyleSheet(CYBERPUNK_GLOBAL_STYLESHEET)
    osd = VolumeOSD(step=VOLUME_STEP)
    signals = VolumeSignals()
    signals.increase.connect(osd.increase_volume)
    signals.decrease.connect(osd.decrease_volume)
    signals.mute.connect(osd.toggle_mute)
    for path in keyboard_paths:
        t = threading.Thread(target=read_keyboard_events, args=(signals, path), daemon=True)
        t.start()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
