# Building the Windows installer

SanMitra distributes **OfficeMitra-Setup.exe** — a standard Windows installer that non-technical users double-click to install.

## What the customer sees

1. Download **OfficeMitra-Setup.exe** from your website
2. Double-click → guided wizard (Next → Install)
3. Installer copies files, runs first-time setup (Python packages)
4. **Desktop shortcut** “OfficeMitra” appears with the app icon
5. Customer double-clicks the desktop icon to launch the dashboard

## Build steps (SanMitra team)

### Prerequisites

- Windows 10/11
- [Inno Setup 6](https://jrsoftware.org/isdl.php) (free)
- Python 3.11+ on the build machine (for tests only)

### Build the setup EXE

```powershell
cd D:\SSDV
.\installer\build-installer.ps1
```

Output: **`dist\OfficeMitra-Setup.exe`**

Upload this file to your landing page / customer portal.

### Test without Inno Setup

For development or ZIP distribution:

```powershell
# Double-click in Explorer:
Install-OfficeMitra.bat
```

This opens a graphical setup wizard and creates the desktop shortcut.

## Files

| File | Purpose |
| --- | --- |
| `installer/OfficeMitra.iss` | Inno Setup script |
| `installer/build-installer.ps1` | Builds `dist/OfficeMitra-Setup.exe` |
| `installer/gui-install.ps1` | Graphical installer (no Inno required) |
| `installer/OfficeMitra.Install.psm1` | Shared install logic |
| `Install-OfficeMitra.bat` | Double-click entry for GUI installer |
| `install.ps1` | Console installer (+ silent mode for Inno) |
| `Start-OfficeMitra.bat` | Launches the Streamlit dashboard |
| `assets/officemitra.ico` | App icon |

## Customer still needs Python?

Yes, for v1 the installer expects **Python 3.11+** on the PC (with “Add to PATH”). The GUI installer shows a clear message if Python is missing.

Future: bundle Python embeddable in the Inno package for a fully self-contained install.

## Support

contact@sanmitratech.in | https://www.sanmitratech.in
