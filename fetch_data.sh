#!/usr/bin/env bash
# 下載原始資料到 data/raw/。需先 pip install gdown（見 requirements.txt）。
# 1) Google Drive：YouBike 2.0 即時場站動態 2025-08~09（9.1GB zip / 43.9GB csv）
# 2) data.taipei：臺北市 YouBike 起訖站點統計（4 個 GEOJSON）
set -e
cd "$(dirname "$0")"
RAW=data/raw
mkdir -p "$RAW"
PY=${PYTHON:-python3}

echo "=== [1/2] Google Drive 即時動態資料（大檔，約 9GB 下載）==="
ZIP="$RAW/ubike_station_dynamics_202508_202509.zip"
if [ ! -f "$RAW/ubike2.0即時場站動態資料_202508_202509.csv" ]; then
  $PY -m gdown "16VQuwMU2o1xXQwZ8H2TUf_zpfhmJcgfn" -O "$ZIP"
  echo "解壓中（→ 43.9GB）..."; unzip -o "$ZIP" -d "$RAW"
else
  echo "已存在，略過。"
fi

echo "=== [2/2] data.taipei 起訖統計 GEOJSON ==="
declare -A R=(
  [odstat_weekday_202512]=0a875ec8-c974-49ac-bbfc-887f220f403a
  [odstat_weekend_202512]=4b7341cf-22c2-4dd1-9121-9a916d46e6d1
  [odstat_weekday_202507]=bb00cae4-2f06-484d-9b97-26fc9221757d
  [odstat_weekend_202507]=4b71676f-f52b-4125-ac2b-dd794d2e8501
)
for name in "${!R[@]}"; do
  curl -sL -m 180 "https://data.taipei/api/frontstage/tpeod/dataset/resource.download?rid=${R[$name]}" \
       -o "$RAW/${name}.geojson"
  echo "  ${name}.geojson  $(wc -c < "$RAW/${name}.geojson") bytes"
done
echo "=== 完成。接著執行 src/run_pipeline.sh ==="
