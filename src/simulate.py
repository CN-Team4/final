"""
Time-step 模擬器 v3（§7 決策 + §8 主指標）。對齊 spec §3.2 與使用者定案：

- 調度站位置「固定」＝**資料實測的真實調度足跡**（empirical.py：哪些站實際被補車），
  每站每窗服務量＝實測補車速率 dispatch_cap_peak（免憑空設 K）；敏感度以整體縮放 cap_scale 表示。
- 唯一操弄變量＝資訊（使用者是否知道調度足跡）。兩組用完全相同的足跡與容量。
- **不含等待**（依使用者定案）：Δ 只代表「知道調度站位置」的純價值，不混入「資訊讓人不呆等」。

WITHOUT INFO：理性前往「最近的一個站」m。
  m 剛好屬於調度足跡且該站容量>0 → 走 i→m 騎 m→j（耗一格）；否則走 i→m 再走 m→j。
WITH INFO：知道整個足跡 → 選容忍距離 τ·dist(i,j) 內、容量>0 的最近調度站 g
  → 走 i→g 騎 g→j；否則走 i→j。

成本含還車側：任何騎到車者，到 dst 依實測尖峰滿位率 frac_full 加（騎去最近站+走回）期望成本。
"""
from __future__ import annotations
import numpy as np
import polars as pl
import config as C
import geo


def dispatch_footprint(cluster_sids, min_cap=None):
    """從 station_stats 取 cluster 內真實調度足跡：{sno: 每窗容量}。"""
    min_cap = C.DISPATCH_MIN_CAP if min_cap is None else min_cap
    st = pl.read_parquet(C.STATION_STATS_PARQUET)
    cs = set(cluster_sids)
    caps = {}
    for r in st.iter_rows(named=True):
        if r["sno"] in cs and (r.get("dispatch_cap_peak") or 0) >= min_cap:
            caps[r["sno"]] = float(r["dispatch_cap_peak"])
    return caps


class Sim:
    def __init__(self, params=None):
        self.p = dict(V_WALK=C.V_WALK, V_BIKE=C.V_BIKE, TAU=C.TAU)
        if params:
            self.p.update(params)
        sd = geo.load_stations()
        self.sdict = {r["sno"]: (r["lon"], r["lat"]) for r in sd.iter_rows(named=True)}
        self._sids = np.array(list(self.sdict.keys()))
        self._lon = np.array([self.sdict[s][0] for s in self._sids])
        self._lat = np.array([self.sdict[s][1] for s in self._sids])
        self._near = {}
        self.frac_full = {}
        try:
            st = pl.read_parquet(C.STATION_STATS_PARQUET)
            self.frac_full = {r["sno"]: (r["frac_full_peak"] or 0.0) for r in st.iter_rows(named=True)}
        except Exception:
            pass

    def dist(self, a, b):
        lo1, la1 = self.sdict[a]; lo2, la2 = self.sdict[b]
        return geo.manhattan_m(lo1, la1, lo2, la2)

    def nearest_station(self, i):
        if i in self._near:
            return self._near[i]
        lo, la = self.sdict[i]
        latm = (self._lat + la) / 2.0
        mlon = 111_320.0 * np.cos(np.radians(latm))
        d = np.abs(self._lon - lo) * mlon + np.abs(self._lat - la) * 111_320.0
        d[self._sids == i] = np.inf
        m = int(self._sids[int(np.argmin(d))])
        self._near[i] = m
        return m

    def _return_extra(self, j):
        ff = self.frac_full.get(j, 0.0)
        if ff <= 0:
            return 0.0
        nv = self.nearest_station(j); d = self.dist(j, nv)
        return ff * (d / self.p["V_BIKE"] + d / self.p["V_WALK"])

    def prepare(self, od_table, dispatch_caps):
        p = self.p
        dispatch_sids = list(dispatch_caps.keys())
        disp_idx = {g: k for k, g in enumerate(dispatch_sids)}
        n = len(od_table)
        lam = np.array([r.get("eff_lambda", r["lambda_base"]) for r in od_table])
        go_succ = np.empty(n); go_fail = np.empty(n); walk_ij = np.empty(n); tol = np.empty(n)
        m_gi = np.full(n, -1, dtype=int)
        dig = np.full((n, len(dispatch_sids)), np.inf)
        serve_cost = np.full((n, len(dispatch_sids)), np.inf)
        for k, r in enumerate(od_table):
            i, j = r["origin"], r["dst"]
            dij = self.dist(i, j); ret_j = self._return_extra(j)
            m = self.nearest_station(i); dim = self.dist(i, m); dmj = self.dist(m, j)
            walk_ij[k] = dij / p["V_WALK"]; tol[k] = p["TAU"] * dij
            go_succ[k] = dim / p["V_WALK"] + dmj / p["V_BIKE"] + ret_j
            go_fail[k] = dim / p["V_WALK"] + dmj / p["V_WALK"]
            if m in disp_idx:
                m_gi[k] = disp_idx[m]
            for g, gi in disp_idx.items():
                d_ig = self.dist(i, g); dig[k, gi] = d_ig
                serve_cost[k, gi] = d_ig / p["V_WALK"] + self.dist(g, j) / p["V_BIKE"] + ret_j
        reachable = dig <= tol[:, None]
        base_cap = np.array([dispatch_caps[g] for g in dispatch_sids])
        return dict(lam=lam, go_succ=go_succ, go_fail=go_fail, m_gi=m_gi,
                    walk_ij=walk_ij, dig=dig, serve_cost=serve_cost, reachable=reachable,
                    base_cap=base_cap, n_dispatch=len(dispatch_sids))

    def run_once(self, prep, alpha, cap_scale, seed):
        rng = np.random.default_rng(seed)
        counts = rng.poisson(alpha * prep["lam"])
        n = int(counts.sum())
        if n == 0:
            return None
        od_idx = np.repeat(np.arange(len(counts)), counts)
        arrival = rng.uniform(*C.SIM_WINDOW, size=n)
        order = np.argsort(arrival, kind="stable")
        budget0 = np.maximum(0, np.round(prep["base_cap"] * cap_scale)).astype(int)
        nd = prep["n_dispatch"]

        # WITHOUT info：去最近站，恰為調度站才借到
        c_wo = np.empty(n); b_wo = budget0.copy()
        gs, gf, mgi = prep["go_succ"], prep["go_fail"], prep["m_gi"]
        for a in order:
            r = od_idx[a]; gi = mgi[r]
            if gi >= 0 and b_wo[gi] > 0:
                b_wo[gi] -= 1; c_wo[a] = gs[r]
            else:
                c_wo[a] = gf[r]

        # WITH info：選容忍距離內、有餘量的最近調度站
        c_wi = np.empty(n); b_wi = budget0.copy()
        reach, serve, dig, walk_ij = prep["reachable"], prep["serve_cost"], prep["dig"], prep["walk_ij"]
        for a in order:
            r = od_idx[a]; best_gi, best_d = -1, np.inf
            for gi in range(nd):
                if b_wi[gi] > 0 and reach[r, gi] and dig[r, gi] < best_d:
                    best_gi, best_d = gi, dig[r, gi]
            if best_gi >= 0:
                b_wi[best_gi] -= 1; c_wi[a] = serve[r, best_gi]
            else:
                c_wi[a] = walk_ij[r]
        return dict(n=n, mean_without=float(c_wo.mean()),
                    mean_with=float(c_wi.mean()), mean_diff=float((c_wo - c_wi).mean()))

    def run_reps(self, od_table, alpha, dispatch_caps, cap_scale=1.0,
                 n_reps=None, base_seed=None, prep=None):
        n_reps = n_reps or C.N_REPS
        base_seed = base_seed if base_seed is not None else C.BASE_SEED
        if prep is None:
            prep = self.prepare(od_table, dispatch_caps)
        diffs, wos, wis, ns = [], [], [], []
        for r in range(n_reps):
            out = self.run_once(prep, alpha, cap_scale, base_seed + r)
            if out is None:
                continue
            diffs.append(out["mean_diff"]); wos.append(out["mean_without"])
            wis.append(out["mean_with"]); ns.append(out["n"])
        if not diffs:
            return None
        diffs = np.array(diffs)
        tot_cap = float(np.maximum(0, np.round(prep["base_cap"] * cap_scale)).sum())
        return dict(alpha=alpha, cap_scale=cap_scale, total_cap=tot_cap,
                    n_dispatch=prep["n_dispatch"], mean_n=float(np.mean(ns)),
                    mean_without=float(np.mean(wos)), mean_with=float(np.mean(wis)),
                    mean_diff=float(diffs.mean()),
                    ci_diff=float(C.CI_Z * diffs.std(ddof=1) / np.sqrt(len(diffs))) if len(diffs) > 1 else 0.0,
                    n_reps=len(diffs))
