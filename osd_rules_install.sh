#!/usr/bin/env bash
#
# install_input.sh
#
# Description:
#   This script grants the current user the ability to read /dev/input/event*
#   devices without needing sudo. It does this by:
#     1) Appending a udev rule that sets these devices to group 'input'
#        with 0660 (rw-rw----) permissions.
#     2) Reloading udev so the rule takes effect immediately.
#     3) Adding the current user to the 'input' group so they have permission
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

# 1) Write (or append) the udev rule.
sudo sh -c 'echo "KERNEL==\"event*\", SUBSYSTEM==\"input\", MODE=\"0660\", GROUP=\"input\"" >> /etc/udev/rules.d/99-input.rules'

# 2) Reload the updated udev rules so any new or existing /dev/input/event* devices get the new permissions.
sudo udevadm control --reload-rules
sudo udevadm trigger

# 3) Add your current user ($USER) to the 'input' group so you can read /dev/input/event* without sudo.
sudo usermod -aG input "$USER"

# 4) Print a quick reminder.
echo "Done. You should log out and log back in (or reboot) to apply the new group membership fully."
echo "(Alternatively, run 'exec newgrp input' in your shell to switch groups immediately for the current session.)"
