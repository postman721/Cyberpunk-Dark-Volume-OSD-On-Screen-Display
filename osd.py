#!/usr/bin/env python3
"""

Basic run with: python3 osd.py
Systemd enabled service automation with: python3 osd.py --install-service
Volume OSD with support for:
  - Dedicated media keys:
      XF86AudioRaiseVolume (KEY_VOLUMEUP, code 115)
      XF86AudioLowerVolume (KEY_VOLUMEDOWN, code 114)
      XF86AudioMute        (KEY_MUTE, code 113)
  - Alt-based shortcuts:
      Alt+Up       → Increase volume
      Alt+Down     → Decrease volume
      Alt+M        → Toggle mute

This script also includes a routine to install a systemd user service.
Run:
    python3 osd.py --install-service
to create, enable, and start a user service so that the OSD launches automatically on login.

Requirements:
  - python3-evdev, python3-pyqt5, pulseaudio-utils (or PipeWire's pactl equivalent)
  - Set KEYBOARD_DEVICE to the correct event (use `sudo evtest` to check which /dev/input/eventX carries your media keys)
  - Your user must be in the 'input' group (e.g., sudo gpasswd -a $USER input, then log out/in)
"""

import sys
import os
import threading
import subprocess
import time
from evdev import InputDevice, ecodes, categorize

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtWidgets import (
    QApplication, QStyleFactory, QWidget, QVBoxLayout,
    QLabel, QProgressBar, QDesktopWidget
)

# -------------------------- #
#    CONFIGURATION SECTION   #
# -------------------------- #

# Change this to the event device that actually carries your media keys (verified with "sudo evtest").
KEYBOARD_DEVICE = "/dev/input/event2"

# Volume step (in percent) for each volume increment/decrement
VOLUME_STEP = 5

# A global stylesheet for a cyberpunk look
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

# ------------------------ #
#   VOLUME CONTROL HELPERS #
# ------------------------ #

def get_system_volume() -> int:
    """
    Query the default PulseAudio sink for its volume (0..100).
    """
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
    """
    Set the default PulseAudio sink to the given volume percentage (0..100).
    """
    volume = max(0, min(100, volume))
    subprocess.run(
        ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{volume}%"],
        check=False
    )

def change_system_volume(delta: int) -> int:
    """
    Add 'delta' (positive or negative) to the current volume.
    Returns the new volume (0..100).
    """
    current = get_system_volume()
    new_vol = max(0, min(100, current + delta))
    set_system_volume(new_vol)
    return new_vol

def toggle_system_mute():
    """
    Toggle mute on the default PulseAudio sink.
    """
    subprocess.run(
        ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
        check=False
    )

def is_system_muted() -> bool:
    """
    Check if the default sink is muted.
    """
    try:
        output = subprocess.check_output(
            ["pactl", "get-sink-mute", "@DEFAULT_SINK@"],
            text=True
        )
        return "yes" in output.lower()
    except subprocess.CalledProcessError:
        return False

# -------------------------- #
#      VOLUME OSD CLASSES    #
# -------------------------- #

class VolumeOSD(QWidget):
    """
    A PyQt-based on-screen display widget for volume changes.
    """
    def __init__(self, step=5):
        super().__init__()
        self.step = step

        self.init_ui()

        # Timer to auto-hide the OSD after 2 seconds of inactivity
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.setInterval(2000)
        self.hide_timer.timeout.connect(self.hide)

        # Show the current volume on startup
        self.update_osd_from_system()

    def init_ui(self):
        self.setWindowTitle("Volume OSD")
        # Frameless + always on top
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
        """
        Get volume/mute state from system and refresh the OSD text and bar.
        """
        if is_system_muted():
            self.label.setText("Muted")
            self.progress_bar.setValue(0)
        else:
            vol = get_system_volume()
            self.label.setText(f"Volume: {vol}%")
            self.progress_bar.setValue(vol)

        # Show the OSD, center it, and start auto-hide
        self.show()
        self.raise_()
        self.activateWindow()
        self.center_on_screen()
        self.hide_timer.start()

    def increase_volume(self):
        new_vol = change_system_volume(self.step)
        self.label.setText(f"Volume: {new_vol}%")
        self.progress_bar.setValue(new_vol)
        print("Increase volume triggered")  # debug
        self.show_osd_again()

    def decrease_volume(self):
        new_vol = change_system_volume(-self.step)
        self.label.setText(f"Volume: {new_vol}%")
        self.progress_bar.setValue(new_vol)
        print("Decrease volume triggered")  # debug
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
        print("Toggle mute triggered")  # debug
        self.show_osd_again()

    def show_osd_again(self):
        self.show()
        self.raise_()
        self.activateWindow()
        self.center_on_screen()
        self.hide_timer.start()

class VolumeSignals(QObject):
    """
    Qt signals to communicate volume changes from the background thread to the OSD widget.
    """
    increase = pyqtSignal()
    decrease = pyqtSignal()
    mute = pyqtSignal()

# -------------------------- #
#     EVDEV READING THREAD   #
# -------------------------- #

def read_keyboard_events(signals: VolumeSignals, dev_path: str):
    """
    Reads raw keyboard events from evdev and emits signals for:
      - Alt+Up, Alt+Down, Alt+M
      - KEY_VOLUMEUP, KEY_VOLUMEDOWN, KEY_MUTE
    """
    try:
        dev = InputDevice(dev_path)
        print(f"[INFO] Listening on {dev_path} for keyboard events.")
    except Exception as e:
        print(f"[ERROR] Could not open {dev_path}: {e}")
        return

    MIN_INTERVAL = 0.1  # filter out repeated keydown events too quickly
    last_event_times = {}

    # Evdev code constants
    KEY_UP = ecodes.KEY_UP
    KEY_DOWN = ecodes.KEY_DOWN
    KEY_M = ecodes.KEY_M

    KEY_VOLUMEUP = ecodes.KEY_VOLUMEUP     # 115
    KEY_VOLUMEDOWN = ecodes.KEY_VOLUMEDOWN # 114
    KEY_MUTE = ecodes.KEY_MUTE             # 113

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
            # Skip if too soon after last event for this key
            continue
        last_event_times[key_event.scancode] = current_time

        # Debug: show which key codes are detected
        keycodes = key_event.keycode
        if isinstance(keycodes, str):
            keycodes = [keycodes]
        print(f"Detected keys: {', '.join(keycodes)} (scancode: {key_event.scancode}) state: {key_event.keystate}")

        if key_event.keystate == key_event.key_down:
            if key_event.scancode in (KEY_LEFTALT, KEY_RIGHTALT):
                alt_pressed = True

            # Alt-based shortcuts
            if alt_pressed:
                if key_event.scancode == KEY_UP:
                    signals.increase.emit()
                elif key_event.scancode == KEY_DOWN:
                    signals.decrease.emit()
                elif key_event.scancode == KEY_M:
                    signals.mute.emit()

            # Dedicated media keys
            if key_event.scancode == KEY_VOLUMEUP:
                signals.increase.emit()
            elif key_event.scancode == KEY_VOLUMEDOWN:
                signals.decrease.emit()
            elif key_event.scancode == KEY_MUTE:
                signals.mute.emit()

        elif key_event.keystate == key_event.key_up:
            if key_event.scancode in (KEY_LEFTALT, KEY_RIGHTALT):
                alt_pressed = False

# -------------------------- #
#   SYSTEMD SERVICE INSTALL  #
# -------------------------- #

def install_systemd_service():
    """
    Writes a systemd user service to ~/.config/systemd/user/volume-osd.service,
    enabling auto-start at login and auto-restart on failure.
    """
    service_dir = os.path.expanduser("~/.config/systemd/user")
    if not os.path.exists(service_dir):
        os.makedirs(service_dir)

    service_path = os.path.join(service_dir, "volume-osd.service")
    script_path = os.path.abspath(__file__)
    uid = os.getuid()

    # Adjust DISPLAY if necessary. Often ':0' is correct, but check 'echo $DISPLAY'.
    service_file_content = f"""[Unit]
Description=Volume OSD Service
After=graphical-session.target

[Service]
ExecStart={sys.executable} {script_path}
Restart=always
RestartSec=5
Environment=DISPLAY=:0
Environment=XDG_RUNTIME_DIR=/run/user/{uid}

[Install]
WantedBy=default.target
"""

    with open(service_path, "w") as f:
        f.write(service_file_content)

    print(f"Systemd service file written to {service_path}")

    # Reload systemd user daemon, enable and start the service
    subprocess.run(["systemctl", "--user", "daemon-reload"])
    subprocess.run(["systemctl", "--user", "enable", "volume-osd.service"])
    subprocess.run(["systemctl", "--user", "start", "volume-osd.service"])
    print("Systemd service installed and started.")

# -------------------------- #
#           MAIN APP         #
# -------------------------- #

def main():
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create("Fusion"))

    # Cyberpunk palette
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

    # Create the OSD widget
    osd = VolumeOSD(step=VOLUME_STEP)

    # Create signals
    signals = VolumeSignals()
    signals.increase.connect(osd.increase_volume)
    signals.decrease.connect(osd.decrease_volume)
    signals.mute.connect(osd.toggle_mute)

    # Start the evdev event reader thread
    t = threading.Thread(
        target=read_keyboard_events,
        args=(signals, KEYBOARD_DEVICE),
        daemon=True
    )
    t.start()

    # Run the Qt event loop
    sys.exit(app.exec_())

# -------------------------- #
#          ENTRY POINT       #
# -------------------------- #

if __name__ == "__main__":
    # If called with --install-service, install the user service and exit
    if "--install-service" in sys.argv:
        install_systemd_service()
        sys.exit(0)
    else:
        main()
