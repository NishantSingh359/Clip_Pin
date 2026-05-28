# Copy Pin

Copy Pin is a small clipboard history shelf for **PySide6 / Qt**. It lets you collect clipboard items (text, links, paths, images/screenshots), pin items, and quickly paste them back.

## Features

- Detects clipboard content type (link / text / path / image)
- Displays items as chips in a floating shelf
- Pin/unpin chips
- Clear all unpin chips
- Delete chips
- Auto-hides shelf when you move away
- Use [CTRAL + SPACE] to pin/unpin shelf
- Password and OTP are protected and delete after 10 mins
- Max 100 copy limit

---

https://github.com/user-attachments/assets/1dcf69b3-304e-4a17-8b0b-03b7b739d8fe


## ClipPin Installation Guide (Windows)

### Download ClipPin

1. Open the ClipPin GitHub page
2. Go to: Releases → Latest Release
3. Download: `ClipPin-v1.0.zip`

---

### Extract The ZIP

1. Right click: `ClipPin-v1.0.zip`
2. Click: Extract All
3. Extract to any permanent location.

After extraction you should see:

``` text
ClipPin/
├── ClipPin.exe
├── _internal/
```

---

### Run ClipPin

Double click: `ClipPin.exe`

The app should now launch.

---

### Windows SmartScreen Warning

Because ClipPin is an indie/open-source app and not code-signed yet, Windows may show: `Windows protected your PC`

If this happens:

1. Click: More info

2. Then click: Run anyway

This is normal for unsigned desktop applications.

---

### Auto Start With Windows

To launch ClipPin automatically when Windows starts:

1. Press: `Win + R`

2. Type: `shell:startup`

3. Press Enter

4. Create a shortcut of: `ClipPin.exe`

5. Move the `shortcut` and copy `_internal` folder into the Startup folder

Correct setup:

``` text
C:\Apps\ClipPin
├── ClipPin.exe
├── _internal/

Startup folder:
├── ClipPin Shortcut
├── _internal/

```
---

### Recommended System

* Windows 10 or Windows 11
* 64-bit system

---

### Privacy

ClipPin stores clipboard history locally on your computer.

No cloud sync.
No telemetry.
No online tracking.

All data remains on-device.
