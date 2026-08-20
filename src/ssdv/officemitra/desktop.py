"""Desktop launcher for the frozen OfficeMitra app (Windows and macOS)."""

from __future__ import annotations

import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

PORT = 8501
HOST = "127.0.0.1"
URL = f"http://{HOST}:{PORT}"

_log = logging.getLogger("officemitra.desktop")


def _configure_logging(log_file: Path) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stderr),
        ],
    )


def _app_script() -> Path:
    from ssdv.paths import is_frozen, resource_root

    if is_frozen():
        bundled = resource_root() / "ssdv" / "officemitra" / "app.py"
        if bundled.is_file():
            return bundled
    return Path(__file__).resolve().parent / "app.py"


def _seed_examples() -> None:
    from ssdv.paths import resource_root, user_data_dir

    src = resource_root() / "examples"
    dest = user_data_dir() / "examples"
    if src.is_dir() and not dest.exists():
        shutil.copytree(src, dest)


def _ensure_streamlit_config() -> None:
    from ssdv.paths import resource_root, user_data_dir

    dest_dir = user_data_dir() / ".streamlit"
    dest = dest_dir / "config.toml"
    if dest.exists():
        return
    src = resource_root() / ".streamlit" / "config.toml"
    dest_dir.mkdir(parents=True, exist_ok=True)
    if src.is_file():
        shutil.copy2(src, dest)
    else:
        dest.write_text(
            '[browser]\ngatherUsageStats = false\n\n[client]\ntoolbarMode = "minimal"\n',
            encoding="utf-8",
        )


def _wait_then_open(timeout: float = 90.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((HOST, PORT), timeout=1.0):
                webbrowser.open(URL)
                _log.info("Opened browser at %s", URL)
                return
        except OSError:
            time.sleep(0.35)
    _log.error("Dashboard did not become ready on %s", URL)


def _run_streamlit(app: Path, db: Path) -> None:
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"

    flag_options = {
        "global_developmentMode": False,
        "server_headless": True,
        "server_port": PORT,
        "server_address": HOST,
        "server_fileWatcherType": "none",
        "browser_gatherUsageStats": False,
        "client_toolbarMode": "minimal",
    }
    args = ["--db", str(db)]
    from streamlit.web import bootstrap

    bootstrap.run(str(app), False, args, flag_options)


def _icon_path() -> Path | None:
    from ssdv.paths import resource_root

    for name in ("officemitra.ico", "officemitra-app-icon.png", "officemitra.png"):
        candidate = resource_root() / "assets" / name
        if candidate.is_file():
            return candidate
    return None


def _run_status_window(log_file: Path) -> int:
    try:
        import tkinter as tk
        from tkinter import ttk
    except ImportError:
        _log.warning("tkinter not available; waiting until the process is closed")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return 0
        return 0

    root = tk.Tk()
    root.title("OfficeMitra")
    root.resizable(False, False)
    icon = _icon_path()
    if icon is not None and icon.suffix.lower() == ".ico":
        try:
            root.iconbitmap(str(icon))
        except tk.TclError:
            pass

    frame = ttk.Frame(root, padding=20)
    frame.grid(sticky="nsew")
    ttk.Label(frame, text="OfficeMitra is running", font=("TkDefaultFont", 14, "bold")).grid(
        row=0, column=0, columnspan=2, sticky="w"
    )
    ttk.Label(frame, text="Your books stay on this computer.").grid(
        row=1, column=0, columnspan=2, sticky="w", pady=(8, 0)
    )
    ttk.Label(frame, text=f"Dashboard: {URL}").grid(
        row=2, column=0, columnspan=2, sticky="w", pady=(4, 0)
    )
    ttk.Label(frame, text="Close this window to quit.").grid(
        row=3, column=0, columnspan=2, sticky="w", pady=(4, 12)
    )

    def open_dash() -> None:
        webbrowser.open(URL)

    ttk.Button(frame, text="Open dashboard", command=open_dash).grid(row=4, column=0, sticky="w")
    ttk.Button(frame, text="Quit", command=root.destroy).grid(
        row=4, column=1, sticky="e", padx=(12, 0)
    )
    ttk.Label(frame, text=f"Log: {log_file}", wraplength=420).grid(
        row=5, column=0, columnspan=2, sticky="w", pady=(14, 0)
    )

    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
    return 0


def _server_command() -> list[str]:
    from ssdv.paths import is_frozen

    if is_frozen():
        return [sys.executable]
    return [sys.executable, "-m", "ssdv.officemitra.desktop"]


def _spawn_server() -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["OFFICEMITRA_ROLE"] = "server"
    kwargs: dict = {"env": env}
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(_server_command(), **kwargs)


def _stop_server(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()


def main() -> int:
    from ssdv.paths import connect_db_path, user_data_dir

    data_home = user_data_dir()
    os.chdir(str(data_home))
    log_file = data_home / "logs" / "officemitra.log"
    _configure_logging(log_file)
    _seed_examples()
    _ensure_streamlit_config()

    app = _app_script()
    db = Path(os.environ.get("OFFICEMITRA_DB") or connect_db_path())
    db.parent.mkdir(parents=True, exist_ok=True)
    if not app.is_file():
        _log.error("Cannot find OfficeMitra UI script at %s", app)
        return 2

    if os.environ.get("OFFICEMITRA_ROLE") == "server":
        _log.info("Dashboard process from %s (vault %s)", app, db)
        _run_streamlit(app, db)
        return 0

    _log.info("Starting OfficeMitra (vault %s)", db)
    os.environ["OFFICEMITRA_DB"] = str(db)
    proc = _spawn_server()
    threading.Thread(target=_wait_then_open, daemon=True).start()
    try:
        return _run_status_window(log_file)
    finally:
        _stop_server(proc)


if __name__ == "__main__":
    raise SystemExit(main())
