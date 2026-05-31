"""
需求估計模型（§6）。

Step1 日需求 D_d^{ij} = D_m^{ij} / N_d
Step2 時需求 D_t^{ij} = D_d^{ij} * P^i(t)
Step3 真實需求 D_r = (1+α) D_t；模擬母體（缺車組）= α * D_t（§2 核心前提）

本模組提供：以某 origin 集合（cluster 起點）為起點的 OD 表，及尖峰窗 P^i 占比。
"""
from __future__ import annotations
import polars as pl
import config as C


def load_od():
    return pl.read_parquet(C.OD_PARQUET)


def load_pit():
    """各站每小時占比 P^i(t)。回傳 dict[sno] -> [24] list。"""
    df = pl.read_parquet(C.PIT_PARQUET)
    out = {}
    for sno, sub in df.group_by("sno"):
        sno = sno[0] if isinstance(sno, tuple) else sno
        s = sub.sort("hour")
        out[sno] = s["p_hour"].to_list()
    return out


def peak_share(pit, sno):
    """origin sno 在尖峰窗（PEAK_HOURS 整點）的 P^i 占比和。缺值回退 cluster 分布。"""
    arr = pit.get(sno)
    if arr is None or sum(arr) == 0:
        return None
    return sum(arr[h] for h in C.PEAK_HOURS)


def cluster_peak_share():
    df = pl.read_parquet(C.PIT_CLUSTER_PARQUET).sort("hour")
    p = df["p_hour"].to_list()
    return sum(p[h] for h in C.PEAK_HOURS)


def load_shortage_weight():
    """各站尖峰實測缺車率 frac_sbi0_peak（origins 空間加權用）。無檔則 None。"""
    try:
        st = pl.read_parquet(C.STATION_STATS_PARQUET)
        return {r["sno"]: (r["frac_sbi0_peak"] or 0.0) for r in st.iter_rows(named=True)}
    except Exception:
        return None


def origin_od_table(origins, od=None, pit=None, shortage_weight=True):
    """
    為每個 origin i 整理其作為起點的 OD：回傳 list of dict
      {origin, dst, D_d, peak_share, lambda_base, eff_lambda}
    lambda_base = D_d * peak_share（純需求）。
    eff_lambda = lambda_base * w[i]，其中 w[i] ∝ 該站實測尖峰缺車率，
      經需求加權正規化使 Σ eff_lambda = Σ lambda_base（缺車空間分布貼真實，總量仍由 α 控）。
    缺 station_stats 時 eff_lambda = lambda_base。
    """
    if od is None:
        od = load_od()
    if pit is None:
        pit = load_pit()
    cl_share = cluster_peak_share()
    sw = load_shortage_weight() if shortage_weight else None
    rows = []
    sub = od.filter(pl.col("on").is_in(list(origins)))
    for r in sub.iter_rows(named=True):
        i = r["on"]
        D_d = r["txn"] / C.N_WORKDAYS_202512
        ps = peak_share(pit, i)
        if ps is None:
            ps = cl_share
        rows.append({"origin": i, "dst": r["off"], "D_d": D_d,
                     "peak_share": ps, "lambda_base": D_d * ps})
    if sw:
        # 需求加權平均缺車率，用以正規化（保持總缺車量 = α·Σlambda_base）
        tot = sum(x["lambda_base"] for x in rows)
        mean_short = sum(x["lambda_base"] * sw.get(x["origin"], 0.0) for x in rows) / tot if tot else 0.0
        for x in rows:
            w = (sw.get(x["origin"], 0.0) / mean_short) if mean_short > 0 else 1.0
            x["eff_lambda"] = x["lambda_base"] * w
    else:
        for x in rows:
            x["eff_lambda"] = x["lambda_base"]
    return rows


if __name__ == "__main__":
    import config as C
    import geo
    sd = geo.station_dict()
    origins = geo.cluster_members(C.CLUSTER_CENTER, sdict=sd)
    tbl = origin_od_table(origins)
    tot = sum(r["lambda_base"] for r in tbl)
    print(f"cluster 起點數={len(origins)}, OD 列={len(tbl)}")
    print(f"尖峰窗每日總(基礎)需求 lambda_base 合計 = {tot:.1f} 趟/日")
    print("α=0.18 時缺車期望數 =", round(tot * 0.18, 1), "趟/日")
