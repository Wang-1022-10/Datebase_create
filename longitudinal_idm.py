#!/usr/bin/env python3
"""
从 SQLite 读取离线多模态预测轨迹，用 IDM 计算本车纵向控制指令。
不执行任何轨迹预测，仅读库 + 跟驰模型。

依赖: Python 3 标准库 + numpy + sqlite3
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

DT_PRED = 0.5  # predictions.t 步长 (s)


@dataclass(frozen=True)
class EgoState:
    frame_id: int
    x: float
    y: float
    v: float
    a: float


@dataclass(frozen=True)
class TrajectoryPoint:
    t: float
    x: float
    y: float


@dataclass(frozen=True)
class PredictedTrajectory:
    target_id: str
    trajectory_index: int
    probability: float
    points: Tuple[TrajectoryPoint, ...]  # sorted by t


@dataclass(frozen=True)
class IDMParams:
    a_max: float = 2.0       # 最大加速度 (m/s^2)
    b: float = 2.0           # 舒适减速度 (m/s^2)
    v0: float = 15.0         # 期望速度 (m/s)
    s0: float = 2.0          # 最小间距 (m)
    T: float = 1.5           # 期望车头时距 (s)
    delta: float = 4.0       # 加速度指数
    vehicle_length: float = 4.8
    lane_half_width: float = 1.75
    control_dt: float = 0.5  # 控制周期，与预测步长一致


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def list_frame_ids(conn: sqlite3.Connection) -> List[int]:
    rows = conn.execute(
        """
        SELECT frame_id FROM ego_state
        UNION
        SELECT frame_id FROM predictions
        ORDER BY frame_id
        """
    ).fetchall()
    return sorted({int(r["frame_id"]) for r in rows})


def load_ego(conn: sqlite3.Connection, frame_id: int) -> Optional[EgoState]:
    row = conn.execute(
        "SELECT frame_id, x, y, v, a FROM ego_state WHERE frame_id = ?",
        (frame_id,),
    ).fetchone()
    if row is None:
        return None
    return EgoState(
        frame_id=int(row["frame_id"]),
        x=float(row["x"]),
        y=float(row["y"]),
        v=float(row["v"]),
        a=float(row["a"]),
    )


def load_trajectories(conn: sqlite3.Connection, frame_id: int) -> List[PredictedTrajectory]:
    rows = conn.execute(
        """
        SELECT frame_id, target_id, trajectory_index, probability, t, x, y
        FROM predictions
        WHERE frame_id = ?
        ORDER BY target_id, trajectory_index, t
        """,
        (frame_id,),
    ).fetchall()
    if not rows:
        return []

    buckets: Dict[Tuple[str, int], Dict] = {}
    for r in rows:
        key = (str(r["target_id"]), int(r["trajectory_index"]))
        if key not in buckets:
            buckets[key] = {
                "target_id": str(r["target_id"]),
                "trajectory_index": int(r["trajectory_index"]),
                "probability": float(r["probability"]),
                "points": [],
            }
        buckets[key]["points"].append(
            TrajectoryPoint(t=float(r["t"]), x=float(r["x"]), y=float(r["y"]))
        )

    trajectories: List[PredictedTrajectory] = []
    for item in buckets.values():
        pts = tuple(sorted(item["points"], key=lambda p: p.t))
        trajectories.append(
            PredictedTrajectory(
                target_id=item["target_id"],
                trajectory_index=item["trajectory_index"],
                probability=item["probability"],
                points=pts,
            )
        )
    return trajectories


def _relative_xy(point: TrajectoryPoint, ego: EgoState) -> Tuple[float, float]:
    return point.x - ego.x, point.y - ego.y


def _longitudinal_speed(p1: TrajectoryPoint, p2: TrajectoryPoint) -> float:
    dt = p2.t - p1.t
    if dt <= 1e-6:
        return 0.0
    return math.hypot(p2.x - p1.x, p2.y - p1.y) / dt


def select_best_modal_trajectory(
    trajectories: Sequence[PredictedTrajectory], target_id: str
) -> Optional[PredictedTrajectory]:
    cands = [t for t in trajectories if t.target_id == target_id]
    if not cands:
        return None
    return max(cands, key=lambda t: t.probability)


def select_nearest_lead_target(
    ego: EgoState,
    trajectories: Sequence[PredictedTrajectory],
    params: IDMParams,
) -> Optional[Tuple[str, PredictedTrajectory]]:
    """同一车道内、本车前方纵向距离最近的目标（按最高概率模态判断位置）。"""
    by_target: Dict[str, PredictedTrajectory] = {}
    for traj in trajectories:
        cur = by_target.get(traj.target_id)
        if cur is None or traj.probability > cur.probability:
            by_target[traj.target_id] = traj

    best: Optional[Tuple[str, PredictedTrajectory, float]] = None
    for target_id, traj in by_target.items():
        if not traj.points:
            continue
        # 用 t=1 作为最近未来状态；若无 t=1 则取最小 t
        p1 = min(traj.points, key=lambda p: p.t)
        rx, ry = _relative_xy(p1, ego)
        if rx <= 0.0:
            continue
        if abs(ry) > params.lane_half_width:
            continue
        if best is None or rx < best[2]:
            best = (target_id, traj, rx)

    if best is None:
        return None
    modal = select_best_modal_trajectory(trajectories, best[0])
    if modal is None:
        return None
    return best[0], modal


def lead_state_from_trajectory(
    ego: EgoState, traj: PredictedTrajectory, vehicle_length: float
) -> Tuple[float, float]:
    """
    返回 (净间距 s, 前车速度 v_lead)。
    间距 = 前车 t=1 相对纵向位置 - 车长；速度由 t=1 与 t=2 差分。
    """
    if len(traj.points) < 1:
        return float("inf"), 0.0

    ordered = sorted(traj.points, key=lambda p: p.t)
    p1 = ordered[0]
    rx, _ = _relative_xy(p1, ego)

    if len(ordered) >= 2:
        v_lead = _longitudinal_speed(ordered[0], ordered[1])
    else:
        v_lead = 0.0

    s = max(rx - vehicle_length, 0.1)
    return s, v_lead


def idm_acceleration(v: float, v_lead: float, s: float, p: IDMParams) -> float:
    """Intelligent Driver Model 期望加速度。"""
    v = max(v, 0.0)
    s = max(s, 0.1)
    delta_v = v - v_lead
    s_star = p.s0 + max(0.0, v * p.T) + (v * delta_v) / (2.0 * math.sqrt(max(p.a_max * p.b, 1e-6)))
    free_term = 1.0 - (v / max(p.v0, 1e-3)) ** p.delta
    interact_term = (s_star / s) ** 2
    return p.a_max * (free_term - interact_term)


def compute_control(
    ego: EgoState,
    trajectories: Sequence[PredictedTrajectory],
    params: IDMParams,
) -> Dict[str, object]:
    lead = select_nearest_lead_target(ego, trajectories, params)
    if lead is None:
        # 无前车时按期望速度自由行驶
        accel = idm_acceleration(ego.v, 0.0, float("inf"), params)
        target_speed = float(np.clip(ego.v + accel * params.control_dt, 0.0, params.v0))
        return {
            "frame_id": ego.frame_id,
            "accel": round(accel, 4),
            "target_speed": round(target_speed, 4),
            "lead_target_id": None,
            "mode": "free",
        }

    target_id, modal_traj = lead
    s, v_lead = lead_state_from_trajectory(ego, modal_traj, params.vehicle_length)
    accel = idm_acceleration(ego.v, v_lead, s, params)
    target_speed = float(np.clip(ego.v + accel * params.control_dt, 0.0, params.v0))

    return {
        "frame_id": ego.frame_id,
        "accel": round(accel, 4),
        "target_speed": round(target_speed, 4),
        "lead_target_id": target_id,
        "trajectory_index": modal_traj.trajectory_index,
        "probability": modal_traj.probability,
        "gap_m": round(s, 4),
        "lead_speed_mps": round(v_lead, 4),
        "mode": "following",
    }


def run_frame(conn: sqlite3.Connection, frame_id: int, params: IDMParams) -> Optional[Dict[str, object]]:
    ego = load_ego(conn, frame_id)
    if ego is None:
        return None
    trajs = load_trajectories(conn, frame_id)
    return compute_control(ego, trajs, params)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="IDM 纵向控制（读取 SQLite 预测轨迹）")
    parser.add_argument("--db", required=True, help="SQLite 数据库路径")
    parser.add_argument("--frame-id", type=int, default=None, help="指定帧；缺省则处理全部帧")
    parser.add_argument("--v0", type=float, default=15.0, help="IDM 期望速度 m/s")
    parser.add_argument("--lane-half-width", type=float, default=1.75, help="同车道横向阈值 m")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    params = IDMParams(v0=args.v0, lane_half_width=args.lane_half_width)

    with connect(args.db) as conn:
        frame_ids = [args.frame_id] if args.frame_id is not None else list_frame_ids(conn)
        for fid in frame_ids:
            result = run_frame(conn, fid, params)
            if result is None:
                print(json.dumps({"frame_id": fid, "error": "missing ego_state"}, ensure_ascii=False))
                continue
            # 对外输出格式：每帧一行，仅必需字段 + 可选调试字段分开？
            # 用户要求: {"frame_id", "accel", "target_speed"}
            out = {
                "frame_id": result["frame_id"],
                "accel": result["accel"],
                "target_speed": result["target_speed"],
            }
            print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
