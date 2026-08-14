"""河流圖共用計算（M1 與 M2 的骨幹）。

作法：對近 N 年的官方逐日比值取分位，再用「現價 ÷ 現值比值」回推每股基準
（P/E 對應 TTM EPS、P/B 對應每股淨值），把分位比值乘回去得到價格帶。

為什麼不自己拿還原股價去除以 EPS：
證交所的逐日比值本身就是「該日收盤價 ÷ 該日當時已知的每股數值」。
除權息當天分子分母同步變動，序列前後可比。若改用還原股價除以「今天」的 EPS，
等於把今天的獲利狀況套到五年前的價格上，高息股會整段偏移 —— 那正是鐵則 4 要避免的錯。
"""
from __future__ import annotations

import datetime as dt
from typing import Callable, List, Optional, Sequence, Tuple

from .. import config
from ..util import percentile, percentile_rank
from .base import ValuationResult

MIN_SAMPLES = 250  # 少於約一年的交易日，分位數沒有意義


def build(
    model: str,
    title: str,
    series: Sequence[Tuple[dt.date, float]],
    current_ratio: Optional[float],
    current_price: Optional[float],
    per_share_label: str,
    ratio_label: str = "",
    warnings: Optional[List[str]] = None,
    unavailable_reason: str = "",
) -> ValuationResult:
    """title 是圖表標題（「P/E 河流圖」）；ratio_label 是比值本身的名稱（「本益比」）。

    兩者不可混用 —— 內文寫「目前 P/E 河流圖 32.74」是讀不通的。
    """
    warnings = list(warnings or [])
    ratio_label = ratio_label or title

    if unavailable_reason:
        return ValuationResult(model, title, applicable=False,
                               reason=unavailable_reason, warnings=warnings)

    cutoff = config.today() - dt.timedelta(days=int(365.25 * config.RIVER_YEARS))
    usable = [(d, v) for d, v in series if d >= cutoff and v is not None and v > 0]

    if len(usable) < MIN_SAMPLES:
        return ValuationResult(
            model, title, applicable=False, warnings=warnings,
            reason="資料缺漏：近 {} 年僅取得 {} 個有效樣本（需 {} 個以上）".format(
                config.RIVER_YEARS, len(usable), MIN_SAMPLES),
            detail={"samples": len(usable)},
        )

    if current_ratio is None or current_ratio <= 0:
        return ValuationResult(
            model, title, applicable=False, warnings=warnings,
            reason="資料缺漏：目前{}為負或未提供（虧損股在證交所端點是空字串）".format(ratio_label),
            detail={"samples": len(usable)},
        )

    if current_price is None or current_price <= 0:
        return ValuationResult(model, title, applicable=False, warnings=warnings,
                               reason="資料缺漏：取不到現價", detail={"samples": len(usable)})

    values = sorted(v for _, v in usable)
    bands = {q: percentile(values, q) for q in config.PERCENTILE_POINTS}

    # 現價 ÷ 現值比值 = 每股基準（EPS 或每股淨值）
    per_share = current_price / current_ratio
    price_at = {q: bands[q] * per_share for q in config.PERCENTILE_POINTS}

    rank = percentile_rank(values, current_ratio)

    return ValuationResult(
        model, title,
        low=price_at[25], mid=price_at[50], high=price_at[75],
        applicable=True,
        warnings=warnings,
        detail={
            "samples": len(usable),
            "period_start": usable[0][0].isoformat(),
            "period_end": usable[-1][0].isoformat(),
            "current_ratio": current_ratio,
            "current_percentile": rank,
            "ratio_bands": {str(q): bands[q] for q in config.PERCENTILE_POINTS},
            "price_bands": {str(q): price_at[q] for q in config.PERCENTILE_POINTS},
            "per_share_label": per_share_label,
            "per_share_value": per_share,
            "ratio_label": ratio_label,
        },
    )
