# DockPaste

DockPaste is a small clipboard history shelf for **PySide6 / Qt**. It lets you collect clipboard items (text, links, paths, images/screenshots), pin items, and quickly paste them back.

## Features

- Detects clipboard content type (link / text / path / image)
- Displays items as chips in a floating shelf
- Pin/unpin chips
- Clear all unpin chips
- Delete chips
- Auto-hides shelf when you move away
- Use [CTRL + WIN] to pin/unpin shelf
- Max 100 copy limit

---

https://github.com/user-attachments/assets/1dcf69b3-304e-4a17-8b0b-03b7b739d8fe


## DockPaste Installation Guide (Windows)

### Install DockPaste

1. Go to the latest GitHub Release.
2. Download and run `DockPaste-Setup-1.0.0.exe`.
3. Follow the installer and launch DockPaste from the Start menu or optional desktop shortcut.

The installer places the application and its required runtime files in the per-user program folder. You do not need to move files into the Windows Startup folder yourself.

---

### Windows SmartScreen Warning

Because DockPaste is an indie/open-source app and not code-signed yet, Windows may show: `Windows protected your PC`

If this happens:

1. Click: More info

2. Then click: Run anyway

This is normal for unsigned desktop applications.

---

### Auto Start With Windows

Open the DockPaste system tray menu, choose **Settings**, and enable **Start with Windows**. This setting applies to the current Windows user and can be turned off from the same screen.

To keep DockPaste running after closing its shelf, enable **Keep running when closed** in Settings. Use **Exit** in the tray menu to fully quit the application.
---

### Build The Windows Installer

Install [Inno Setup 6](https://jrsoftware.org/isinfo.php), activate the project virtual environment, then run:

```powershell
.\build_installer.ps1
```

The script builds the PyInstaller application bundle and then creates `dist\installer\DockPaste-Setup-1.0.0.exe`. The installed app includes its `_internal` runtime folder; the installer manages these files and creates the application shortcuts.

---

### Recommended System

* Windows 10 or Windows 11
* 64-bit system

---

### Privacy

DockPaste stores clipboard history locally on your computer.

No cloud sync.
No telemetry.
No online tracking.

All data remains on-device.
