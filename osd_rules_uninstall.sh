#!/usr/bin/env bash
#
# uninstall_input.sh
#
# Description:
#   This script undoes the changes made by an "install" script that appended
#   a udev rule for /dev/input/event* and added the current user to the 'input' group.
#
# Steps performed here:
#   1) Remove the line containing our custom rule from /etc/udev/rules.d/99-input.rules
#      (and delete the file entirely if it becomes empty).
#   2) Reload udev rules so the changes take effect right away.
#   3) Remove the current user from the 'input' group, preventing them from reading
#      /dev/input/event* devices without sudo.  
#   4) Inform the user that a logout or reboot may still be necessary to fully refresh
#      the session’s group memberships.
#
# Usage:
#   sudo ./uninstall_input.sh
#
# Note:
#   - If the user was not actually in the 'input' group, the removal step will print
#     a harmless error message (ignored in the script).
#   - Logging out or rebooting is recommended so the removal from 'input' group
#     definitely applies to all new sessions.

RULE='KERNEL=="event*", SUBSYSTEM=="input", MODE="0660", GROUP="input"'
RULEFILE="/etc/udev/rules.d/99-input.rules"

# 1) Remove the line containing our rule from 99-input.rules (if the file exists).
if [ -f "$RULEFILE" ]; then
  sudo sed -i "\|$RULE|d" "$RULEFILE"
  
  # If the file is now empty, remove it entirely.
  if [ ! -s "$RULEFILE" ]; then
    sudo rm -f "$RULEFILE"
  fi
fi

# 2) Reload the updated udev rules so our removal takes effect immediately.
sudo udevadm control --reload-rules
sudo udevadm trigger

# 3) Remove the current user from the 'input' group (ignore error if not in group).
sudo gpasswd -d "$USER" input || echo "User $USER not in 'input' group or error."

# 4) Inform the user about final steps.
echo "Done. A logout or reboot may still be needed for the group removal to fully apply."
