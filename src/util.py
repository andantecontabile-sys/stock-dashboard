"""數值解析與分位數計算。

證交所把數字當字串送，且缺值有五種寫法（""、"--"、"-"、"N/A"、"0.00" 之外的全形空白），
一律轉成 None，由呼叫端標示「資料缺漏」（鐵則 7）。
"""
from __future__ import annotations

from typing import List, Optional, Sequence

_MISSING_TOKENS = {"", "--", "-", "n/a", "na", "null", "nan", "－", "—"}


def parse_number(raw) -> Optional[float]:
    """把證交所的字串數字轉 float。無法解析一律回 None，絕不回 0。"""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
        return value if value == value else None  # 濾掉 NaN

    text = str(raw).strip().replace(",", "").replace("＋", "+").replace("　", "")
    if text.lower() in _MISSING_TOKENS:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def percentile(sorted_values: Sequence[float], q: float) -> float:
    """線性內插分位數，與 numpy.percentile 的預設行為一致。

    sorted_values 必須已排序且非空，由呼叫端保證。
    """
    if not sorted_values:
        raise ValueError("percentile() 需要非空序列")
    if len(sorted_values) == 1:
        return float(sorted_values[0])

    position = (len(sorted_values) - 1) * (q / 100.0)
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    weight = position - lower_index
    lower = float(sorted_values[lower_index])
    upper = float(sorted_values[upper_index])
    return lower + (upper - lower) * weight


def percentile_rank(sorted_values: Sequence[float], value: float) -> float:
    """value 在序列中的百分位（0–100），用「小於等於的比例」定義。"""
    if not sorted_values:
        raise ValueError("percentile_rank() 需要非空序列")
    count = sum(1 for v in sorted_values if v <= value)
    return 100.0 * count / len(sorted_values)


def quantiles(values: Sequence[float], points: Sequence[int]) -> List[float]:
    ordered = sorted(float(v) for v in values)
    return [percentile(ordered, q) for q in points]
