#!/usr/bin/env python3
"""创建 demo.db：表结构 + 模拟数据（seed_simulation.sql）"""
import sqlite3
from pathlib import Path

root = Path(__file__).resolve().parent
db = root / "demo.db"
seed = root / "seed_simulation.sql"

if not seed.exists():
    raise SystemExit("缺少 seed_simulation.sql，请先运行: python generate_seed_sql.py")

if db.exists():
    db.unlink()

conn = sqlite3.connect(db)
conn.executescript((root / "schema.sql").read_text(encoding="utf-8"))
conn.executescript(seed.read_text(encoding="utf-8"))
conn.commit()
conn.close()
print(f"OK: {db}")
print("运行规划: python longitudinal_idm.py --db demo.db")
