#!/usr/bin/env python3
"""
Cyberpunk Dark Volume OSD (On-Screen Display), capturing Alt-based key combinations using evdev.

Key combinations:
  - Alt+Up:   Increase system volume by a configurable step (default 5%).
  - Alt+Down: Decrease system volume by the same step.
  - Alt+M:    Toggle mute state for the default sink.

This script uses:
sudo apt update && sudo apt install python3 python3-pyqt5 python3-evdev pulseaudio-utils


Running Requirements:
 - You must have Python 3, PyQt5, and python-evdev installed.
 - Make sure you have permission to read from /dev/input/eventX (often requires sudo or membership in the `input` group).
 - Update KEYBOARD_DEVICE to the correct path (use `evtest` to figure out which event device your keyboard is on).
"""

import os
import sys
import threading
import subprocess
from evdev import InputDevice, ecodes, categorize

# PyQt imports
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtWidgets import (
    QApplication, QStyleFactory, QWidget, QVBoxLayout, QLabel,
    QProgressBar, QDesktopWidget
)


# -------------------------- #
#    CONFIGURATION SECTION   #
# -------------------------- #

# Update this to match your keyboard device, e.g. /dev/input/event2
KEYBOARD_DEVICE = "/dev/input/event2"

# Volume step in percent when pressing Alt+Up or Alt+Down
VOLUME_STEP = 5

# A global stylesheet to create a dark, cyberpunk-style appearance in the OSD
CYBERPUNK_GLOBAL_STYLESHEET = """
* {
    background-color: #121212;  /* Dark background */
    color: #00ffff;             /* Neon cyan text */
    selection-background-color: #00ffff;
    selection-color: #121212;
}
QProgressBar {
    border: 2px solid #00ffff;  /* Neon cyan border */
    border-radius: 4px;
    background-color: #1a1a1a;  /* Slightly lighter dark background */
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
    Get the current volume percentage for the default audio sink.

    Returns:
        An integer in [0..100] representing the system volume.
    """
    try:
        # 'pactl get-sink-volume @DEFAULT_SINK@' output example:
        # "Volume: front-left: 65536 / 100% / 0.00 dB, front-right: 65536 / 100% / 0.00 dB"
        output = subprocess.check_output(
            ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
            text=True
        )
        # Parse out the percentage. We look for the first token ending with '%'.
        for part in output.split():
            if part.endswith("%"):
                vol_str = part.strip("%")
                try:
                    vol = int(vol_str)
                    # Ensure volume is clamped to [0..100]
                    return max(0, min(100, vol))
                except ValueError:
                    pass
        return 0  # fallback if not found or parsing fails
    except subprocess.CalledProcessError:
        return 0  # fallback if something goes wrong with pactl


def set_system_volume(volume: int):
    """
    Set the system volume to a given percentage.

    Args:
        volume: An integer in [0..100].
    """
    # Clamp volume to [0..100] just to be safe.
    volume = max(0, min(100, volume))
    subprocess.run(
        ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{volume}%"],
        check=False
    )


def change_system_volume(delta: int) -> int:
    """
    Adjust the system volume by a given delta (+/-).

    Args:
        delta: A positive or negative integer volume change.

    Returns:
        The new volume as an integer in [0..100].
    """
    current = get_system_volume()
    new_vol = max(0, min(100, current + delta))
    set_system_volume(new_vol)
    return new_vol


def toggle_system_mute():
    """
    Toggle the mute state of the default sink using pactl.
    """
    subprocess.run(
        ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "toggle"],
        check=False
    )


def is_system_muted() -> bool:
    """
    Check if the system (default sink) is currently muted.

    Returns:
        True if muted, False otherwise.
    """
    try:
        # 'pactl get-sink-mute @DEFAULT_SINK@' -> "Mute: yes" or "Mute: no"
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
    A PyQt-based volume On-Screen Display widget.
    
    Displays the current volume level (or 'Muted') and a progress bar,
    automatically hides after a short timeout.
    """
    def __init__(self, step=5):
        """
        Constructor for VolumeOSD.

        Args:
            step (int): Volume step in percentage for increase/decrease.
        """
        super().__init__()
        self.step = step

        # Prepare UI elements
        self.init_ui()

        # Timer to auto-hide OSD after 2 seconds of inactivity
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.setInterval(2000)  # 2 seconds
        self.hide_timer.timeout.connect(self.hide)

        # Initialize the OSD display (so it shows the current volume at startup)
        self.update_osd_from_system()

    def init_ui(self):
        """
        Initialize the OSD UI as a frameless, always-on-top window with a label and a progress bar.
        """
        self.setWindowTitle("Volume OSD")
        # Make the window frameless and stay on top of other windows
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.resize(300, 80)

        # Create a vertical layout
        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        # Create a label to display volume percentage or 'Muted'
        self.label = QLabel("Volume: ??%")
        self.label.setAlignment(Qt.AlignCenter)

        # Create a progress bar to visualize the volume percentage
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        # We hide the numeric text inside the progress bar (the label handles that)
        self.progress_bar.setTextVisible(False)

        # Add the widgets to the layout
        layout.addWidget(self.label)
        layout.addWidget(self.progress_bar)

        # Assign the layout to this widget
        self.setLayout(layout)

    def center_on_screen(self):
        """
        Center the OSD on the primary screen.
        """
        screen_geometry = QDesktopWidget().availableGeometry()
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) // 2
        self.move(x, y)

    def update_osd_from_system(self):
        """
        Fetch the real system volume/mute state and update the label and progress bar.
        Also makes the OSD visible, centers it, and restarts the hide timer.
        """
        if is_system_muted():
            self.label.setText("Muted")
            self.progress_bar.setValue(0)
        else:
            vol = get_system_volume()
            self.label.setText(f"Volume: {vol}%")
            self.progress_bar.setValue(vol)

        # Show the OSD and bring it to the front
        self.show()
        self.raise_()
        self.activateWindow()
        self.center_on_screen()
        self.hide_timer.start()

    def increase_volume(self):
        """
        Slot to handle volume increase. Increases the system volume by self.step.
        Updates the OSD label & progress bar accordingly.
        """
        new_vol = change_system_volume(self.step)
        self.label.setText(f"Volume: {new_vol}%")
        self.progress_bar.setValue(new_vol)
        self.show_osd_again()

    def decrease_volume(self):
        """
        Slot to handle volume decrease. Decreases the system volume by self.step.
        Updates the OSD label & progress bar accordingly.
        """
        new_vol = change_system_volume(-self.step)
        self.label.setText(f"Volume: {new_vol}%")
        self.progress_bar.setValue(new_vol)
        self.show_osd_again()

    def toggle_mute(self):
        """
        Slot to handle mute toggling. Toggles the system mute state and updates the OSD.
        """
        toggle_system_mute()
        if is_system_muted():
            self.label.setText("Muted")
            self.progress_bar.setValue(0)
        else:
            vol = get_system_volume()
            self.label.setText(f"Volume: {vol}%")
            self.progress_bar.setValue(vol)
        self.show_osd_again()

    def show_osd_again(self):
        """
        Helper to ensure the OSD is visible and on top, re-center, and restart the hide timer.
        Called after each volume or mute change event.
        """
        self.show()
        self.raise_()
        self.activateWindow()
        self.center_on_screen()
        self.hide_timer.start()


class VolumeSignals(QObject):
    """
    Defines custom Qt signals for volume-related events. These signals are emitted
    from the background thread reading keyboard events, and are connected to the
    respective slots in the VolumeOSD.
    
    Signals:
      - increase: Emitted to indicate volume should be increased.
      - decrease: Emitted to indicate volume should be decreased.
      - mute:     Emitted to indicate mute should be toggled.
    """
    increase = pyqtSignal()
    decrease = pyqtSignal()
    mute = pyqtSignal()


# -------------------------- #
#     EVDEV READING THREAD   #
# -------------------------- #

def read_keyboard_events(signals: VolumeSignals, dev_path: str):
    """
    Background thread function to read raw keyboard events from evdev and emit signals.

    This version only listens for Alt-based key combinations:
      - Alt+Up   => Increase volume
      - Alt+Down => Decrease volume
      - Alt+M    => Toggle mute

    Args:
        signals (VolumeSignals): The VolumeSignals object whose signals we will emit.
        dev_path (str): The path to the keyboard device (e.g. /dev/input/event2).
    """
    try:
        dev = InputDevice(dev_path)
        print(f"[INFO] Listening on {dev_path} for keyboard events.")
    except Exception as e:
        print(f"[ERROR] Could not open {dev_path}: {e}")
        return

    # Define the keys we care about
    KEY_UP = ecodes.KEY_UP
    KEY_DOWN = ecodes.KEY_DOWN
    KEY_M = ecodes.KEY_M  # Alt+M for mute toggle

    # Track whether Alt is currently pressed
    alt_pressed = False
    KEY_LEFTALT = ecodes.KEY_LEFTALT
    KEY_RIGHTALT = ecodes.KEY_RIGHTALT

    # Read events in a loop (this will block until events come in)
    for event in dev.read_loop():
        if event.type == ecodes.EV_KEY:
            key_event = categorize(event)

            # If this is a "key down" event
            if key_event.keystate == key_event.key_down:
                # Check if the user just pressed Alt
                if key_event.scancode in (KEY_LEFTALT, KEY_RIGHTALT):
                    alt_pressed = True

                # If Alt is pressed, see which key was pressed along with it
                if alt_pressed:
                    if key_event.scancode == KEY_UP:
                        signals.increase.emit()
                    elif key_event.scancode == KEY_DOWN:
                        signals.decrease.emit()
                    elif key_event.scancode == KEY_M:
                        signals.mute.emit()

            # If this is a "key up" event
            elif key_event.keystate == key_event.key_up:
                # If the user released Alt, set alt_pressed to False
                if key_event.scancode in (KEY_LEFTALT, KEY_RIGHTALT):
                    alt_pressed = False


# -------------------------- #
#           MAIN APP         #
# -------------------------- #

def main():
    """
    Main function that:
      1. Initializes the Qt Application and sets up global theme/stylesheet.
      2. Creates the VolumeOSD widget.
      3. Starts a background thread to read keyboard events with evdev.
      4. Connects evdev signals to the OSD's slots.
      5. Enters the Qt event loop.
    """
    app = QApplication(sys.argv)

    # Force Fusion style for consistency across platforms
    app.setStyle(QStyleFactory.create("Fusion"))

    # Create a custom cyberpunk-style QPalette
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

    # Apply the global stylesheet for the cyberpunk look
    app.setStyleSheet(CYBERPUNK_GLOBAL_STYLESHEET)

    # Create and display the Volume OSD (with a given step size)
    osd = VolumeOSD(step=VOLUME_STEP)

    # Create an instance of VolumeSignals
    signals = VolumeSignals()

    # Connect signals to the corresponding VolumeOSD methods (slots)
    signals.increase.connect(osd.increase_volume)
    signals.decrease.connect(osd.decrease_volume)
    signals.mute.connect(osd.toggle_mute)

    # Start the background thread to read keyboard events
    t = threading.Thread(
        target=read_keyboard_events,
        args=(signals, KEYBOARD_DEVICE),
        daemon=True
    )
    t.start()

    # Enter the Qt event loop
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
