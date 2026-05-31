"""
建站點主檔與月 OD 矩陣（§3 站點圖、§6 Step1 輸入）。

- 站點主檔：由 4 個 OD GEOJSON 蒐集站 id / 名 / 座標 / 區（座標取各站出現的中位數）。
- OD 矩陣：weekday_202512 的 sum_of_txn_times = 月交易量 D_m^{ij}。
輸出：data/processed/stations.parquet, od_weekday_202512.parquet
"""
from __future__ import annotations
import json
import statistics
from collections import defaultdict
import polars as pl
import config as C


def _load_geojson(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)["features"]


def build_stations():
    coords = defaultdict(lambda: ([], []))   # sid -> (lons, lats)
    names, areas = {}, {}
    for path in C.OD_ALL.values():
        for feat in _load_geojson(path):
            p = feat["properties"]
            cs = feat["geometry"]["coordinates"]
            o, d = cs[0], cs[-1]
            for sid, nm, ar, c in (
                (p["on_stop_id"], p["on_stop"], p["district_origin"], o),
                (p["off_stop_id"], p["off_stop"], p["district_destination"], d),
            ):
                coords[sid][0].append(c[0])
                coords[sid][1].append(c[1])
                names[sid] = nm
                areas[sid] = ar
    rows = []
    for sid, (lons, lats) in coords.items():
        rows.append({
            "sno": int(sid),
            "name": names[sid],
            "district": areas[sid],
            "lon": statistics.median(lons),
            "lat": statistics.median(lats),
        })
    df = pl.DataFrame(rows).unique(subset=["sno"]).sort("sno")
    df.write_parquet(C.STATIONS_PARQUET)
    print(f"[stations] {df.height} 站（已去重）-> {C.STATIONS_PARQUET}")
    return df


def build_od():
    rows = []
    for feat in _load_geojson(C.OD_PRIMARY):
        p = feat["properties"]
        rows.append({
            "on": int(p["on_stop_id"]),
            "off": int(p["off_stop_id"]),
            "txn": int(p["sum_of_txn_times"]),
        })
    df = pl.DataFrame(rows)
    # 同一 OD 可能重複 → 合計
    df = df.group_by(["on", "off"]).agg(pl.col("txn").sum()).sort("txn", descending=True)
    df.write_parquet(C.OD_PARQUET)
    print(f"[od] {df.height} 組 OD，總交易 {df['txn'].sum():,} -> {C.OD_PARQUET}")
    return df


if __name__ == "__main__":
    build_stations()
    build_od()
