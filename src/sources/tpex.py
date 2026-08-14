"""上櫃（TPEx）資料源。

欄位名與上市完全不同（SecuritiesCompanyCode vs Code、PriceEarningRatio vs PEratio），
所以這裡是獨立解析器，不共用 twse.py（CLAUDE.md §8）。

已知限制（2026-08-14 實測）：
  上櫃的個股歷史本益比端點 www/zh-tw/afterTrading/peQry 回 302，官方已搬遷且未公告新位置。
  因此上櫃標的目前只有「當日」PER/PBR，沒有五年歷史 → M1/M2 一律 applicable=False，
  並在 HTML 標示「資料缺漏：上櫃歷史本益比端點失效」。不以上市端點頂替，不以當日值外推。
"""
from __future__ import annotations

import datetime as dt
from typing import Dict, List

from .. import config
from ..http import FetchError, get_json
from ..util import parse_number
from .twse import DailyQuote, RatioPoint

OPENAPI = "https://www.tpex.org.tw/openapi/v1"
WWW = "https://www.tpex.org.tw/www/zh-tw/afterTrading"

SOURCE = "tpex"

RATIO_HISTORY_UNAVAILABLE = "上櫃個股歷史本益比端點（peQry）已失效，無五年分位樣本"


def fetch_ticker_master() -> List[Dict[str, str]]:
    rows = get_json(SOURCE, "mopsfin_t187ap03_O", OPENAPI + "/mopsfin_t187ap03_O",
                    ttl_days=config.TICKER_MASTER_MAX_AGE_DAYS,
                    interval=config.TPEX_REQUEST_INTERVAL_SEC, debug_dump=True)
    return [r for r in rows if isinstance(r, dict)]


def fetch_daily_all() -> Dict[str, DailyQuote]:
    rows = get_json(SOURCE, "daily_close_quotes",
                    OPENAPI + "/tpex_mainboard_daily_close_quotes",
                    interval=config.TPEX_REQUEST_INTERVAL_SEC, debug_dump=True)
    result: Dict[str, DailyQuote] = {}
    for row in rows:
        code = (row.get("SecuritiesCompanyCode") or "").strip()
        if not code:
            continue
        result[code] = DailyQuote(
            code=code,
            name=(row.get("CompanyName") or "").strip(),
            date=config.roc_to_date(row.get("Date", "")),
            open_=parse_number(row.get("Open")),
            high=parse_number(row.get("High")),
            low=parse_number(row.get("Low")),
            close=parse_number(row.get("Close")),
            volume=parse_number(row.get("TradingShares")),
            value=parse_number(row.get("TransactionAmount")),
        )
    return result


def fetch_ratios_all() -> Dict[str, RatioPoint]:
    rows = get_json(SOURCE, "peratio_analysis",
                    OPENAPI + "/tpex_mainboard_peratio_analysis",
                    interval=config.TPEX_REQUEST_INTERVAL_SEC, debug_dump=True)
    result: Dict[str, RatioPoint] = {}
    for row in rows:
        code = (row.get("SecuritiesCompanyCode") or "").strip()
        if not code:
            continue
        result[code] = RatioPoint(
            date=config.roc_to_date(row.get("Date", "")),
            per=parse_number(row.get("PriceEarningRatio")),
            pbr=parse_number(row.get("PriceBookRatio")),
            dividend_yield=parse_number(row.get("YieldRatio")),
        )
    return result


def fetch_ratio_history(stock_no: str, years: int = config.RIVER_YEARS) -> List[RatioPoint]:
    """目前無官方端點可用，一律回空序列。呼叫端須據此標示資料缺漏，不得靜默補值。"""
    return []


def fetch_price_history(stock_no: str, years: int = config.RIVER_YEARS) -> List[DailyQuote]:
    """個股逐日成交資訊。端點 tradingStock 的回應包在 tables[0].data。"""
    today = config.today()
    bars: List[DailyQuote] = []

    year, month = today.year - years, today.month
    while (year, month) <= (today.year, today.month):
        key = "tradingStock_{}_{:04d}{:02d}".format(stock_no, year, month)
        try:
            payload = get_json(
                SOURCE, key, WWW + "/tradingStock",
                params={"code": stock_no, "date": "{:04d}/{:02d}/01".format(year, month),
                        "id": "", "response": "json"},
                ttl_days=config.CACHE_TTL_DAYS_FINANCIALS,
                interval=config.TPEX_REQUEST_INTERVAL_SEC,
            )
        except FetchError:
            payload = None

        if payload:
            for table in payload.get("tables") or []:
                for row in table.get("data") or []:
                    # 日期, 成交仟股, 成交仟元, 開盤, 最高, 最低, 收盤, 漲跌, 筆數
                    if len(row) < 7:
                        continue
                    date = config.roc_to_date(row[0])
                    if date is None:
                        continue
                    volume_lots = parse_number(row[1])
                    value_thousands = parse_number(row[2])
                    bars.append(DailyQuote(
                        code=stock_no, name="", date=date,
                        open_=parse_number(row[3]),
                        high=parse_number(row[4]),
                        low=parse_number(row[5]),
                        close=parse_number(row[6]),
                        # 上櫃是「仟股」與「仟元」，換算成股與元才能跟上市比
                        volume=None if volume_lots is None else volume_lots * 1000,
                        value=None if value_thousands is None else value_thousands * 1000,
                    ))

        month += 1
        if month > 12:
            year, month = year + 1, 1

    bars.sort(key=lambda b: b.date)
    return bars
