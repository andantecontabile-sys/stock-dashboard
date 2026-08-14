# 每日選股儀表板

本機一鍵執行，產出單一 `output/dashboard_YYYYMMDD.html`。不架伺服器、不上雲、不常駐。

規格與鐵則見 [CLAUDE.md](CLAUDE.md)。**目前完成度：Sprint 1（台股 + M1/M2 + inbox 匯入）。**

## 執行

```
./run.command          # macOS，首次執行會自動建 venv 並裝套件
run.bat                # Windows
```

常用參數：

```
./run.command --ticker 2330          # 直接指定標的，略過 inbox
./run.command --ticker 2330 --ticker 2327
./run.command --no-open              # 產出後不開瀏覽器
./run.command --rebuild-tickers      # 強制重建 data/ticker_master.csv
```

## 放貼文進 inbox

把粉專貼文存成 `inbox/任意檔名.txt`（或 `.md`），第一行可選填 metadata：

```
::source=某粉專 ::date=2026-08-10 ::stance=看多
（以下貼上貼文全文）
```

執行後檔案會移到 `inbox/archive/YYYYMMDD/`。

標的抽取用 Claude 做命名實體辨識（CLAUDE.md §3 禁止用 regex 比對中文簡稱），
需要在專案根目錄建立 `.env`：

```
ANTHROPIC_API_KEY=sk-ant-...
```

**沒設金鑰時抽取會停用**，並在 HTML 的資料缺漏清單裡說明原因。這是刻意的：
抽錯標的會讓整份估值指向錯誤的公司，比抽不到更糟。此時改用 `--ticker` 直接指定。

## 現況與已知限制

| 項目 | 狀態 |
|---|---|
| 上市（TWSE）M1 P/E 河流圖、M2 P/B 河流圖 | ✅ 已驗證，2330 數字與證交所官方一致 |
| 上櫃（TPEX）當日 PER/PBR | ✅ |
| 上櫃五年歷史分位 | ❌ 官方 `peQry` 端點回 302 已搬遷，M1/M2 一律標為資料缺漏 |
| inbox 截圖 OCR | ❌ 只計數並標示，不解讀 |
| M3 PEG / M4 DDM / M5 DCF、美股 | ❌ Sprint 2 |
| 籌碼層 F1–F4、觀察等級 | ❌ Sprint 3 |

**Sprint 1 未通過驗證前不得進入 Sprint 2**（CLAUDE.md §9）。

## 兩處與規格的刻意差異

1. **分位用證交所官方逐日 PER/PBR 序列，未自行以還原股價重算。**
   官方序列的分子是當日收盤價、分母是當日已知的每股數值，除權息當天同步變動，
   序列本身即可比。若改用還原股價除以「今天」的 EPS，等於把今天的獲利套到五年前的價格上
   —— 那正是鐵則 4 要避免的錯。

2. **帶狀圖用內嵌 SVG，不走 Chart.js CDN。**
   §7 同時要求「單一自包含 HTML」與「CDN + 離線退化為表格」，兩者互斥。
   內嵌 SVG 兩個目標都滿足，離線一樣看得到圖。

## 開發

```
.venv/bin/python -m pytest tests/ -q
```

每個估值模型都有用手算過的固定輸入寫的測試（CLAUDE.md §10）。
新接 API 端點時，先把原始回應 dump 到 `debug/`，人工確認欄位名後再寫解析器（鐵則 3）——
2026-08-14 的探測樣本留在 `debug/probe/`。

## 目錄

```
src/sources/     twse.py / tpex.py — 兩市場欄位名不同，解析器不可共用
src/models/      river.py 為 M1/M2 共用骨幹，cyclical.py 為循環股名單
cache/           API 回應快取，{source}/{date}/{key}.json
debug/probe/     首次接端點時的原始回應樣本
```
