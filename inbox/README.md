# inbox

把有價值的粉專貼文、週報丟進這個資料夾，執行時會自動讀取。

- `*.txt` / `*.md` — 貼文全文
- `*.png` / `*.jpg` — 手機截圖（目前只計數並在 HTML 標示，尚未 OCR）
- `bsr/` — 券商分點日報表 CSV（Sprint 3 才會用到）

第一行可選填 metadata，缺省時由模型推斷：

```
::source=某粉專 ::date=2026-08-10 ::stance=看多
```

處理完的檔案會移到 `archive/YYYYMMDD/`。本檔案（README.md）不會被讀取或搬移。
