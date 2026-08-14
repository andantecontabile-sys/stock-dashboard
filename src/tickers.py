"""ticker_master.csv 的建立與查詢（CLAUDE.md §3）。

來源為 TWSE / TPEx 的上市上櫃公司基本資料端點，每週重建一次。
"""
from __future__ import annotations

import csv
import datetime as dt
from typing import Dict, List, Optional

from . import config
from .sources import tpex, twse

FIELDS = ["ticker", "name", "market", "industry_code", "full_name"]


class Ticker:
    __slots__ = ("ticker", "name", "market", "industry_code", "full_name")

    def __init__(self, ticker, name, market, industry_code, full_name):
        self.ticker = ticker
        self.name = name
        self.market = market                 # TWSE | TPEX
        self.industry_code = industry_code
        self.full_name = full_name


def _is_stale() -> bool:
    if not config.TICKER_MASTER.exists():
        return True
    age = dt.date.today() - dt.date.fromtimestamp(config.TICKER_MASTER.stat().st_mtime)
    return age.days >= config.TICKER_MASTER_MAX_AGE_DAYS


def rebuild() -> List[Ticker]:
    rows: List[Ticker] = []

    for row in twse.fetch_ticker_master():
        code = (row.get("公司代號") or "").strip()
        if not code:
            continue
        rows.append(Ticker(
            ticker=code,
            name=(row.get("公司簡稱") or "").strip(),
            market="TWSE",
            industry_code=(row.get("產業別") or "").strip(),
            full_name=(row.get("公司名稱") or "").strip(),
        ))

    for row in tpex.fetch_ticker_master():
        code = (row.get("SecuritiesCompanyCode") or "").strip()
        if not code:
            continue
        rows.append(Ticker(
            ticker=code,
            name=(row.get("CompanyAbbreviation") or "").strip(),
            market="TPEX",
            industry_code=(row.get("SecuritiesIndustryCode") or "").strip(),
            full_name=(row.get("CompanyName") or "").strip(),
        ))

    config.TICKER_MASTER.parent.mkdir(parents=True, exist_ok=True)
    with config.TICKER_MASTER.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for item in rows:
            writer.writerow({f: getattr(item, f) for f in FIELDS})

    return rows


def load(force_rebuild: bool = False) -> Dict[str, Ticker]:
    """回傳 {代號: Ticker}。過期或不存在時自動重建。"""
    if force_rebuild or _is_stale():
        rows = rebuild()
    else:
        rows = []
        with config.TICKER_MASTER.open(encoding="utf-8", newline="") as handle:
            for record in csv.DictReader(handle):
                rows.append(Ticker(**{f: record.get(f, "") for f in FIELDS}))

    return {t.ticker: t for t in rows}


def by_name(master: Dict[str, Ticker]) -> Dict[str, Ticker]:
    """簡稱 → Ticker。同名時保留上市那一檔。"""
    index: Dict[str, Ticker] = {}
    for item in master.values():
        if not item.name:
            continue
        existing = index.get(item.name)
        if existing is None or (existing.market == "TPEX" and item.market == "TWSE"):
            index[item.name] = item
    return index


def resolve(master: Dict[str, Ticker], ticker: str, name: str = "") -> Optional[Ticker]:
    """代號優先，其次簡稱完全相符。查不到回 None —— 呼叫端必須送進 unresolved。"""
    ticker = (ticker or "").strip().upper()
    if ticker and ticker in master:
        return master[ticker]

    name = (name or "").strip()
    if name:
        return by_name(master).get(name)
    return None
