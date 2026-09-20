#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""可选：调用 scripts/run-osm-signal-import.bat（推荐直接双击 import-osm-signals.bat）。"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def find_mvn() -> list[str]:
    import shutil

    for name in ("mvn.cmd", "mvn.exe", "mvn"):
        p = shutil.which(name)
        if p:
            return [p]
    return []


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--import-mysql", action="store_true")
    ap.add_argument("--pbf", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    if args.pbf or args.out:
        mvn = find_mvn()
        if not mvn:
            print("ERROR: 未找到 mvn。请安装 Maven 并加入 PATH，或使用 import-osm-signals.bat")
            sys.exit(1)
        backend = ROOT / "backend"
        cmd = mvn + [
            "-q",
            "compile",
            "exec:java",
            "-Dexec.mainClass=com.driving.tools.OsmSignalSqlGenerator",
        ]
        exec_args = []
        if args.pbf:
            exec_args.append(str(args.pbf.resolve()))
        if args.out:
            exec_args.append(str(args.out.resolve()))
        if exec_args:
            cmd.append("-Dexec.args=" + ",".join(exec_args))
        r = subprocess.run(cmd, cwd=str(backend), env=os.environ.copy())
        if r.returncode != 0:
            sys.exit(r.returncode)
        if args.import_mysql:
            _import_mysql(args.out)
        return

    flag = "" if args.import_mysql else "sql-only"
    bat = ROOT / "scripts" / "run-osm-signal-import.bat"
    r = subprocess.run(["cmd", "/c", str(bat), flag], cwd=str(ROOT))
    sys.exit(r.returncode)


def _import_mysql(out: Path | None) -> None:
    sql = out or (ROOT / "backend/src/main/resources/db/signal_osm_seed.sql")
    ps1 = ROOT / "scripts/import-sql.ps1"
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ps1),
            "-SqlFile",
            str(sql.resolve()),
        ],
        cwd=str(ROOT),
        check=True,
    )


if __name__ == "__main__":
    main()
