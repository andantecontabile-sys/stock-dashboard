"""把資料層、估值層串成單一標的的分析結果。"""
from __future__ import annotations

import statistics
from typing import Dict, List, Optional

from .http import FetchError
from .models import m1_pe, m2_pb
from .models.base import ValuationResult
from .sources import tpex, twse
from .tickers import Ticker

# Sprint 1 只有 M1/M2。CLAUDE.md §5 的分歧度是為五模型設計的，
# 樣本數會直接寫進輸出，避免把兩個模型的變異係數誤讀成五模型的分歧度。
SPRINT1_MODELS = 2


class SecurityAnalysis:
    def __init__(self, ticker: Ticker):
        self.ticker = ticker
        self.price: Optional[float] = None
        self.price_date = None
        self.per: Optional[float] = None
        self.pbr: Optional[float] = None
        self.dividend_yield: Optional[float] = None
        self.ratio_date = None
        self.valuations: List[ValuationResult] = []
        self.mentions: List = []
        self.missing: List[str] = []      # 資料缺漏清單，會原樣印在 HTML（鐵則 7）

    @property
    def applicable(self) -> List[ValuationResult]:
        return [v for v in self.valuations if v.applicable]

    def divergence(self) -> Optional[Dict]:
        """模型分歧度：各模型 mid 的變異係數（CLAUDE.md §5）。"""
        mids = [v.mid for v in self.applicable if v.mid]
        if len(mids) < 2:
            return None
        mean = statistics.fmean(mids)
        if mean == 0:
            return None
        cv = statistics.pstdev(mids) / mean
        return {
            "cv": cv,
            "models_used": len(mids),
            "models_total": SPRINT1_MODELS,
            "note": "Sprint 1 僅有 M1/M2 兩個模型，此變異係數不等同五模型分歧度",
        }

    def undervalued_count(self) -> Dict:
        """現價落在幾個模型的低估區（現價低於該模型的 p25 價格）。"""
        count = sum(1 for v in self.applicable if v.low is not None
                    and self.price is not None and self.price < v.low)
        return {"count": count, "of": len(self.applicable), "sprint_total": SPRINT1_MODELS}


def _source_for(market: str):
    return tpex if market == "TPEX" else twse


def analyze(ticker: Ticker) -> SecurityAnalysis:
    result = SecurityAnalysis(ticker)
    source = _source_for(ticker.market)

    try:
        quotes = source.fetch_daily_all()
        quote = quotes.get(ticker.ticker)
    except FetchError as exc:
        quote = None
        result.missing.append("當日行情取用失敗：{}".format(exc))

    if quote is None:
        result.missing.append("資料缺漏：{} 當日無成交資訊（可能停牌或已下市）".format(ticker.ticker))
    else:
        result.price = quote.close
        result.price_date = quote.date
        if quote.close is None:
            result.missing.append("資料缺漏：收盤價為空")

    try:
        ratios = source.fetch_ratios_all()
        ratio = ratios.get(ticker.ticker)
    except FetchError as exc:
        ratio = None
        result.missing.append("當日本益比／股價淨值比取用失敗：{}".format(exc))

    if ratio is not None:
        result.per = ratio.per
        result.pbr = ratio.pbr
        result.dividend_yield = ratio.dividend_yield
        result.ratio_date = ratio.date
        if ratio.per is None:
            result.missing.append("資料缺漏：官方本益比為空（通常代表近四季 EPS 為負）")
        if ratio.pbr is None:
            result.missing.append("資料缺漏：官方股價淨值比為空")
    else:
        result.missing.append("資料缺漏：{} 不在當日比值清單中".format(ticker.ticker))

    history = source.fetch_ratio_history(ticker.ticker)
    unavailable = tpex.RATIO_HISTORY_UNAVAILABLE if ticker.market == "TPEX" else ""
    if unavailable:
        result.missing.append("資料缺漏：" + unavailable)

    result.valuations.append(m1_pe.evaluate(
        ticker=ticker.ticker,
        industry_code=ticker.industry_code,
        ratio_history=history,
        current_per=result.per,
        current_price=result.price,
        unavailable_reason=unavailable,
    ))
    result.valuations.append(m2_pb.evaluate(
        ticker=ticker.ticker,
        ratio_history=history,
        current_pbr=result.pbr,
        current_price=result.price,
        unavailable_reason=unavailable,
    ))

    return result
