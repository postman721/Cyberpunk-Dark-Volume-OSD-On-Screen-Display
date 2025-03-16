# **Cyberpunk Dark Volume OSD (On-Screen Display)**  

![Image](https://github.com/user-attachments/assets/7838ca2f-6173-440f-9814-ac5c682deef7)

![Image](https://github.com/user-attachments/assets/a48cfcc3-e081-4632-80fc-292c32407daa)

Used wallpaper is this: https://www.techtimejourney.net/wp-content/gallery/2024-gallery/sky.x78351.png

A sleek **Cyberpunk-inspired** Volume OSD for Linux, using **PyQt5** and **evdev** for global keyboard capture.  
This allows volume control **without sudo** by properly setting udev rules and group permissions.

---

## **Key Combinations:**
  - **Alt + Up** → Increase system volume (default step: **5%**)
  - **Alt + Down** → Decrease system volume (**5%** step)
  - **Alt + M** → Toggle **Mute/Unmute**
  - If keycodes do not work, install evtest and change the input device to match your keyboard.

### **Features**
✔ **Global Hotkeys** – Works across all apps (via evdev).  
✔ **Real-time OSD** – Displays volume level or mute status on-screen.  
✔ **No Sudo for Volume** – Once installed, runs as a normal user.  
✔ **Cyberpunk-Themed UI** – Dark mode, neon accents.  

---

## **Installation**

Install dependencies:  
```bash
sudo apt update && sudo apt install python3 python3-pyqt5 python3-evdev pulseaudio-utils
```

- python3 – Runs the script
- python3-pyqt5 – Provides the graphical OSD
- python3-evdev – Captures global keyboard shortcuts
- pulseaudio-utils – Enables volume control via pactl

## Development & Helper Scripts

	- osd_rules_install.sh – Installs udev rules and adds user to input group.
	- osd_rules_uninstall.sh – Reverts udev rules and removes user from input group.
	- ⚠️ Always check scripts before executing.
	- Notice: For me the reboot was the thing that fixed the udev rule permissions completely.

chmod +x insert_script_name_here.sh

If you want to be certain that the script will run, use bash in front of it: bash insert_script_name_here.sh


## Permissions Setup (No-Sudo Input Access)

To allow volume keys to work without running as root, use:

```bash
sudo ./osd_rules_install.sh
```
This will:
	- Sets up udev rules so /dev/input/event* devices are accessible to the input group.
	- Adds the current user to input so they can read keyboard events.

There is also an alternative script,made to address live-build issues: normal_system_fix.sh. Try that script if the other one fails.

## The wandering keyboard issue. 

Keyboard is not a fixed entity and thus its numbering will move upon fresh install. This will do harm to osd. Here is a fix for it.

		sudo apt install evtest #Install evtest

		sudo evtest #Find your keyboard

		sudo nano /usr/share/osd.py #Open osd.py


		KEYBOARD_DEVICE = "/dev/input/event4"  #Modify the number to match the device number of keyboard.


		Exit Openbox and login again.


## Uninstall (Revert Permissions)

If you want to remove permissions and reset udev rules:

```bash
sudo ./osd_rules_uninstall.sh
```
This will:

	- Remove the custom udev rule.
	- Reload udev so devices revert to default permissions.
	- Remove the user from the input group.

### Running the Volume OSD

Once installed, launch the OSD:

```python
chmod +x osd.py 
python3 osd.py
```

Systemd enabled service automation with: 
```python python3 osd.py --install-service```

The OSD will display volume changes whenever you press Alt + Up/Down/M.
