#!/usr/bin/env bash
# 編譯英文正式報告 REPORT.tex -> REPORT.pdf
#
# 需求：XeLaTeX + BibTeX（TeX Live），中文字型 Noto Sans CJK TC。
# 參考文獻用 BibTeX（references.bib）管理，故必須跑完整 4 步；
# 只跑一次 xelatex 內文引用會變成 [?]（bibtex 尚未解析）。
# 圖片取自 results/（graphicspath 已指向該目錄），請先跑過 src/run_pipeline.sh
# 或使用已入庫的 results/*.png。
set -e
cd "$(dirname "$0")"

xelatex -interaction=nonstopmode -halt-on-error REPORT.tex
bibtex   REPORT
xelatex -interaction=nonstopmode -halt-on-error REPORT.tex
xelatex -interaction=nonstopmode -halt-on-error REPORT.tex

echo "完成 -> REPORT.pdf"
