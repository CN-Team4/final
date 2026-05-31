"""
從 43.9GB 即時動態資料實證以下事實，取代憑空參數：
  1) 缺車站 / 缺車程度：尖峰時段 sbi==0 的比例 → 真實「借不到車」機率 → 推 α
  2) 真實調度站：卡車補車事件（sbi 單步大幅躍增 >= REFILL_TH）發生在哪些站
  3) 目的地滿位機率：尖峰時段 bemp<=VACANCY 的比例（還車成本用）
輸出 data/processed/station_stats.parquet（每站尖峰統計），並印 cluster 重點表。
"""
from __future__ import annotations
import polars as pl
import config as C
import geo

REFILL_TH = 10     # 單一狀態變更 sbi 增加 >= 此值 → 視為調度補車（非自然還車）
VACANCY = 2        # 可還空位 <= 此值視為「滿位」（§7.1 還車 VACANCY=2）


def build_stats():
    peak = list(C.PEAK_HOURS)
    lf = pl.scan_csv(C.DYNAMICS_CSV, has_header=False, infer_schema_length=0,
                     truncate_ragged_lines=True, ignore_errors=True).select(
        pl.col("column_1").cast(pl.Int64, strict=False).alias("sno"),
        pl.col("column_4").cast(pl.Int32, strict=False).alias("sbi"),
        pl.col("column_13").cast(pl.Int32, strict=False).alias("bemp"),
        pl.col("column_6").str.strptime(pl.Datetime, "%Y-%m-%d %H:%M:%S", strict=False).alias("mday"),
    ).filter(pl.col("sno").is_not_null() & pl.col("sbi").is_not_null() & pl.col("mday").is_not_null())

    lf = lf.unique(subset=["sno", "mday"]).sort(["sno", "mday"])
    lf = lf.with_columns([
        (pl.col("sbi") - pl.col("sbi").shift(1)).over("sno").alias("d_sbi"),
        pl.col("mday").dt.hour().alias("hour"),
        pl.col("mday").dt.date().alias("date"),
    ])
    pk = pl.col("hour").is_in(peak)
    # 全域：資料涵蓋的尖峰「天數」（每天一個尖峰窗）→ 換算每窗調度容量
    n_peak_days = lf.filter(pk).select(pl.col("date")).unique().collect(engine="streaming").height
    stats = lf.group_by("sno").agg([
        pl.len().alias("n_obs"),
        pk.sum().alias("n_peak"),
        ((pl.col("sbi") == 0) & pk).sum().alias("short_peak"),
        ((pl.col("bemp") <= VACANCY) & pk).sum().alias("full_peak"),
        ((pl.col("d_sbi") >= REFILL_TH) & pk).sum().alias("refill_ev_peak"),
        pl.when((pl.col("d_sbi") >= REFILL_TH) & pk).then(pl.col("d_sbi")).otherwise(0).sum().alias("refill_tot_peak"),
        (pl.col("sbi") == 0).mean().alias("frac_sbi0_all"),
    ]).collect(engine="streaming")

    stats = stats.with_columns([
        (pl.col("short_peak") / pl.col("n_peak")).alias("frac_sbi0_peak"),
        (pl.col("full_peak") / pl.col("n_peak")).alias("frac_full_peak"),
        # 每個尖峰窗的實測調度容量（補車總量 / 天數）→ 真實 dispatch K，免憑空設
        (pl.col("refill_tot_peak") / max(n_peak_days, 1)).alias("dispatch_cap_peak"),
    ])
    stats.write_parquet(C.STATION_STATS_PARQUET)
    print(f"[empirical] {stats.height} 站, 尖峰涵蓋 {n_peak_days} 天 -> {C.STATION_STATS_PARQUET}")
    return stats


def report(stats):
    sd = geo.station_dict()
    cluster = set(geo.ntu_cluster())
    cl = stats.filter(pl.col("sno").is_in(list(cluster)))
    name = {s: sd[s][2] for s in cluster if s in sd}

    print("\n=== 缺車站排行（cluster，尖峰 sbi==0 比例最高）===")
    top = cl.sort("frac_sbi0_peak", descending=True).head(12)
    for r in top.iter_rows(named=True):
        print(f"  {r['sno']} {name.get(r['sno'],'?')[:18]:<18} 尖峰缺車={r['frac_sbi0_peak']:.1%} (n={r['n_peak']})")

    print("\n=== 真實調度足跡（cluster，每尖峰窗實測調度容量 台/窗）===")
    topr = cl.sort("dispatch_cap_peak", descending=True).head(15)
    for r in topr.iter_rows(named=True):
        print(f"  {r['sno']} {name.get(r['sno'],'?')[:18]:<18} 容量={r['dispatch_cap_peak']:.1f} 台/窗 (總補={r['refill_tot_peak']})")
    foot = cl.filter(pl.col("dispatch_cap_peak") >= 1.0)
    print(f"  → 容量≥1 台/窗的站共 {foot.height} 站，偵測合計 {foot['dispatch_cap_peak'].sum():.0f} 台/窗")
    print(f"     （此為偵測上限，可能含自然還車潮誤判；建模時總量錨物理中估，見 config.DISPATCH_TOTAL_BASE）")

    print("\n=== 目的地滿位機率（cluster，尖峰 bemp<=2 比例最高）===")
    topf = cl.sort("frac_full_peak", descending=True).head(8)
    for r in topf.iter_rows(named=True):
        print(f"  {r['sno']} {name.get(r['sno'],'?')[:18]:<18} 尖峰滿位={r['frac_full_peak']:.1%}")

    # cluster 需求加權的尖峰缺車比例 → 推 α
    import demand
    od = demand.origin_od_table(list(cluster))
    load = {}
    for rr in od:
        load[rr["origin"]] = load.get(rr["origin"], 0) + rr["lambda_base"]
    fmap = {r["sno"]: r["frac_sbi0_peak"] for r in cl.iter_rows(named=True)}
    num = sum(load[s] * fmap.get(s, 0.0) for s in load)
    den = sum(load.values())
    f = num / den if den else 0.0
    alpha = f / (1 - f) if f < 1 else float("inf")
    print(f"\n=== cluster 需求加權尖峰缺車比例 f = {f:.1%}  → 對應 α ≈ {alpha:.3f} ===")
    print(f"    (缺車比例 = α/(1+α);實證落點可錨定實驗一的合理 α 區間)")


if __name__ == "__main__":
    s = build_stats()
    report(s)
