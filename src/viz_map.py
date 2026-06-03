"""
地圖視覺化（§11：OpenStreetMap + Leaflet）。產出報告用互動 HTML 與靜態 PNG。

輸出（results/）：
  map_cluster.html   互動地圖：cluster 站點(依需求大小著色)、Goal、起點、最佳調度點、半徑圈、Top OD 流
  map_cluster.png    靜態 OSM 底圖版（報告插圖）
  map_exp2.html      實驗二空間熱圖：各候選調度站依 with-info 平均 cost 著色
  map_exp2.png       同上靜態版
"""
from __future__ import annotations
import csv
import os
import math
import numpy as np
import folium
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.colors as mcolors
import config as C
import geo
import demand


def _read_csv(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def _cluster_ctx():
    sd = geo.station_dict()
    cluster = geo.ntu_cluster()
    od = demand.origin_od_table(cluster)
    load = {}
    for r in od:
        load[r["origin"]] = load.get(r["origin"], 0) + r["lambda_base"]
    clon, clat, _ = sd[C.CLUSTER_CENTER]
    return sd, cluster, load, (clon, clat)


def _color_scale(values, cmap_name):
    vmin, vmax = min(values), max(values)
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    cmap = cm.get_cmap(cmap_name)
    return norm, cmap, vmin, vmax


def _hex(cmap, norm, v):
    return mcolors.to_hex(cmap(norm(v)))


# ---------------------------------------------------------------- 互動地圖
def map_cluster_interactive():
    sd, cluster, load, (clon, clat) = _cluster_ctx()
    best = None
    p2 = os.path.join(C.RESULTS, "exp2_dispatch.csv")
    if os.path.exists(p2):
        rows = sorted(_read_csv(p2), key=lambda r: float(r["mean_with"]))
        best = int(rows[0]["dispatch"])

    m = folium.Map(location=[clat, clon], zoom_start=15, tiles="OpenStreetMap",
                   control_scale=True)
    fg_st = folium.FeatureGroup(name="cluster 站點（圓點大小=借車需求，即使用者起點權重）").add_to(m)
    fg_od = folium.FeatureGroup(name="Top OD 流", show=False).add_to(m)

    lv = list(load.values())
    norm, cmap, vmin, vmax = _color_scale(lv if lv else [0, 1], "YlOrRd")
    for s in cluster:
        lon, lat, nm = sd[s]
        d = load.get(s, 0.0)
        folium.CircleMarker(
            [lat, lon], radius=4 + 9 * (d / vmax if vmax else 0),
            color=_hex(cmap, norm, d), fill=True, fill_opacity=0.8, weight=1,
            popup=folium.Popup(f"{nm}<br>id={s}<br>尖峰基礎需求={d:.1f} 趟/日", max_width=250),
            tooltip=nm,
        ).add_to(fg_st)

    # Goal（公館）
    glon, glat, gnm = sd[C.GOAL_STATION]
    folium.Marker([glat, glon], tooltip=f"Goal: {gnm}",
                  icon=folium.Icon(color="green", icon="flag")).add_to(m)
    # （不再畫 START_STATIONS 假三角；使用者起點由上方圓點的需求權重表示）
    # 真實調度足跡（資料實測，大小=每窗容量）
    from simulate import dispatch_footprint
    caps = dispatch_footprint(cluster)
    if caps:
        cmax = max(caps.values())
        fg_disp = folium.FeatureGroup(name="真實調度足跡（大小=容量）").add_to(m)
        for g, cap in caps.items():
            lon, lat, nm = sd[g]
            folium.CircleMarker(
                [lat, lon], radius=4 + 10 * (cap / cmax), color="#1f4e79",
                fill=True, fill_color="#2e75b6", fill_opacity=0.85, weight=1,
                popup=folium.Popup(f"調度站 {nm}<br>容量 {cap:.1f} 台/窗", max_width=240),
                tooltip=f"調度 {nm}: {cap:.0f} 台/窗",
            ).add_to(fg_disp)

    # Top OD 流（cluster 起點出發的前 40 條）
    od = demand.origin_od_table(cluster)
    od = sorted(od, key=lambda r: r["lambda_base"], reverse=True)[:40]
    for r in od:
        i, j = r["origin"], r["dst"]
        if i in sd and j in sd:
            folium.PolyLine([[sd[i][1], sd[i][0]], [sd[j][1], sd[j][0]]],
                            color="#555", weight=1 + 2 * (r["lambda_base"] / od[0]["lambda_base"]),
                            opacity=0.4, tooltip=f"{sd[i][2]}→{sd[j][2]}: {r['lambda_base']:.1f}").add_to(fg_od)

    folium.LayerControl().add_to(m)
    p = os.path.join(C.RESULTS, "map_cluster.html"); m.save(p)
    print("  ->", p)


def map_exp2_interactive():
    p2 = os.path.join(C.RESULTS, "exp2_dispatch.csv")
    if not os.path.exists(p2):
        return
    sd = geo.station_dict()
    rows = _read_csv(p2)
    vals = [float(r["mean_with"]) / 60 for r in rows]
    norm, cmap, vmin, vmax = _color_scale(vals, "RdYlGn_r")  # 綠=cost低=好
    clon, clat, _ = sd[C.CLUSTER_CENTER]
    m = folium.Map(location=[clat, clon], zoom_start=15, tiles="CartoDB positron",
                   control_scale=True)
    best = min(rows, key=lambda r: float(r["mean_with"]))
    for r in rows:
        s = int(r["dispatch"]); v = float(r["mean_with"]) / 60
        lon, lat, nm = sd[s]
        folium.CircleMarker(
            [lat, lon], radius=9, color="#333", weight=1,
            fill=True, fill_color=_hex(cmap, norm, v), fill_opacity=0.9,
            popup=folium.Popup(f"{nm}<br>調度站設此 → with-info 平均 cost={v:.2f} 分<br>"
                               f"Δ={float(r['mean_diff'])/60:.2f} 分", max_width=260),
            tooltip=f"{nm}: {v:.2f} 分",
        ).add_to(m)
    bl = sd[int(best["dispatch"])]
    folium.Marker([bl[1], bl[0]], tooltip=f"最佳: {bl[2]} ({float(best['mean_with'])/60:.2f}分)",
                  icon=folium.Icon(color="red", icon="star", prefix="fa")).add_to(m)
    p = os.path.join(C.RESULTS, "map_exp2.html"); m.save(p)
    print("  ->", p)


# ---------------------------------------------------------------- 靜態地圖
def _to_webmerc(lon, lat):
    R = 6378137.0
    x = R * math.radians(lon)
    y = R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return x, y


def _basemap(ax):
    try:
        import contextily as cx
        cx.add_basemap(ax, source=cx.providers.CartoDB.Positron, crs="EPSG:3857", attribution_size=5)
    except Exception as e:
        print("    (basemap 跳過:", str(e)[:60], ")")


def map_cluster_static():
    sd, cluster, load, (clon, clat) = _cluster_ctx()
    fig, ax = plt.subplots(figsize=(9, 9))
    xs, ys, ds = [], [], []
    for s in cluster:
        x, y = _to_webmerc(*sd[s][:2]); xs.append(x); ys.append(y); ds.append(load.get(s, 0.0))
    ds = np.array(ds)
    sc = ax.scatter(xs, ys, s=20 + 180 * ds / (ds.max() or 1), c=ds, cmap="YlOrRd",
                    edgecolors="k", linewidths=0.4, alpha=0.9, zorder=3)
    plt.colorbar(sc, ax=ax, fraction=0.035, pad=0.02, label="借車需求 (趟/日)，即使用者起點權重")
    # Goal / 最佳調度（不再畫 START_STATIONS 假三角；起點由圓點需求權重表示）
    gx, gy = _to_webmerc(*sd[C.GOAL_STATION][:2])
    ax.scatter([gx], [gy], marker="*", s=420, c="lime", edgecolors="k", zorder=5, label="Goal 公館")
    # 真實調度足跡（藍方塊，大小=容量）
    from simulate import dispatch_footprint
    caps = dispatch_footprint(cluster)
    if caps:
        cmax = max(caps.values())
        for g, cap in caps.items():
            x, y = _to_webmerc(*sd[g][:2])
            ax.scatter([x], [y], marker="s", s=30 + 120 * cap / cmax, c="#2e75b6",
                       edgecolors="navy", linewidths=0.5, zorder=4, alpha=0.85)
        ax.scatter([], [], marker="s", c="#2e75b6", edgecolors="navy", label="真實調度足跡(大小=容量)")
    ax.scatter([], [], marker="o", c="orange", edgecolors="k", label="站點(大小=借車需求/起點)")
    ax.set_aspect("equal")   # 維持地圖長寬比（Web Mercator）
    _basemap(ax)
    ax.set_title(f"YouBike 模擬 cluster（官方臺大專區∪宿舍∪公館, {len(cluster)} 站）")
    ax.set_xticks([]); ax.set_yticks([]); ax.legend(loc="upper right", fontsize=9)
    fig.tight_layout()
    p = os.path.join(C.RESULTS, "map_cluster.png"); fig.savefig(p, dpi=150); plt.close(fig)
    print("  ->", p)


def map_exp2_static():
    p2 = os.path.join(C.RESULTS, "exp2_dispatch.csv")
    if not os.path.exists(p2):
        return
    sd = geo.station_dict()
    rows = _read_csv(p2)
    fig, ax = plt.subplots(figsize=(9, 9))
    xs, ys, vs = [], [], []
    for r in rows:
        x, y = _to_webmerc(*sd[int(r["dispatch"])][:2]); xs.append(x); ys.append(y)
        vs.append(float(r["mean_with"]) / 60)
    vs = np.array(vs)
    sc = ax.scatter(xs, ys, s=130, c=vs, cmap="RdYlGn_r", edgecolors="k", linewidths=0.5, zorder=3)
    plt.colorbar(sc, ax=ax, fraction=0.035, pad=0.02, label="調度站設此 → with-info 平均 cost (分)")
    best = min(rows, key=lambda r: float(r["mean_with"]))
    bx, by = _to_webmerc(*sd[int(best["dispatch"])][:2])
    ax.scatter([bx], [by], marker="*", s=420, c="gold", edgecolors="k", zorder=5,
               label=f"最佳: {sd[int(best['dispatch'])][2]}")
    ax.set_aspect("equal")   # 維持地圖長寬比（Web Mercator）
    _basemap(ax)
    ax.set_title(f"附錄(實驗二)：單點調度位置品質（綠=cost 低=佳, 實證α≈{C.ALPHA_EMPIRICAL})")
    ax.set_xticks([]); ax.set_yticks([]); ax.legend(loc="upper right", fontsize=9)
    fig.tight_layout()
    p = os.path.join(C.RESULTS, "map_exp2.png"); fig.savefig(p, dpi=150); plt.close(fig)
    print("  ->", p)


def main():
    from analyze import _setup_cjk_font
    _setup_cjk_font()
    map_cluster_interactive()
    map_exp2_interactive()
    map_cluster_static()
    map_exp2_static()
    print("地圖完成。")


if __name__ == "__main__":
    main()
