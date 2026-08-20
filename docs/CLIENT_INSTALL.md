# OfficeMitra — Install and launch (Windows and Mac)

![SanMitra Tech Solutions](client/images/sanmitra-logo.png)

**SanMitra Technologies**

- **Website:** [https://www.sanmitratech.in](https://www.sanmitratech.in)
- **Support email:** [contact@sanmitratech.in](mailto:contact@sanmitratech.in)

This guide is for **non-technical users**. You do **not** need to install Python. The full manual is in **[CLIENT_MANUAL.md](CLIENT_MANUAL.md)**.

**Your data stays on your computer.** OfficeMitra reads exported journals. It does not log into Tally, Zoho, or Busy, and it never writes back.

---

## Windows 10 or 11

![Installation Steps Checklist](client/images/install-steps.png)

### Install

1. Download **`OfficeMitra-Setup.exe`** from SanMitra (purchase email or website).
2. Double-click the file. If Windows SmartScreen appears, choose **More info** → **Run anyway**.
3. Click **Next** → **Install**.
4. Tick **Launch OfficeMitra** at the end, or use the **OfficeMitra** icon on your desktop.

### Daily use

1. Double-click **OfficeMitra** on the desktop (or Start menu).
2. A small window opens — **leave it open** while you work.
3. Your browser opens the dashboard. Use **Setup** to connect Tally or upload CSV/XML.
4. To quit: close the browser tab, then close the OfficeMitra window.

If the browser does not open, go to **http://localhost:8501**.

### Portable zip (no installer)

1. Unzip **`OfficeMitra-windows.zip`** to a simple folder (for example `C:\OfficeMitra`).
2. Open **`HOW-TO-INSTALL.txt`** in that folder for a short checklist.
3. Double-click **`OfficeMitra.exe`**.
4. Full guides are in the **`docs`** folder: **CLIENT_INSTALL.pdf**, **CLIENT_MANUAL.pdf**.

---

## Mac (macOS 12 Monterey or later)

### Install

1. Download **`OfficeMitra.dmg`**.
2. Double-click the disk image.
3. Drag **OfficeMitra** into **Applications**.
4. Eject the disk image.

### First open (unsigned build)

Apple may say the app is from an unidentified developer:

1. In **Applications**, **right-click** (or Control-click) **OfficeMitra**.
2. Choose **Open**.
3. Confirm **Open**.

You only do this once.

### Daily use

1. Open **OfficeMitra** from Applications, Launchpad, or Spotlight.
2. Leave the small status window open.
3. Safari or Chrome opens the dashboard at **http://localhost:8501**.
4. To quit: close the status window (or **OfficeMitra → Quit**).

---

## Where your books are stored

| System | Folder |
| --- | --- |
| Windows | `C:\Users\<you>\AppData\Local\OfficeMitra\data` |
| Mac | `~/Library/Application Support/OfficeMitra/data` |

The vault file is **`ssdv_connect.sqlite`** after you import your company.

---

## Need help?

| | |
| --- | --- |
| **Full manual** | [CLIENT_MANUAL.md](CLIENT_MANUAL.md) |
| **Email** | [contact@sanmitratech.in](mailto:contact@sanmitratech.in) |
| **Website** | [https://www.sanmitratech.in](https://www.sanmitratech.in) |

When emailing support, include your Windows or Mac version, what you were doing, a screenshot, and whether you use Tally, Zoho, Busy, or Excel.

---

## Developers only (source + Python)

Contributors can still use the repo: install Python 3.11+, run `install.ps1` (Windows) or `pip install -e ".[ui]"`, then `ssdv ui`. See **[installer/README.md](../installer/README.md)**.

---

*OfficeMitra is part of the SanMitra SSDV product family. Read-only analytics from posted journals.*
