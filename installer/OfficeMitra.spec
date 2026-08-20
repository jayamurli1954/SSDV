# PyInstaller spec for OfficeMitra (Windows .exe and macOS .app).
# Build:  pyinstaller installer/OfficeMitra.spec --noconfirm --clean

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

SPECDIR = Path(SPECPATH).resolve()
ROOT = SPECDIR.parent
SRC = ROOT / "src"

datas: list[tuple[str, str]] = []
binaries: list[tuple[str, str]] = []
hiddenimports: list[str] = []

for pkg in (
    "streamlit",
    "altair",
    "pandas",
    "numpy",
    "pyarrow",
    "jsonschema",
    "narwhals",
    "PIL",
    "yaml",
    "sqlalchemy",
    "pydantic",
    "pydantic_core",
    "pydantic_settings",
    "tornado",
    "watchdog",
    "click",
    "blinker",
    "toml",
    "openpyxl",
    "pptx",
    "lxml",
    "certifi",
    "charset_normalizer",
    "anyio",
    "httpx",
    "httpcore",
    "h11",
    "idna",
    "sniffio",
    "packaging",
    "tenacity",
    "protobuf",
    "cachetools",
    "gitpython",
    "git",
    "pydeck",
    "rich",
    "markdown_it",
    "mdurl",
    "pygments",
    "referencing",
    "rpds",
    "jsonschema_specifications",
):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception:
        pass

hiddenimports += collect_submodules("ssdv")
hiddenimports += [
    "ssdv.officemitra.app",
    "ssdv.officemitra.desktop",
    "streamlit.web.bootstrap",
    "streamlit.web.cli",
    "streamlit.runtime",
    "streamlit.runtime.scriptrunner",
    "tkinter",
]

for dist in ("streamlit", "altair", "pandas", "numpy", "jsonschema", "packaging"):
    try:
        datas += copy_metadata(dist)
    except Exception:
        pass

datas += [
    (str(SRC / "ssdv" / "officemitra" / "app.py"), "ssdv/officemitra"),
    (str(SRC / "ssdv" / "data"), "ssdv/data"),
    (str(ROOT / "config"), "config"),
    (str(ROOT / "assets"), "assets"),
    (str(ROOT / "examples"), "examples"),
    (str(ROOT / ".streamlit"), ".streamlit"),
]

icon_ico = ROOT / "assets" / "officemitra.ico"
icon_icns = ROOT / "assets" / "officemitra.icns"
if sys.platform == "darwin" and icon_icns.is_file():
    icon = str(icon_icns)
elif icon_ico.is_file():
    icon = str(icon_ico)
else:
    icon = None

a = Analysis(
    [str(SRC / "ssdv" / "officemitra" / "desktop.py")],
    pathex=[str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(SPECDIR / "hooks" / "pyi_rth_officemitra.py")],
    excludes=["matplotlib", "scipy", "IPython", "notebook", "pytest"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OfficeMitra",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="OfficeMitra",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="OfficeMitra.app",
        icon=icon,
        bundle_identifier="in.sanmitratech.officemitra",
        info_plist={
            "CFBundleName": "OfficeMitra",
            "CFBundleDisplayName": "OfficeMitra",
            "CFBundleShortVersionString": "0.1.0",
            "CFBundleVersion": "0.1.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
            "NSHumanReadableCopyright": "Copyright SanMitra Technologies",
        },
    )
