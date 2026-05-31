"""
幾何與 cluster 工具（§2 Manhattan distance、§3 cluster/外溢站）。
"""
from __future__ import annotations
import math
import numpy as np
import polars as pl
import config as C

_M_PER_DEG_LAT = 111_320.0


def _m_per_deg_lon(lat_deg):
    return 111_320.0 * math.cos(math.radians(lat_deg))


def load_stations():
    df = pl.read_parquet(C.STATIONS_PARQUET)
    return df


def station_dict(df=None):
    """sno -> (lon, lat, name)"""
    if df is None:
        df = load_stations()
    return {r["sno"]: (r["lon"], r["lat"], r["name"]) for r in df.iter_rows(named=True)}


def manhattan_m(lon1, lat1, lon2, lat2):
    """Manhattan distance(公尺)。以兩點緯度均值換算經度尺度。"""
    latm = (lat1 + lat2) / 2.0
    dx = abs(lon1 - lon2) * _m_per_deg_lon(latm)
    dy = abs(lat1 - lat2) * _M_PER_DEG_LAT
    return dx + dy


def build_distance_matrix(sids, sdict):
    """回傳 (index_map, DxN numpy Manhattan 距離矩陣)。完全圖（§3）。"""
    n = len(sids)
    lon = np.array([sdict[s][0] for s in sids])
    lat = np.array([sdict[s][1] for s in sids])
    latm = (lat[:, None] + lat[None, :]) / 2.0
    mlon = 111_320.0 * np.cos(np.radians(latm))
    dx = np.abs(lon[:, None] - lon[None, :]) * mlon
    dy = np.abs(lat[:, None] - lat[None, :]) * _M_PER_DEG_LAT
    D = dx + dy
    idx = {s: i for i, s in enumerate(sids)}
    return idx, D


# 市區臺大醫院（離校園 ~3km，非校園活動圈，排除）
NTU_HOSPITAL_EXCLUDE = {500106062, 500106104, 500106105}


def ntu_cluster():
    """官方分類為主的臺大 cluster（取代任意半徑）：
       district=臺大專區（官方校園專區） ∪ 站名含「臺大/台大」（含大安區宿舍帶） ∪ 公館各出口（Goal）
       − 市區臺大醫院 3 站。回傳 sorted sno list（約 76 站）。"""
    df = pl.read_parquet(C.STATIONS_PARQUET).unique(subset=["sno"])
    sids = set()
    for r in df.iter_rows(named=True):
        s, nm, dist = r["sno"], r["name"], r["district"]
        if dist == "臺大專區" or "臺大" in nm or "台大" in nm or "公館站" in nm:
            sids.add(int(s))
    sids -= NTU_HOSPITAL_EXCLUDE
    return sorted(sids)


def cluster_members(center_sid, l_m=None, sdict=None):
    """中心站 center 之 cluster：Manhattan 距離 <= l 的站（§3.1）。"""
    if sdict is None:
        sdict = station_dict()
    if l_m is None:
        l_m = C.L_CLUSTER_M
    clon, clat, _ = sdict[center_sid]
    members = []
    for s, (lon, lat, _nm) in sdict.items():
        if manhattan_m(clon, clat, lon, lat) <= l_m:
            members.append(s)
    return sorted(members)


if __name__ == "__main__":
    sd = station_dict()
    mem = ntu_cluster()
    print(f"NTU 官方 cluster -> {len(mem)} 站；Goal={C.GOAL_STATION} ({sd[C.GOAL_STATION][2]})")
    lons = [sd[s][0] for s in mem]; lats = [sd[s][1] for s in mem]
    print(f"範圍 經度 {min(lons):.4f}~{max(lons):.4f} 緯度 {min(lats):.4f}~{max(lats):.4f}")
    for s in mem[:10]:
        print("  ", s, sd[s][2])
