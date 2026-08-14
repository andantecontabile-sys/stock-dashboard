"""M2 · P/B 河流圖（CLAUDE.md §5）。

淨值按季更新、向前填補至下一季公布日 —— 這件事證交所的 BWIBBU 端點已經做掉了：
它每個交易日都給股價淨值比，分母就是當時最新一期已公布的每股淨值。
所以這裡不需要自己做填補，只要把官方逐日序列取分位即可。

一次性資產減損的加註目前無法自動化：偵測它需要逐季財報附註，屬 Sprint 2 的 XBRL 範圍。
在那之前，本模型固定附上「未檢查一次性沖銷」的提醒，而不是假裝檢查過了。
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from . import river
from .base import ValuationResult

MODEL = "M2"
TITLE = "股價淨值比"

IMPAIRMENT_CAVEAT = (
    "未檢查一次性資產減損／沖銷：偵測需逐季財報附註（Sprint 2 的 XBRL 範圍）。"
    "若當期有大額沖銷，每股淨值會失真，分位僅供參考"
)


def evaluate(
    ticker: str,
    ratio_history: Sequence,       # Sequence[RatioPoint]
    current_pbr: Optional[float],
    current_price: Optional[float],
    unavailable_reason: str = "",
) -> ValuationResult:
    warnings: List[str] = [IMPAIRMENT_CAVEAT]

    series: List[Tuple] = [(p.date, p.pbr) for p in ratio_history if p.pbr is not None]

    return river.build(
        model=MODEL,
        title="P/B 河流圖",
        series=series,
        current_ratio=current_pbr,
        current_price=current_price,
        per_share_label="每股淨值",
        ratio_label=TITLE,
        warnings=warnings,
        unavailable_reason=unavailable_reason,
    )
