"""Generate the demo client books shipped in the desktop installer.

Runs the ABC Industrial generator for each demo scenario (in parallel, ~2-3 minutes)
and writes gzip-compressed copies to assets/demo/<stem>.sqlite.gz, which the
PyInstaller spec bundles. Called by installer/build-windows.ps1 and
installer/macos/build-macos.sh.
"""

from __future__ import annotations

import gzip
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ssdv.officemitra.demo import DEMO_BOOKS

OUT = ROOT / "assets" / "demo"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        procs = []
        for book in DEMO_BOOKS:
            db = work / f"{book.stem}.sqlite"
            env = dict(os.environ, OFFICEMITRA_HOME=str(work / f"home_{book.stem}"))
            cmd = [sys.executable, "-m", "ssdv", "--db", str(db), "init", "--scenario", book.scenario]
            log = (work / f"{book.stem}.log").open("w", encoding="utf-8")
            procs.append((book, db, log, subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)))
        failed = False
        for book, db, log, proc in procs:
            code = proc.wait()
            log.close()
            if code != 0 or not db.is_file():
                failed = True
                print(f"FAILED {book.stem} (exit {code}):")
                print((work / f"{book.stem}.log").read_text(encoding="utf-8")[-2000:])
                continue
            target = OUT / f"{book.stem}.sqlite.gz"
            with db.open("rb") as src, gzip.open(target, "wb", compresslevel=9) as out:
                shutil.copyfileobj(src, out)
            print(f"{target.relative_to(ROOT)}  {target.stat().st_size / 1e6:.1f} MB  ({book.label})")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
