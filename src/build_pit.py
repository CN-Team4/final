"""
由 43.9GB 即時場站動態資料推導出發時間分布 P^i(t)（§6 Step2 的 P^i(t)）。

方法（實證）：
  動態資料是各站「可借車數 sbi」隨時間(mday=狀態變更時間)的快照。
  同一站相鄰兩次「狀態變更」之間 sbi 的下降 = 該時段被借走的車數（出借事件）。
  將出借量依 mday 的小時(hour-of-day)彙整 → 各站每小時出借量；
  正規化成占比 → P^i(t)（每小時占全日比例，sum_t P^i(t)=1）。

去重 (sno,mday,sbi) 後依 (sno,mday) 排序取差分；負向變化計為出借。
為降低調度卡車「整批上下架」雜訊，單步出借量上限設 BORROW_CAP。

輸出：
  pit_hourly.parquet     每站 × 24 小時 的出借量與占比
  pit_cluster.parquet    校園 cluster 彙總的 24 小時占比（作 cluster 代表 P(t)）
"""
from __future__ import annotations
import time
import polars as pl
import config as C

BORROW_CAP = 20   # 單一狀態變更計入的出借量上限（過濾調度整批作業雜訊）


def build_pit(cluster_sids=None):
    t0 = time.time()
    # 無表頭，欄位以位置取：column_1=sno, column_4=sbi, column_6=mday
    lf = pl.scan_csv(
        C.DYNAMICS_CSV,
        has_header=False,
        infer_schema_length=0,           # 全部當字串讀，避免型別誤判
        truncate_ragged_lines=True,
        ignore_errors=True,
    ).select(
        pl.col("column_1").cast(pl.Int64, strict=False).alias("sno"),
        pl.col("column_4").cast(pl.Int32, strict=False).alias("sbi"),
        pl.col("column_6").str.strptime(pl.Datetime, "%Y-%m-%d %H:%M:%S", strict=False).alias("mday"),
    ).filter(
        pl.col("sno").is_not_null() & pl.col("sbi").is_not_null() & pl.col("mday").is_not_null()
    )

    # 去重 (sno,mday)：同一站同一狀態變更時間只留一筆
    lf = lf.unique(subset=["sno", "mday"]).sort(["sno", "mday"])

    # 相鄰差分（同站分組）；負向 = 出借
    lf = lf.with_columns(
        (pl.col("sbi") - pl.col("sbi").shift(1)).over("sno").alias("delta"),
    )
    lf = lf.with_columns([
        pl.col("mday").dt.hour().alias("hour"),
        pl.col("mday").dt.date().alias("date"),
        pl.when(pl.col("delta") < 0)
          .then((-pl.col("delta")).clip(0, BORROW_CAP))
          .otherwise(0)
          .alias("borrow"),
    ])

    # 每站 × 小時 出借量
    hourly = (
        lf.group_by(["sno", "hour"])
          .agg(pl.col("borrow").sum().alias("borrow"))
          .collect(engine="streaming")
    )
    # 觀測天數（每站），供日均換算
    ndays = (
        lf.group_by("sno").agg(pl.col("date").n_unique().alias("n_days"))
          .collect(engine="streaming")
    )
    print(f"[pit] 彙整完成 {time.time()-t0:.0f}s; 站數={hourly['sno'].n_unique()}")

    # 補滿 0–23 小時
    full = (
        hourly["sno"].unique().to_frame()
        .join(pl.DataFrame({"hour": list(range(24))}), how="cross")
        .join(hourly, on=["sno", "hour"], how="left")
        .with_columns(pl.col("borrow").fill_null(0))
    )
    # 每站正規化成占比 P^i(t)
    full = full.with_columns(
        (pl.col("borrow") / pl.col("borrow").sum().over("sno")).fill_nan(0).alias("p_hour")
    ).sort(["sno", "hour"])
    full = full.join(ndays, on="sno", how="left")
    full.write_parquet(C.PIT_PARQUET)
    print(f"[pit] -> {C.PIT_PARQUET} ({full.height} rows)")

    # cluster 彙總分布
    if cluster_sids:
        cl = (
            full.filter(pl.col("sno").is_in(list(cluster_sids)))
                .group_by("hour").agg(pl.col("borrow").sum())
                .sort("hour")
        )
        cl = cl.with_columns((pl.col("borrow") / pl.col("borrow").sum()).alias("p_hour"))
        cl.write_parquet(C.PIT_CLUSTER_PARQUET)
        print(f"[pit] cluster 分布 -> {C.PIT_CLUSTER_PARQUET}")
        with pl.Config(tbl_rows=24):
            print(cl)
    return full


if __name__ == "__main__":
    import sys
    sids = None
    if len(sys.argv) > 1:
        sids = [int(x) for x in sys.argv[1:]]
    build_pit(cluster_sids=sids)
