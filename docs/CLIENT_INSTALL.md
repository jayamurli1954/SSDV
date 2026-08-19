# OfficeMitra — Quick install guide (Windows)

**SanMitra Technologies**

- **Website:** [https://www.sanmitratech.in](https://www.sanmitratech.in)
- **Support email:** [contact@sanmitratech.in](mailto:contact@sanmitratech.in)

This guide is for **non-technical users**. The full manual with workflows, FAQs, and troubleshooting is in **[CLIENT_MANUAL.md](CLIENT_MANUAL.md)**.

---

## Before you start

| You need | Notes |
| --- | --- |
| **Windows 10 or 11** | 64-bit recommended |
| **Internet** | Only for the first install (to download Python packages) |
| **Python 3.11 or 3.12** | Free from [python.org](https://www.python.org/downloads/) — tick **Add python.exe to PATH** during install |
| **The SSDV folder** | Unzip the package SanMitra gave you (for example `D:\SSDV`) |

**Your data stays on your PC.** OfficeMitra reads exported journals. It does not log into Tally, Zoho, Busy, or MitraBooks, and it never writes back.

![Install steps](client/images/install-steps.png)

---

## Install in 3 steps (recommended)

### Step 1 — Download and run the installer

1. Download **`OfficeMitra-Setup.exe`** from SanMitra (your purchase confirmation or download page).
2. Double-click the file.
3. Follow the wizard: **Next** → choose folder (default is fine) → **Install**.
4. Wait until setup finishes (first time may take a few minutes while components download).

If Windows SmartScreen appears, choose **More info** → **Run anyway** (the file is from SanMitra).

### Step 2 — Install Python (only if the installer asks)

1. Download **Python 3.11** or **3.12** from [https://www.python.org/downloads/](https://www.python.org/downloads/).
2. Run the installer.
3. **Important:** tick **Add python.exe to PATH**.
4. Run **OfficeMitra-Setup.exe** again, or open **Install OfficeMitra** from the Start Menu.

### Step 3 — Open OfficeMitra from your desktop

1. Double-click the **OfficeMitra** icon on your desktop.
2. A small window opens — **leave it open** while you work.
3. Your browser opens the dashboard. Use the **Setup** screen to connect Tally or upload your CSV/XML export.

---

## Alternative: ZIP package (advanced)

If SanMitra sent a ZIP folder instead of `OfficeMitra-Setup.exe`:

1. Unzip to a simple path, for example `D:\OfficeMitra`.
2. Double-click **`Install-OfficeMitra.bat`**.
3. Click **Install** in the setup window.
4. Use the **OfficeMitra** desktop shortcut to launch.

---

## Install in 5 steps (legacy ZIP + PowerShell)

### Step 1 — Unzip the package

1. Copy the SSDV folder to a simple path, for example `D:\SSDV` or `C:\OfficeMitra`.
2. Do not put it inside `Program Files` if you can avoid it (permissions are simpler elsewhere).

### Step 2 — Install Python (if the installer asks)

1. Download **Python 3.11** or **3.12** from [https://www.python.org/downloads/](https://www.python.org/downloads/).
2. Run the installer.
3. **Important:** tick **Add python.exe to PATH**.
4. Click **Install Now**.

### Step 3 — Run the guided installer

1. Open the SSDV folder in File Explorer.
2. **Right-click** `install.ps1` → **Run with PowerShell**.
3. If Windows asks about scripts, choose **Run once** or allow scripts for this folder.
4. Wait until you see **Installation complete!**

**Alternative (if right-click does not work):**

1. Press **Windows key**, type **PowerShell**, open **Windows PowerShell**.
2. Type: `cd D:\SSDV` (change the path if yours is different).
3. Type: `Set-ExecutionPolicy -Scope Process Bypass`
4. Type: `.\install.ps1`

### Step 4 — Start OfficeMitra

1. Double-click the **OfficeMitra** icon on your **desktop** (created by the installer).
2. A small window opens — **leave it open**.
3. Your browser should open **http://localhost:8501**.

If the browser does not open, open Edge or Chrome manually and go to: **http://localhost:8501**

### Step 5 — Load your company (Setup wizard)

1. On first launch, the **Setup** screen appears automatically.
2. Choose your data source (Tally live, Tally XML, CSV from Zoho/Busy/Excel).
3. Connect or upload your export file.
4. If books already exist, confirm **Yes, overwrite and continue** only when reloading fresh data.
5. After validation succeeds, choose **CEO pack**, **CFO pack**, or **Board pack** in the sidebar.

Set **As of** to the **last date in your export** (for example 31 Mar 2025).

---

## Daily use

| Action | How |
| --- | --- |
| **Open OfficeMitra** | Double-click **OfficeMitra** on the desktop |
| **Close OfficeMitra** | Close the browser tab, then close the small OfficeMitra window |
| **Refresh books** | Sidebar → **Change data source** → upload again (confirm overwrite) |
| **Board PDF** | Any pack screen → **Download Board pack (PDF)** |

---

## Need help?

| | |
| --- | --- |
| **Full manual** | [CLIENT_MANUAL.md](CLIENT_MANUAL.md) |
| **Technical reference** | [USER_MANUAL.md](USER_MANUAL.md) |
| **Email** | [contact@sanmitratech.in](mailto:contact@sanmitratech.in) |
| **Website** | [https://www.sanmitratech.in](https://www.sanmitratech.in) |

When emailing support, please include:

- Your Windows version
- What you were trying to do
- A screenshot of any error message
- Whether you use Tally, Zoho, Busy, or Excel export

---

*OfficeMitra is part of the SanMitra SSDV product family. Read-only analytics from posted journals.*
