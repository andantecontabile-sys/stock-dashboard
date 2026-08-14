"""M1 · P/E 河流圖（CLAUDE.md §5）。"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from . import cyclical, river
from .base import ValuationResult

MODEL = "M1"
TITLE = "本益比"


def evaluate(
    ticker: str,
    industry_code: Optional[str],
    ratio_history: Sequence,       # Sequence[RatioPoint]
    current_per: Optional[float],
    current_price: Optional[float],
    unavailable_reason: str = "",
) -> ValuationResult:
    warnings: List[str] = []

    cyclical_label = cyclical.classify(ticker, industry_code)
    if cyclical_label:
        warnings.append("屬{}（景氣循環股）：{}".format(cyclical_label, cyclical.CYCLICAL_WARNING))

    series: List[Tuple] = [(p.date, p.per) for p in ratio_history if p.per is not None]

    return river.build(
        model=MODEL,
        title="P/E 河流圖",
        series=series,
        current_ratio=current_per,
        current_price=current_price,
        per_share_label="TTM EPS",
        ratio_label=TITLE,
        warnings=warnings,
        unavailable_reason=unavailable_reason,
    )
