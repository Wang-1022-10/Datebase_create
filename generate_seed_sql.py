#!/usr/bin/env python3
"""生成 planner/seed_simulation.sql（模拟 CAN 本车状态 + 论文离线多模态预测）"""

from __future__ import annotations

import math
from pathlib import Path

FRAMES = 30
DT = 0.5
STEPS = list(range(1, 13))  # t = 1..12

# 自车坐标系：每帧 ego 在原点，predictions 的 x,y 为相对本车 (m)


def ego_rows() -> list[tuple]:
    rows = []
    v = 10.0
    for fid in range(1, FRAMES + 1):
        # 模拟 CAN：速度小幅波动 + 加速度
        v = max(6.0, min(14.0, v + 0.15 * math.sin(fid * 0.4)))
        a = 0.3 * math.cos(fid * 0.35)
        rows.append((fid, 0.0, 0.0, round(v, 3), round(a, 3)))
    return rows


def traj_points(
    fid: int,
    x0: float,
    y0: float,
    vx: float,
    vy: float,
    ax: float = 0.0,
) -> list[tuple[float, float, float]]:
    pts = []
    for t in STEPS:
        tt = t * DT
        x = x0 + vx * tt + 0.5 * ax * tt * tt
        y = y0 + vy * tt
        pts.append((float(t), round(x, 3), round(y, 3)))
    return pts


def prediction_rows() -> list[tuple]:
    rows: list[tuple] = []
    for fid in range(1, FRAMES + 1):
        # ── 前车 A：同车道，35m 起，约 9 m/s，模态0 高概率 ──
        base_x = 32.0 + fid * 0.25
        modals_a = [
            (0, 0.72, 9.0, 0.05, -0.05),   # index, prob, vx, vy, ax
            (1, 0.28, 7.5, 0.15, -0.25),   # 减速/横向偏一点
        ]
        for idx, prob, vx, vy, ax in modals_a:
            for t, x, y in traj_points(fid, base_x, 0.15, vx, vy, ax):
                rows.append((fid, "veh_A", idx, prob, t, x, y))

        # ── 侧方 B：邻道，不应被选为跟驰目标 ──
        for t, x, y in traj_points(fid, 28.0 + fid * 0.2, 3.6, 8.5, 0.0):
            rows.append((fid, "veh_B", 0, 1.0, t, x, y))

        # ── 远车 C：同车道但更远 ──
        for t, x, y in traj_points(fid, 75.0 + fid * 0.1, -0.1, 11.0, 0.0):
            rows.append((fid, "veh_C", 0, 0.55, t, x, y))
        for t, x, y in traj_points(fid, 72.0 + fid * 0.1, 0.2, 10.0, 0.0, -0.15):
            rows.append((fid, "veh_C", 1, 0.45, t, x, y))

        # ── 切入 D：20 帧后从侧方并入（仅部分帧）──
        if fid >= 20:
            for t, x, y in traj_points(fid, 18.0 + (fid - 20) * 0.5, 2.5 - (fid - 20) * 0.3, 7.0, -0.4):
                rows.append((fid, "veh_D", 0, 0.65, t, x, y))
            for t, x, y in traj_points(fid, 16.0, 3.8, 6.0, 0.0):
                rows.append((fid, "veh_D", 1, 0.35, t, x, y))

    return rows


def main() -> None:
    out = Path(__file__).resolve().parent / "seed_simulation.sql"
    ego = ego_rows()
    pred = prediction_rows()

    lines = [
        "-- 自动生成：模拟 ego_state（CAN/定位）+ predictions（论文离线多模态轨迹）",
        "-- 坐标系：当前帧自车坐标系，ego 每帧位于 (0,0)",
        "-- 重新生成: python generate_seed_sql.py",
        "",
        "DELETE FROM predictions;",
        "DELETE FROM ego_state;",
        "",
        "INSERT INTO ego_state (frame_id, x, y, v, a) VALUES",
    ]
    lines.append(",\n".join(f"({a},{b},{c},{d},{e})" for a, b, c, d, e in ego) + ";")
    lines.append("")
    lines.append("INSERT INTO predictions "
                 "(frame_id, target_id, trajectory_index, probability, t, x, y) VALUES")
    lines.append(",\n".join(
        f"({a},'{b}',{c},{d},{e},{f},{g})" for a, b, c, d, e, f, g in pred
    ) + ";")

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out} ({len(ego)} ego rows, {len(pred)} prediction rows)")


if __name__ == "__main__":
    main()
