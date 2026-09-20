#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 OSM 逻辑小路网 SQL + GeoJSON
坐标系：GCJ-02（与高德地图一致）
区域：重庆观音桥 / 红旗河沟 5×5 网格，间距约 500m
"""

import json
import math
from pathlib import Path

ROWS, COLS = 5, 5
# 与高德地图对齐：西北角观音桥步行街口，东南至紫荆路片区
BASE_LNG, BASE_LAT = 106.5310, 29.5730
DLNG, DLAT = 0.0050, 0.0050

NAMED_INT = {
    (1, 1): "观音桥步行街口",
    (1, 3): "北城天街路口",
    (1, 5): "洋河路口",
    (3, 1): "华新街路口",
    (3, 3): "红旗河沟路口",
    (3, 5): "黄泥磅路口",
    (5, 1): "李家坪路口",
    (5, 3): "郑家院子路口",
    (5, 5): "紫荆路口",
}

ROOT = Path(__file__).resolve().parent.parent
OUT_SQL = ROOT / "backend" / "src" / "main" / "resources" / "db" / "traffic_seed.sql"
OUT_GEO = ROOT / "frontend" / "assets" / "road_network.geojson"


def int_code(r, c):
    return f"INT_G{r}{c}"


def sec_h_code(r, c):
    return f"SEC_G{r}{c}_H"


def sec_v_code(r, c):
    return f"SEC_G{r}{c}_V"


def lng_lat(r, c):
    return round(BASE_LNG + (c - 1) * DLNG, 7), round(BASE_LAT - (r - 1) * DLAT, 7)


def haversine_m(lng1, lat1, lng2, lat2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return int(round(2 * r * math.asin(math.sqrt(a))))


def travel_sec(dist_m, speed_kmh):
    return max(1, int(round(dist_m / max(speed_kmh, 1) * 3.6)))


def main():
    n_counter = 1
    s_counter = 1
    nodes = []
    coord = {}

    for r in range(1, ROWS + 1):
        for c in range(1, COLS + 1):
            code = int_code(r, c)
            lng, lat = lng_lat(r, c)
            coord[code] = (lng, lat)
            if (r, c) in NAMED_INT:
                name = NAMED_INT[(r, c)]
                remark = f"主路口 G{r}C{c}"
            else:
                name = f"节点N{n_counter:03d}"
                n_counter += 1
                remark = f"网格 G{r}C{c}"
            nodes.append((code, name, lng, lat, remark))

    for r in range(1, ROWS + 1):
        for c in range(1, COLS):
            lng = round((lng_lat(r, c)[0] + lng_lat(r, c + 1)[0]) / 2, 7)
            lat = lng_lat(r, c)[1]
            code = sec_h_code(r, c)
            coord[code] = (lng, lat)
            name = f"路段S{s_counter:03d}"
            s_counter += 1
            nodes.append((code, name, lng, lat, f"东西向 G{r}C{c}-G{r}C{c+1}"))

    for r in range(1, ROWS):
        for c in range(1, COLS + 1):
            lng = lng_lat(r, c)[0]
            lat = round((lng_lat(r, c)[1] + lng_lat(r + 1, c)[1]) / 2, 7)
            code = sec_v_code(r, c)
            coord[code] = (lng, lat)
            name = f"路段S{s_counter:03d}"
            s_counter += 1
            nodes.append((code, name, lng, lat, f"南北向 G{r}C{c}-G{r+1}C{c}"))

    edges = []
    geo_features = []

    def add_edge(a, b, speed):
        lng1, lat1 = coord[a]
        lng2, lat2 = coord[b]
        d = haversine_m(lng1, lat1, lng2, lat2)
        t = travel_sec(d, speed)
        edges.append((a, b, d, t, speed))
        geo_features.append({
            "type": "Feature",
            "properties": {"from": a, "to": b, "distance_m": d, "speed_kmh": speed},
            "geometry": {"type": "LineString", "coordinates": [[lng1, lat1], [lng2, lat2]]},
        })

    for r in range(1, ROWS + 1):
        for c in range(1, COLS):
            a, mid, b = int_code(r, c), sec_h_code(r, c), int_code(r, c + 1)
            for fr, to in ((a, mid), (mid, a), (mid, b), (b, mid)):
                add_edge(fr, to, 60)

    for r in range(1, ROWS):
        for c in range(1, COLS + 1):
            a, mid, b = int_code(r, c), sec_v_code(r, c), int_code(r + 1, c)
            for fr, to in ((a, mid), (mid, a), (mid, b), (b, mid)):
                add_edge(fr, to, 50)

    lights = []
    phases = []
    for r in range(1, ROWS + 1):
        for c in range(1, COLS + 1):
            code = int_code(r, c)
            suffix = f"G{r}{c}"
            lng, lat = lng_lat(r, c)
            for d, dlat, dlng in (("N", 0.00025, 0), ("E", 0, 0.00025), ("S", -0.00025, 0), ("W", 0, -0.00025)):
                lc = f"TL_{suffix}_{d}"
                lights.append((lc, code, d, round(lng + dlng, 7), round(lat + dlat, 7)))
                rem = 10.0 + (r * 7 + c * 3) % 25
                for pno, mov, active in ((1, "STRAIGHT", 1), (2, "LEFT", 0), (3, "RIGHT", 0)):
                    phases.append((lc, pno, mov, 45, 35, 3, rem if active else 0, active))

    node_features = []
    for code, name, lng, lat, remark in nodes:
        kind = "intersection" if code.startswith("INT_") else "segment"
        node_features.append({
            "type": "Feature",
            "properties": {"code": code, "name": name, "kind": kind, "remark": remark},
            "geometry": {"type": "Point", "coordinates": [lng, lat]},
        })

    geo = {"type": "FeatureCollection", "features": node_features + geo_features}
    OUT_GEO.parent.mkdir(parents=True, exist_ok=True)
    OUT_GEO.write_text(json.dumps(geo, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "-- 自动生成：OSM 逻辑小路网 GCJ-02 坐标（scripts/generate_traffic_network.py）",
        "SET NAMES utf8mb4;",
        "USE vehicle_road_cloud_integration;",
        "",
        f"-- 节点 {len(nodes)} | 边 {len(edges)} | 中心约 106.541, 29.563（高德观音桥片区）",
        "INSERT INTO road_nodes (node_code, node_name, lng, lat, remark) VALUES",
    ]
    lines.append(",\n".join(f"('{c}', '{n}', {lng}, {lat}, '{rm}')" for c, n, lng, lat, rm in nodes) + ";")
    lines.append("")
    lines.append("INSERT INTO road_network (from_node, to_node, distance_m, travel_time_sec, speed_limit_kmh) VALUES")
    lines.append(",\n".join(f"('{a}','{b}',{d},{t},{sp})" for a, b, d, t, sp in edges) + ";")
    lines.append("")
    lines.append("INSERT INTO traffic_lights (light_code, node_code, direction, lng, lat) VALUES")
    lines.append(",\n".join(f"('{lc}','{nc}','{d}',{lng},{lat})" for lc, nc, d, lng, lat in lights) + ";")
    lines.append("")
    lines.append("INSERT INTO traffic_phases (light_code, phase_no, movement, red_sec, green_sec, yellow_sec, current_remaining_sec, is_active) VALUES")
    lines.append(",\n".join(
        f"('{lc}',{pno},'{mov}',{red},{green},{yellow},{rem:.1f},{active})" for lc, pno, mov, red, green, yellow, rem, active in phases
    ) + ";")
    lines.append("")
    for lane_type, movement in (("LEFT", "LEFT"), ("STRAIGHT", "STRAIGHT"), ("RIGHT", "RIGHT")):
        lines.append(f"INSERT INTO traffic_lanes (light_code, lane_no, lane_type, phase_id)")
        lines.append(f"SELECT tl.light_code, {1 if movement=='LEFT' else 2 if movement=='STRAIGHT' else 3}, '{lane_type}', p.id FROM traffic_lights tl")
        lines.append(f"JOIN traffic_phases p ON p.light_code = tl.light_code AND p.movement = '{movement}';")
    lines.append("")
    lines.append("INSERT INTO signal_approach (from_node, to_node, light_code, movement)")
    lines.append("SELECT e.from_node, e.to_node,")
    lines.append("  CONCAT('TL_', SUBSTRING(e.to_node, 5), '_',")
    lines.append("    CASE")
    lines.append("      WHEN n_to.lat > n_from.lat + 0.0003 THEN 'N'")
    lines.append("      WHEN n_to.lat < n_from.lat - 0.0003 THEN 'S'")
    lines.append("      WHEN n_to.lng > n_from.lng + 0.0003 THEN 'E'")
    lines.append("      WHEN n_to.lng < n_from.lng - 0.0003 THEN 'W'")
    lines.append("      ELSE 'N'")
    lines.append("    END), 'STRAIGHT'")
    lines.append("FROM road_network e")
    lines.append("JOIN road_nodes n_from ON n_from.node_code = e.from_node")
    lines.append("JOIN road_nodes n_to ON n_to.node_code = e.to_node")
    lines.append("WHERE e.to_node LIKE 'INT_%';")

    OUT_SQL.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"SQL  -> {OUT_SQL}")
    print(f"Geo  -> {OUT_GEO}")
    print(f"nodes={len(nodes)} edges={len(edges)} center=106.541,29.563")


if __name__ == "__main__":
    main()
