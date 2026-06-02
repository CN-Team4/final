"""
分析與繪圖（§8 主指標、§9 呈現）。讀 results/*.csv 產圖。
"""
from __future__ import annotations
import os
import csv
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import config as C

plt.rcParams["axes.grid"] = True
plt.rcParams["figure.dpi"] = 130


def _read(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def plot_exp1():
    rows = _read(os.path.join(C.RESULTS, "exp1_alpha.csv"))
    cl = [r for r in rows if r["label"] == "cluster"]
    if not cl:
        return
    a = [float(r["shortage_ratio"]) * 100 for r in cl]
    wo = [float(r["mean_without"]) / 60 for r in cl]
    wi = [float(r["mean_with"]) / 60 for r in cl]
    diff = [float(r["mean_diff"]) / 60 for r in cl]
    ci = [float(r["ci_diff"]) / 60 for r in cl]

    fig, ax = plt.subplots(1, 2, figsize=(12, 4.5))
    ax[0].plot(a, wo, "o-", label="without info")
    ax[0].plot(a, wi, "s-", label="with info")
    ax[0].set_xlabel("缺車比例 (%)"); ax[0].set_ylabel("平均 cost (分鐘)")
    ax[0].set_title("實驗一：平均抵達 cost vs 缺車比例"); ax[0].legend()
    ax[1].errorbar(a, diff, yerr=ci, fmt="^-", color="C2", capsize=3)
    ax[1].axvspan(10, 20, alpha=0.12, color="orange", label="假說區間 10–20%")
    f_emp = C.ALPHA_EMPIRICAL / (1 + C.ALPHA_EMPIRICAL) * 100
    ax[1].axvline(f_emp, color="red", ls="--", lw=1.5, label=f"實證缺車比例 {f_emp:.0f}%")
    ax[1].set_xlabel("缺車比例 (%)"); ax[1].set_ylabel("cost 差 Δ (分鐘)")
    ax[1].set_title("資訊邊際效益（cost 差，95% CI）"); ax[1].legend()
    for s in ax: s.set_axisbelow(True)
    fig.tight_layout()
    p = os.path.join(C.RESULTS, "exp1_alpha.png"); fig.savefig(p); plt.close(fig)
    print("  ->", p)


def plot_tau():
    path = os.path.join(C.RESULTS, "exp_tau.csv")
    if not os.path.exists(path):
        return
    rows = [r for r in _read(path) if r["label"] == "cluster"]
    taus = sorted({float(r["tau"]) for r in rows})
    fig, ax = plt.subplots(figsize=(8.5, 5))
    for t in taus:
        sub = sorted([r for r in rows if abs(float(r["tau"]) - t) < 1e-9],
                     key=lambda r: float(r["shortage_ratio"]))
        a = [float(r["shortage_ratio"]) * 100 for r in sub]
        diff = [float(r["mean_diff"]) / 60 for r in sub]
        ax.plot(a, diff, "o-", label=f"τ={t:g}")
    ax.axvspan(10, 20, alpha=0.12, color="orange", label="假說區間")
    f_emp = C.ALPHA_EMPIRICAL / (1 + C.ALPHA_EMPIRICAL) * 100
    ax.axvline(f_emp, color="red", ls="--", lw=1.2)
    ax.set_xlabel("缺車比例 (%)"); ax.set_ylabel("cost 差 Δ (分鐘)")
    ax.set_title("τ 敏感度（唯一行為假設）：不同繞路容忍下 Δ vs 缺車比例")
    ax.legend(fontsize=9)
    fig.tight_layout()
    p = os.path.join(C.RESULTS, "tau_sensitivity.png"); fig.savefig(p); plt.close(fig)
    print("  ->", p)


def plot_heatmap():
    path = os.path.join(C.RESULTS, "exp_heatmap.csv")
    if not os.path.exists(path):
        return
    rows = [r for r in _read(path) if r["label"] == "cluster"]
    if not rows:
        return
    alphas = sorted({float(r["alpha"]) for r in rows})
    scales = sorted({float(r["cap_scale"]) for r in rows})
    sr = {a: a / (1 + a) * 100 for a in alphas}
    # 以真實總容量換算每格實際台數標示
    cap_at = {(float(r["alpha"]), float(r["cap_scale"])): float(r["total_cap"]) for r in rows}
    Zdiff = np.full((len(scales), len(alphas)), np.nan)
    Zrel = np.full((len(scales), len(alphas)), np.nan)
    for r in rows:
        i = scales.index(float(r["cap_scale"])); j = alphas.index(float(r["alpha"]))
        Zdiff[i, j] = float(r["mean_diff"]) / 60
        Zrel[i, j] = float(r["rel_improve"]) * 100

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    xt = [f"{sr[a]:.0f}" for a in alphas]
    base_total = max(cap_at.get((alphas[0], s), 0) for s in scales) if scales else 0
    yt = [f"{cap_at.get((alphas[0], s), 0):.0f} 台" for s in scales]
    for ax, Z, title, lab in [(axes[0], Zdiff, "資訊省下時間 Δ (分鐘)", "Δ (分)"),
                              (axes[1], Zrel, "相對改善 (%)", "%")]:
        im = ax.imshow(Z, origin="lower", aspect="auto", cmap="viridis")
        ax.set_xticks(range(len(alphas))); ax.set_xticklabels(xt)
        ax.set_yticks(range(len(scales))); ax.set_yticklabels(yt, fontsize=8)
        ax.set_xlabel("缺車比例 (%)"); ax.set_ylabel("尖峰時段調度車數量（台）")
        ax.set_title(title)
        for i in range(len(scales)):
            for j in range(len(alphas)):
                if not np.isnan(Z[i, j]):
                    ax.text(j, i, f"{Z[i,j]:.1f}", ha="center", va="center",
                            color="w", fontsize=7)
        # 實證缺車比例與真實調度量(×1)的標記
        f_emp = C.ALPHA_EMPIRICAL / (1 + C.ALPHA_EMPIRICAL) * 100
        if alphas:
            xs = [sr[a] for a in alphas]                # 各欄對應的缺車比例%（sr 已是%）
            xpos = float(np.interp(f_emp, xs, list(range(len(xs)))))  # 插值到真實32%位置,不貼格點
            ax.axvline(xpos, color="red", ls="--", lw=1)
        if 1.0 in scales:
            ax.axhline(scales.index(1.0), color="orange", ls="--", lw=1.2)
        # 物理合理區間帶（50–200 台/窗）
        if C.CAP_BAND[0] in scales and C.CAP_BAND[1] in scales:
            lo = scales.index(C.CAP_BAND[0]); hi = scales.index(C.CAP_BAND[1])
            ax.add_patch(plt.Rectangle((-0.5, lo - 0.5), len(alphas), hi - lo + 1,
                         fill=False, edgecolor="white", lw=2.5))
        plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label=lab)
    f_emp = C.ALPHA_EMPIRICAL / (1 + C.ALPHA_EMPIRICAL) * 100
    fig.suptitle(f"資訊能省下的時間（紅線=台大實際缺車約{f_emp:.0f}%，"
                 f"橘線=實際調度量約100台，白框=合理調度量50–200台）")
    fig.tight_layout()
    p = os.path.join(C.RESULTS, "heatmap.png"); fig.savefig(p); plt.close(fig)
    print("  ->", p)


def plot_exp2():
    path = os.path.join(C.RESULTS, "exp2_dispatch.csv")
    if not os.path.exists(path):
        return
    rows = _read(path)
    rows.sort(key=lambda r: float(r["mean_with"]))
    top = rows[:15]
    names = [r["dispatch_name"][:12] for r in top]
    vals = [float(r["mean_with"]) / 60 for r in top]
    fig, ax = plt.subplots(figsize=(9, 6))
    y = np.arange(len(top))
    ax.barh(y, vals, color="C0")
    ax.set_yticks(y); ax.set_yticklabels(names, fontsize=8)
    ax.invert_yaxis()
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.15 or 0.1
    ax.set_xlim(lo - pad, hi + pad)   # 縮放凸顯站間差異（緊湊 cluster 差異小）
    for yi, v in zip(y, vals):
        ax.text(v, yi, f" {v:.2f}", va="center", fontsize=7)
    ax.set_xlabel("with-info 平均 cost (分鐘)")
    ax.set_title("附錄(實驗二)：總容量集中單點之最佳位置（cost 低到高，前15）")
    fig.tight_layout()
    p = os.path.join(C.RESULTS, "exp2_dispatch.png"); fig.savefig(p); plt.close(fig)
    print("  ->", p)


def plot_pit():
    import polars as pl
    path = C.PIT_CLUSTER_PARQUET
    if not os.path.exists(path):
        return
    df = pl.read_parquet(path).sort("hour")
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(df["hour"].to_list(), df["p_hour"].to_list(), color="C3")
    for h in C.PEAK_HOURS:
        ax.axvspan(h - 0.5, h + 0.5, alpha=0.15, color="orange")
    ax.set_xlabel("hour of day"); ax.set_ylabel("出借占比 P(t)")
    ax.set_title("cluster 出發時間分布 P^i(t)（橘=尖峰窗）")
    fig.tight_layout()
    p = os.path.join(C.RESULTS, "pit_cluster.png"); fig.savefig(p); plt.close(fig)
    print("  ->", p)


def _setup_cjk_font():
    """註冊系統 Noto CJK 字型供 matplotlib 使用（.ttc 只會收錄第一個 face）。"""
    import glob
    from matplotlib import font_manager as fm
    for fp in glob.glob("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc") \
            + glob.glob("/usr/share/fonts/**/NotoSansCJK*.ttc", recursive=True):
        try:
            fm.fontManager.addfont(fp)
        except Exception:
            pass
    have = {f.name for f in fm.fontManager.ttflist}
    for cand in ["Noto Sans CJK TC", "Noto Sans CJK JP", "Noto Sans CJK SC",
                 "WenQuanYi Zen Hei"]:
        if cand in have:
            matplotlib.rcParams["font.sans-serif"] = [cand]
            break
    matplotlib.rcParams["axes.unicode_minus"] = False


def main():
    _setup_cjk_font()
    plot_pit(); plot_exp1(); plot_tau(); plot_heatmap(); plot_exp2()
    print("分析完成。")


if __name__ == "__main__":
    main()
