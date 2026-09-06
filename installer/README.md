# Building OfficeMitra for Windows and Mac

Customers install **OfficeMitra like any other desktop app**. They do **not** need Python.

| Platform | File to publish | What the customer does |
| --- | --- | --- |
| **Windows 10/11** | `dist/OfficeMitra-Setup.exe` | Double-click → Next → Install → desktop shortcut |
| **macOS 12+** | `dist/OfficeMitra.dmg` | Open disk image → drag **OfficeMitra** to **Applications** |

Portable fallback (Windows): `dist/OfficeMitra-windows.zip` — unzip, read **`HOW-TO-INSTALL.txt`**, run `OfficeMitra.exe`. The zip also includes **`docs/*.pdf`** (install guide + manuals).

## What the customer sees

1. Download the installer (Windows) or disk image (Mac).
2. Install / drag to Applications.
3. Open **OfficeMitra** from the desktop (Windows) or Launchpad / Applications (Mac).
4. A small status window stays open. The dashboard opens in the browser.
5. Close the status window to quit.

Books are stored on the customer PC:

- Windows: `%LOCALAPPDATA%\OfficeMitra\data`
- Mac: `~/Library/Application Support/OfficeMitra/data`

## Build on Windows

Needs Python 3.11+ **on the build PC only** (not on the customer PC).

```powershell
cd D:\SSDV
.\installer\build-windows.ps1
```

Output:

- `dist\OfficeMitra\OfficeMitra.exe` — the app
- `dist\OfficeMitra-windows.zip` — portable zip
- `dist\OfficeMitra-Setup.exe` — if [Inno Setup 6](https://jrsoftware.org/isdl.php) is installed

Without Inno Setup you can still ship the zip. The GitHub Action installs Inno Setup for you.

## Build on Mac

Needs Python 3.11+ and Xcode command-line tools **on the build Mac only**.

```bash
chmod +x installer/macos/build-macos.sh
./installer/macos/build-macos.sh
```

Output:

- `dist/OfficeMitra.app`
- `dist/OfficeMitra.dmg`

Unsigned builds: the customer right-clicks the app → **Open** the first time (Gatekeeper). Apple notarization needs a paid Apple Developer ID (later).

## GitHub Actions

Workflow **Desktop packages** (`.github/workflows/desktop.yml`):

- Manual run: **Actions → Desktop packages → Run workflow**
- Or push a tag `v0.1.0`

Download the artifacts and put them on https://www.sanmitratech.in.

## Files

| File | Purpose |
| --- | --- |
| `installer/OfficeMitra.spec` | PyInstaller recipe (bundles Streamlit + Python) |
| `installer/build-windows.ps1` | Windows exe + zip + Setup.exe |
| `installer/macos/build-macos.sh` | Mac .app + .dmg |
| `installer/OfficeMitra.iss` | Inno Setup for the bundled exe |
| `installer/OfficeMitra-source.iss` | Optional Python-based source installer (developers) |
| `installer/HOW-TO-INSTALL.txt` | Plain-text note copied into the zip / DMG / Setup |
| `installer/SETUP-FOR-CA.txt` | Step-by-step for CAs: Setup.exe + copy `ssdv.sqlite` |
| `docs/*.pdf` | Client install + manuals packaged next to the app |

## Developer / source install (not for customers)

`Install-OfficeMitra.bat` and `install.ps1` still set up a Python venv for contributors.

## Support

contact@sanmitratech.in | https://www.sanmitratech.in
