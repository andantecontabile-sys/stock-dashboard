"""路徑、常數與民國紀年轉換。"""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent

INBOX_DIR = ROOT / "inbox"
INBOX_ARCHIVE_DIR = INBOX_DIR / "archive"
INBOX_BSR_DIR = INBOX_DIR / "bsr"
CACHE_DIR = ROOT / "cache"
DEBUG_DIR = ROOT / "debug"
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"

TICKER_MASTER = DATA_DIR / "ticker_master.csv"
TICKER_MASTER_MAX_AGE_DAYS = 7  # CLAUDE.md §3：每週重建一次

# CLAUDE.md §4.3
CACHE_TTL_DAYS_FINANCIALS = 30

# CLAUDE.md §5：河流圖回看區間與分位點
RIVER_YEARS = 5
PERCENTILE_POINTS = (10, 25, 50, 75, 90)

# TWSE 對每秒請求數有節流，超過會回 429 並短暫封鎖。
TWSE_REQUEST_INTERVAL_SEC = 3.2
TPEX_REQUEST_INTERVAL_SEC = 1.5

USER_AGENT = "daily-equity-dashboard/1.0 (personal research use)"


def today() -> dt.date:
    return dt.date.today()


def roc_to_date(s: str) -> Optional[dt.date]:
    """民國日期字串轉西元 date。

    證交所在不同端點用了三種格式，全部要吃：
      "1150813"        STOCK_DAY_ALL / BWIBBU_ALL
      "115/08/13"      STOCK_DAY 個股歷史
      "115年08月13日"   BWIBBU 個股歷史
    """
    s = (s or "").strip()
    if not s:
        return None

    digits = ""
    if "年" in s:
        s = s.replace("年", "/").replace("月", "/").replace("日", "")
    if "/" in s:
        parts = [p for p in s.split("/") if p]
        if len(parts) != 3:
            return None
        try:
            roc_year, month, day = (int(p) for p in parts)
        except ValueError:
            return None
    else:
        digits = "".join(ch for ch in s if ch.isdigit())
        if len(digits) != 7:
            return None
        roc_year, month, day = int(digits[:3]), int(digits[3:5]), int(digits[5:7])

    try:
        return dt.date(roc_year + 1911, month, day)
    except ValueError:
        return None


def date_to_roc_compact(d: dt.date) -> str:
    """西元 date 轉 "1150813" 格式。"""
    return "{:03d}{:02d}{:02d}".format(d.year - 1911, d.month, d.day)


def anthropic_api_key() -> Optional[str]:
    """從環境變數或 .env 讀取金鑰。缺少時回 None，呼叫端須自行降級。"""
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key.strip()

    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("ANTHROPIC_API_KEY="):
                value = line.split("=", 1)[1].strip().strip("'\"")
                return value or None
    return None


def ensure_dirs() -> None:
    for path in (
        INBOX_DIR,
        INBOX_ARCHIVE_DIR,
        INBOX_BSR_DIR,
        CACHE_DIR,
        DEBUG_DIR,
        DATA_DIR,
        OUTPUT_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)
