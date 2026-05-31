#!/usr/bin/env bash
# 端到端管線：站點/OD → P^i(t) → 實證統計 → 實驗 → 圖 → 地圖。
# 用法：bash run_pipeline.sh   （在 src/ 下執行）
set -e
cd "$(dirname "$0")"
# Python：優先用環境變數 PYTHON，否則用 ../venv/bin/python，再退回 python3
PY="${PYTHON:-../venv/bin/python}"
[ -x "$PY" ] || PY=python3

echo "=== [1/6] 站點主檔與 OD 矩陣 ==="
$PY build_stations.py

echo "=== [2/6] 由動態資料推導 P^i(t) ==="
CLUSTER_SIDS=$($PY -c "import geo; print(chr(32).join(map(str, geo.ntu_cluster())))")
$PY build_pit.py $CLUSTER_SIDS

echo "=== [3/6] 實證統計（缺車站/真實調度足跡/滿位率/α 錨點）==="
$PY empirical.py

echo "=== [4/6] 實驗一 + 二維熱圖(α×cap) + 附錄最佳單點 ==="
$PY experiments.py

echo "=== [5/6] 分析繪圖 ==="
$PY analyze.py

echo "=== [6/7] 地圖視覺化（OSM + Leaflet）==="
$PY viz_map.py

echo "=== [7/7] agent 移動動畫（Leaflet, anim.html）==="
$PY export_anim.py

echo "=== 完成。results/ 內容： ==="
ls -la ../results/
