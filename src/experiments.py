"""
實驗設計（§9）與主指標輸出（§8）。v3：調度足跡＝資料實測真實位置與容量，不含等待。

實驗一：固定真實調度足跡（cap_scale=1），掃 α，比較 with/without info 的平均 cost 與 Δ。
二維熱圖：掃 α × cap_scale（缺車程度 × 調度量縮放）→ 看公開資訊在哪種場景最有效（§9 待辦）。
容量切片：固定 α=實證錨點，掃 cap_scale。
多起點：各 START_STATIONS 為中心，重算其足跡與起點，檢驗穩健性。
附錄（實驗二）：若把總容量集中於單一站，何處最佳（spec §9 最佳位置 what-if）。
Baseline：without info。輸出 CSV 到 results/。
"""
from __future__ import annotations
import csv
import os
import numpy as np
import config as C
import geo
import demand
from simulate import Sim, dispatch_footprint


def _write_csv(path, rows, fields):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})
    print(f"  -> {path} ({len(rows)} rows)")


def exp1_sweep_alpha(sim, od_table, caps, label, cap_scale=1.0):
    prep = sim.prepare(od_table, caps)
    rows = []
    for a in C.ALPHA_SWEEP:
        res = sim.run_reps(od_table, a, caps, cap_scale, prep=prep)
        if res is None:
            continue
        res["shortage_ratio"] = a / (1 + a)
        res["rel_improve"] = res["mean_diff"] / res["mean_without"] if res["mean_without"] else 0.0
        res["label"] = label
        rows.append(res)
        print(f"  [exp1 {label}] α={a:.2f} 缺車比={a/(1+a):.1%} n≈{res['mean_n']:.0f} "
              f"cap={res['total_cap']:.0f} without={res['mean_without']:.0f}s with={res['mean_with']:.0f}s "
              f"Δ={res['mean_diff']:.0f}±{res['ci_diff']:.0f}s ({res['rel_improve']:.1%})")
    return rows


def exp_heatmap(sim, od_table, caps, label="cluster"):
    """二維：α × cap_scale。"""
    prep = sim.prepare(od_table, caps)
    rows = []
    for a in C.ALPHA_SWEEP:
        for cs in C.CAP_SCALE_SWEEP:
            res = sim.run_reps(od_table, a, caps, cs, prep=prep)
            if res is None:
                continue
            res["shortage_ratio"] = a / (1 + a)
            res["rel_improve"] = res["mean_diff"] / res["mean_without"] if res["mean_without"] else 0.0
            res["label"] = label
            rows.append(res)
    print(f"  [heatmap {label}] {len(rows)} 格 (α×cap_scale)")
    return rows


def exp_tau(sim, od_table, caps, label="cluster"):
    """τ 敏感度（唯一行為假設）：對每個 τ 重掃 α。"""
    rows = []
    for tau in C.TAU_SWEEP:
        sim.p["TAU"] = tau
        prep = sim.prepare(od_table, caps)   # serve/reachable 依 τ，需重算
        for a in C.ALPHA_SWEEP:
            res = sim.run_reps(od_table, a, caps, 1.0, prep=prep)
            if res is None:
                continue
            res["tau"] = tau; res["shortage_ratio"] = a / (1 + a)
            res["rel_improve"] = res["mean_diff"] / res["mean_without"] if res["mean_without"] else 0.0
            res["label"] = label
            rows.append(res)
    sim.p["TAU"] = C.TAU
    print(f"  [tau] {len(rows)} 列 (τ×α)")
    return rows


def exp2_best_single(sim, od_table, cluster_sids, caps, alpha, label):
    """把真實總容量集中在單一站，掃所有站找最佳單點（spec §9 what-if）。"""
    total = sum(caps.values())
    name = geo.station_dict()
    rows = []
    for g in cluster_sids:
        single = {g: total}
        prep = sim.prepare(od_table, single)
        res = sim.run_reps(od_table, alpha, single, 1.0, prep=prep)
        if res is None:
            continue
        rows.append(dict(dispatch=g, dispatch_name=name[g][2], mean_with=res["mean_with"],
                         mean_without=res["mean_without"], mean_diff=res["mean_diff"],
                         ci_diff=res["ci_diff"], mean_n=res["mean_n"], label=label))
    rows.sort(key=lambda r: r["mean_with"])
    for r in rows[:5]:
        print(f"  [exp2 {label}] 單點最佳 {r['dispatch']} {r['dispatch_name']}: with={r['mean_with']:.0f}s")
    return rows


def main():
    sim = Sim()
    sd = geo.station_dict()
    cluster = geo.ntu_cluster()                       # 76 站官方 NTU cluster
    od_cluster = demand.origin_od_table(cluster)
    caps = dispatch_footprint(cluster)                # 調度點＝cluster 內資料實測足跡
    print(f"=== NTU 官方 cluster：{len(cluster)} 站；Goal={sd[C.GOAL_STATION][2]} ===")
    print(f"=== 真實調度足跡：{len(caps)} 站, 合計 {sum(caps.values()):.0f} 台/窗 ===")
    print(f"=== 實證 α 錨點 ≈ {C.ALPHA_EMPIRICAL}（缺車比例 {C.ALPHA_EMPIRICAL/(1+C.ALPHA_EMPIRICAL):.0%}）===\n")

    fields1 = ["label", "alpha", "shortage_ratio", "cap_scale", "total_cap", "mean_n",
               "mean_without", "mean_with", "mean_diff", "ci_diff", "rel_improve", "n_reps", "tau"]

    print("### 實驗一：掃 α（真實調度足跡, cap_scale=1, τ=0.5）")
    rows1 = exp1_sweep_alpha(sim, od_cluster, caps, "cluster")
    _write_csv(os.path.join(C.RESULTS, "exp1_alpha.csv"), rows1, fields1)

    print("\n### 二維熱圖：α × cap_scale（cluster）")
    rowsh = exp_heatmap(sim, od_cluster, caps, "cluster")
    _write_csv(os.path.join(C.RESULTS, "exp_heatmap.csv"), rowsh, fields1)

    print("\n### τ 敏感度（唯一行為假設）：τ × α")
    rowst = exp_tau(sim, od_cluster, caps, "cluster")
    _write_csv(os.path.join(C.RESULTS, "exp_tau.csv"), rowst, fields1)

    print("\n### 附錄（實驗二）：總容量集中單點之最佳位置（α=實證錨點）")
    rows2 = exp2_best_single(sim, od_cluster, cluster, caps, C.ALPHA_EMPIRICAL, "cluster")
    _write_csv(os.path.join(C.RESULTS, "exp2_dispatch.csv"), rows2,
               ["label", "dispatch", "dispatch_name", "mean_without", "mean_with",
                "mean_diff", "ci_diff", "mean_n"])

    print("\n=== 完成，結果於 results/ ===")


if __name__ == "__main__":
    main()
