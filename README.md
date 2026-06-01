# 共享單車調度資訊對使用者等待成本之模擬

> 計算機網路實驗 期末專題 ｜ 第四組 ｜ CN-Team4

以臺大校園 YouBike 尖峰缺車為場景的 time-step 模擬。比較使用者在「**取得調度資訊**」與
「**未取得調度資訊**」兩情境下抵達目的地的平均時間成本,主指標為兩組 cost 差。
**唯一操弄變量是資訊**;調度供給(位置、容量)兩組完全相同且**由真實資料還原**。

完整規格見 [`docs/final.md`](docs/final.md);結果與結論見 [`docs/RESULTS.md`](docs/RESULTS.md)、
[`docs/CONCLUSIONS.md`](docs/CONCLUSIONS.md)。

## 主要結果(摘要)
- 臺大實證缺車比例 ~28%(由真實 sbi=0 推得)、物理合理調度量(50–200 台/尖峰窗)下,
  **公開調度資訊使平均抵達時間下降約 1.9–2.5 分鐘(16–23%,中估~2.1 分/19%)**;
  在假說區間 10–20% 缺車則下降 2.4–3.2 分鐘(22–31%)。
- 資訊在「缺車程度低 + 調度量充足」時最有效(見 α×調度量 二維熱圖)。
- 結論對唯一行為假設 τ(繞路容忍)**穩健**(τ=0.3~0.9 下 Δ 相差 <0.5 分鐘)。
- 最佳調度位置在校園核心;現有營運主力公館站位於邊緣(殘餘需求在校園深處)。

## 資料來源
1. **YouBike 2.0 即時場站動態** 2025-08~09(Google Drive,9.1GB zip / 43.9GB csv;**本研究取值自
   2025-09-01 起、僅平日**)——推導出發時間分布 $P^i(t)$、真實調度足跡、缺車率、滿位率。
2. **臺北市 YouBike 起訖站點統計**(data.taipei,GEOJSON)——月 OD 交易量 $D_m^{ij}$、站點座標。

兩者皆由 `fetch_data.sh` 自動下載(原始大檔不入庫)。

## 重現步驟
```bash
# 1. 環境（Python 3.14）
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. 下載原始資料（約 9GB 下載 / 解壓後 ~44GB，需磁碟空間）
bash fetch_data.sh

# 3. 一鍵跑完整管線：站點→P^i(t)→實證統計→實驗→圖→地圖→動畫
cd src && bash run_pipeline.sh
# 結果輸出於 results/（圖、CSV、互動 html、動畫 html）
```
> 註:`data/processed/*.parquet`(站點、OD、$P^i(t)$、實證統計)已入庫,
> 若只想重跑模擬與繪圖、不重算 44GB,可直接 `cd src && python experiments.py && python analyze.py`。

## 目錄結構
```
src/                模擬與資料管線（見下表）
docs/               final.md(spec)、DATA.md、RESULTS.md、CONCLUSIONS.md
data/processed/     中介檔(parquet,已入庫)；data/raw/ 為原始大檔(不入庫)
results/            圖(png)、表(csv)、互動地圖/動畫(html)
fetch_data.sh       下載原始資料
requirements.txt    套件版本
```

| 模組 | 章節 | 功能 |
|---|---|---|
| `config.py` | §5 | 全域參數與預設值 |
| `build_stations.py` | §3,§6 | OD GEOJSON → 站點主檔 + 月 OD 矩陣 |
| `build_pit.py` | §6 | 44GB 動態資料 → 各站每小時出借占比 $P^i(t)$ |
| `empirical.py` | §3.2,§5 | 實證：真實調度足跡、缺車站、滿位率、α 錨點 |
| `geo.py` | §2,§3 | Manhattan 距離、官方 NTU cluster(76 站) |
| `demand.py` | §6 | 需求估計 + 缺車空間加權 |
| `simulate.py` | §7,§8 | time-step 模擬器(決策+成本+調度容量配置) |
| `experiments.py` | §9 | 實驗一(α)、二維熱圖、τ 敏感度、最佳位置 |
| `analyze.py` | §8 | 繪圖 |
| `viz_map.py` | §11 | OSM+Leaflet 互動/靜態地圖 |
| `export_anim.py` | §11 | agent 移動動畫 |

## 模型重點
- cluster = 官方「臺大專區」∪ 站名含臺大 ∪ 公館 − 市區臺大醫院 = **76 站**(不用任意半徑)。
- 調度站分布由動態資料偵測補車事件還原(37 站);總量難精確量測,錨物理中估 100 台/尖峰窗、
  當不確定參數掃描(50–200),為最大不確定來源。
- without-info:去最近站、恰為調度站才借到(地理決定);with-info:容忍距離內最近調度站借到。
- 不含等待(隔離資訊效果);含還車側成本(依實測滿位率)。
- α、調度量縮放 為掃描變量;τ 為唯一行為假設(做敏感度)。

## 授權與資料
資料版權屬臺北市政府與 YouBike;本 repo 僅含程式與衍生結果,原始資料請自行以 `fetch_data.sh` 取得。
