#!/usr/bin/env bash
#
# install_input.sh
#
# Description:
#   This script grants the invoking user the ability to read /dev/input/event*
#   devices without needing sudo. It does this by:
#     1) Appending a udev rule that sets these devices to group 'input'
#        with 0660 (rw-rw----) permissions.
#     2) Reloading udev so the rule takes effect immediately.
#     3) Adding the invoking user to the 'input' group so they have permission
#        to read those devices.
#   A logout or reboot is generally needed for the new group membership to take
#   effect in newly launched sessions, although 'newgrp' can be used for an
#   immediate (shell-specific) switch.
#
# Usage:
#   sudo ./install_input.sh
#
# Why Use It:
#   - By default, /dev/input/event* devices are owned by 'root' and a specific group
#     (often 'input'), with only root or that group able to read them.
#   - If you want to run an evdev-based Python or other script as a normal user,
#     you need permission to read those device files.
#   - This script automates setting proper permissions via udev and ensures
#     your user is in the correct group, saving you from having to run your
#     script with sudo.

# Determine the real user: if run with sudo, use SUDO_USER; otherwise, use USER.
if [ -n "$SUDO_USER" ]; then
  REAL_USER="$SUDO_USER"
else
  REAL_USER="$USER"
fi

# 1) Append the udev rule to /etc/udev/rules.d/99-input.rules.
sudo sh -c 'echo "KERNEL==\"event*\", SUBSYSTEM==\"input\", MODE=\"0660\", GROUP=\"input\"" >> /etc/udev/rules.d/99-input.rules'

# 2) Reload the updated udev rules so any new or existing /dev/input/event* devices get the new permissions.
sudo udevadm control --reload-rules
sudo udevadm trigger

# 3) Add the real user to the 'input' group.
sudo usermod -aG input "$REAL_USER"

# 4) Print a quick reminder.
echo "Done. You should log out and log back in (or reboot) to apply the new group membership fully."
echo "(Alternatively, run 'exec newgrp input' in your shell to switch groups immediately for the current session.)"
