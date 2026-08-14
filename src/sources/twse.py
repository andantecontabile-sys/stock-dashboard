"""上市（TWSE）資料源。

欄位名以 2026-08-14 實際打過的回應為準，原始樣本留在 debug/probe/（鐵則 3）。
上櫃的欄位名完全不同，見 tpex.py — 兩邊不可共用解析器（CLAUDE.md §8）。
"""
from __future__ import annotations

import datetime as dt
from typing import Dict, List, Optional

from .. import config
from ..http import FetchError, get_json
from ..util import parse_number

OPENAPI = "https://openapi.twse.com.tw/v1"
RWD = "https://www.twse.com.tw/rwd/zh/afterTrading"

SOURCE = "twse"


class DailyQuote:
    """單日行情。close 為未還原收盤價，只准用於顯示今日價（鐵則 4）。"""

    __slots__ = ("code", "name", "date", "open", "high", "low", "close", "volume", "value")

    def __init__(self, code, name, date, open_, high, low, close, volume, value):
        self.code = code
        self.name = name
        self.date = date
        self.open = open_
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume
        self.value = value


class RatioPoint:
    """某一交易日的官方本益比／股價淨值比／殖利率。"""

    __slots__ = ("date", "per", "pbr", "dividend_yield")

    def __init__(self, date, per, pbr, dividend_yield):
        self.date = date
        self.per = per
        self.pbr = pbr
        self.dividend_yield = dividend_yield


def fetch_ticker_master() -> List[Dict[str, str]]:
    """上市公司基本資料。回傳的 key 是中文，這是官方端點的原樣。"""
    rows = get_json(SOURCE, "t187ap03_L", OPENAPI + "/opendata/t187ap03_L",
                    ttl_days=config.TICKER_MASTER_MAX_AGE_DAYS, debug_dump=True)
    return [r for r in rows if isinstance(r, dict)]


def fetch_daily_all() -> Dict[str, DailyQuote]:
    """全上市個股最新一個交易日行情，key 為股票代號。"""
    rows = get_json(SOURCE, "STOCK_DAY_ALL", OPENAPI + "/exchangeReport/STOCK_DAY_ALL",
                    debug_dump=True)
    result: Dict[str, DailyQuote] = {}
    for row in rows:
        code = (row.get("Code") or "").strip()
        if not code:
            continue
        result[code] = DailyQuote(
            code=code,
            name=(row.get("Name") or "").strip(),
            date=config.roc_to_date(row.get("Date", "")),
            open_=parse_number(row.get("OpeningPrice")),
            high=parse_number(row.get("HighestPrice")),
            low=parse_number(row.get("LowestPrice")),
            close=parse_number(row.get("ClosingPrice")),
            volume=parse_number(row.get("TradeVolume")),
            value=parse_number(row.get("TradeValue")),
        )
    return result


def fetch_ratios_all() -> Dict[str, RatioPoint]:
    """全上市個股最新一日的官方 PER/PBR/殖利率。

    注意：PEratio 對虧損股是空字串（實測台泥即為空），parse_number 會回 None，
    呼叫端必須當成資料缺漏，不可視為 0。
    """
    rows = get_json(SOURCE, "BWIBBU_ALL", OPENAPI + "/exchangeReport/BWIBBU_ALL",
                    debug_dump=True)
    result: Dict[str, RatioPoint] = {}
    for row in rows:
        code = (row.get("Code") or "").strip()
        if not code:
            continue
        result[code] = RatioPoint(
            date=config.roc_to_date(row.get("Date", "")),
            per=parse_number(row.get("PEratio")),
            pbr=parse_number(row.get("PBratio")),
            dividend_yield=parse_number(row.get("DividendYield")),
        )
    return result


def _month_starts(years: int) -> List[dt.date]:
    """回看 N 年，每個月的第一天，由舊到新。"""
    today = config.today()
    months: List[dt.date] = []
    year, month = today.year - years, today.month
    while (year, month) <= (today.year, today.month):
        months.append(dt.date(year, month, 1))
        month += 1
        if month > 12:
            year, month = year + 1, 1
    return months


def fetch_ratio_history(stock_no: str, years: int = config.RIVER_YEARS) -> List[RatioPoint]:
    """個股逐日 PER/PBR 歷史，來源為證交所 BWIBBU（以個股月查詢）。

    這是官方逐日序列：分母是「該日當時已知的 EPS／每股淨值」，分子是該日實際收盤價。
    除權息當天價格與比值同步下修，因此這個序列本身就是可比的，
    不需要（也不應該）再拿還原股價去除以今天的 EPS —— 那反而會算錯（見鐵則 4 的用意）。
    """
    points: List[RatioPoint] = []
    for month in _month_starts(years):
        key = "BWIBBU_{}_{:%Y%m}".format(stock_no, month)
        try:
            payload = get_json(
                SOURCE, key, RWD + "/BWIBBU",
                params={"date": month.strftime("%Y%m%d"), "stockNo": stock_no,
                        "response": "json"},
                ttl_days=config.CACHE_TTL_DAYS_FINANCIALS,
            )
        except FetchError:
            continue  # 單月抓不到就跳過，最後由樣本數檢查決定可用性

        if payload.get("stat") != "OK":
            continue
        for row in payload.get("data") or []:
            # fields: 日期, 殖利率(%), 股利年度, 本益比, 股價淨值比, 財報年/季
            if len(row) < 5:
                continue
            date = config.roc_to_date(row[0])
            if date is None:
                continue
            points.append(RatioPoint(
                date=date,
                per=parse_number(row[3]),
                pbr=parse_number(row[4]),
                dividend_yield=parse_number(row[1]),
            ))

    points.sort(key=lambda p: p.date)
    return points


def fetch_price_history(stock_no: str, years: int = config.RIVER_YEARS) -> List[DailyQuote]:
    """個股逐日成交資訊（未還原）。供量能與顯示用，不作為分位計算基礎。"""
    bars: List[DailyQuote] = []
    for month in _month_starts(years):
        key = "STOCK_DAY_{}_{:%Y%m}".format(stock_no, month)
        try:
            payload = get_json(
                SOURCE, key, RWD + "/STOCK_DAY",
                params={"date": month.strftime("%Y%m%d"), "stockNo": stock_no,
                        "response": "json"},
                ttl_days=config.CACHE_TTL_DAYS_FINANCIALS,
            )
        except FetchError:
            continue

        if payload.get("stat") != "OK":
            continue
        for row in payload.get("data") or []:
            # fields: 日期, 成交股數, 成交金額, 開盤價, 最高價, 最低價, 收盤價, 漲跌價差, 成交筆數, 註記
            if len(row) < 7:
                continue
            date = config.roc_to_date(row[0])
            if date is None:
                continue
            bars.append(DailyQuote(
                code=stock_no, name="", date=date,
                open_=parse_number(row[3]),
                high=parse_number(row[4]),
                low=parse_number(row[5]),
                close=parse_number(row[6]),
                volume=parse_number(row[1]),
                value=parse_number(row[2]),
            ))

    bars.sort(key=lambda b: b.date)
    return bars
