"""估值模型的共同輸出型別。

CLAUDE.md §5：每個模型獨立輸出 {low, mid, high, applicable, warnings[]}，
applicable=False 時仍要顯示，並說明為何不適用。
"""
from __future__ import annotations

from typing import Dict, List, Optional


class ValuationResult:
    def __init__(
        self,
        model: str,
        title: str,
        low: Optional[float] = None,
        mid: Optional[float] = None,
        high: Optional[float] = None,
        applicable: bool = False,
        warnings: Optional[List[str]] = None,
        reason: str = "",
        detail: Optional[Dict] = None,
    ):
        self.model = model
        self.title = title
        self.low = low
        self.mid = mid
        self.high = high
        self.applicable = applicable
        self.warnings = warnings or []
        self.reason = reason           # applicable=False 時的原因，會直接印在 HTML 上
        self.detail = detail or {}     # 分位表、樣本數、資料期間等

    def to_dict(self) -> Dict:
        return {
            "model": self.model,
            "title": self.title,
            "low": self.low,
            "mid": self.mid,
            "high": self.high,
            "applicable": self.applicable,
            "warnings": self.warnings,
            "reason": self.reason,
            "detail": self.detail,
        }
