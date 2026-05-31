# CNL YouBike 模擬實驗 — 資料說明

實驗機器：`ssh ws7`，主資料夾 `/tmp2/pinhao/cnl_youbike/`
環境：Python 3.14.4、144 cores、755Gi RAM、5.4T free on /tmp2。
專案 venv：`/tmp2/pinhao/cnl_youbike/venv`（已裝 gdown）。

## 目錄結構
```
cnl_youbike/
├── venv/                 # 專案虛擬環境
├── data/raw/             # 原始資料（見下）
├── data/processed/       # 清理後的中介檔
├── src/                  # 模擬器與資料管線
├── results/              # 實驗輸出（圖、表）
└── docs/                 # 文件
```

## 資料來源 1 — Google Drive（創創資料）
檔名：`ubike_station_dynamics_202508_202509.zip`（9.1 GB 壓縮 / 43.9 GB 解壓）
內容：**YouBike 2.0 即時場站動態資料**，2025-08 ~ 2025-09，輪詢快照，逐筆一站一次。
CSV 無表頭，18 欄（YouBike 2.0 標準格式推斷）：

| # | 欄位 | 意義 | 範例 |
|---|---|---|---|
| 1 | sno | 站點 ID | 500101022 |
| 2 | sna | 站名(中) | YouBike2.0_捷運公館站(2號出口) |
| 3 | tot | 總車格數 | 52 |
| 4 | sbi | 可借車輛數 | 0 |
| 5 | sarea | 行政區 | 大安區 |
| 6 | mday | 狀態最後變更時間 | 2025-08-01 00:08:15 |
| 7 | lat | 緯度 | 25.014910 |
| 8 | lng | 經度 | 121.534380 |
| 9 | ar | 地址(中) | 捷運公館站(2號出口)外側 |
| 10 | sareaen | 行政區(英) | Daan Dist. |
| 11 | snaen | 站名(英) | |
| 12 | aren | 地址(英) | |
| 13 | bemp | 可還空位數 | 52 |
| 14 | act | 啟用狀態 1/0 | 1 |
| 15-17 | 多個時間戳 | 抓取/來源更新時間 | |
| 18 | infoDate | 日期 | 2025-08-01 |

用途：
- 由 sbi 隨時間變化 → 推導各站每小時出借量 → **出發時間分布 P^i(t)**（§6）。
- sbi=0 事件 → 實證 **缺車比例**，校準 α（§5、§9）。
- 站點容量 tot、座標、啟用狀態。

## 資料來源 2 — data.taipei（臺北市 YouBike 起訖站點統計）
dataset id：c7dbdb7c-6bbd-495a-bd23-49b22defd83e，GEOJSON，分平日/假日，月份 202507 & 202512。
- `odstat_weekday_202512.geojson` (12 MB, 20680 OD pairs, 1624 stations) ← 建議主檔
- `odstat_weekend_202512.geojson` (2.4 MB)
- `odstat_weekday_202507.geojson` (6.5 MB)
- `odstat_weekend_202507.geojson` (1.1 MB)

每個 feature = 一組起訖配對：
- `on_stop_id/off_stop_id`, `on_stop/off_stop`：起訖站 ID/名
- `sum_of_txn_times`：**月交易量 D_m^{ij}**（§6 Step 1 的輸入）
- LineString 端點座標 = 起/訖站經緯度
- `district_origin/destination`

用途：§6 需求估計的月 OD 矩陣 D_m^{ij}；§3 站點圖座標。

## 重要發現 / 待釐清
- NTU 校園站點完整（500119xxx 系列 + 公館多出口 500101022/181、500106003/004）。
- **「德田館」(§3 P_init) 不是 YouBike 站名**，需釐清對應哪個實體站作為 agent 起點。
- 缺車事件實證可行（如公館站 2025-08-01 00:08 sbi=0）。
