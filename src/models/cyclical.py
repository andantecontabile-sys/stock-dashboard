"""景氣循環股判定。

CLAUDE.md §5 M1 要求：被動元件、面板、記憶體、航運、鋼鐵、塑化這六類，
必須自動加註「循環股於獲利高峰時 P/E 最低，本模型可能給出反向訊號」。

判定分兩層：
  1. 產業別代號 —— 航運、鋼鐵、塑膠、化學工業整個產業都算，用官方代號即可涵蓋。
  2. 個股名單 —— 被動元件、面板、記憶體散在「半導體」「電子零組件」「光電」三個
     產業代號底下，代號本身分不出來，只能列名單。名單不完整不是 bug，
     但漏標會讓警語失效，新增標的時要一併補。
"""
from __future__ import annotations

from typing import Optional, Set

CYCLICAL_WARNING = (
    "循環股於獲利高峰時 P/E 最低、獲利谷底時 P/E 最高，本模型可能給出反向訊號"
)

# TWSE / TPEx 產業別代號
CYCLICAL_INDUSTRY_CODES = {
    "03": "塑膠",
    "10": "鋼鐵",
    "15": "航運",
    "21": "化學工業",
}

# 代號分不出來、只能列名單的三類
PASSIVE_COMPONENTS: Set[str] = {
    "2327",  # 國巨
    "2492",  # 華新科
    "2375",  # 凱美
    "2456",  # 奇力新
    "3026",  # 禾伸堂
}

PANEL: Set[str] = {
    "2409",  # 友達
    "3481",  # 群創
    "6116",  # 彩晶
    "8069",  # 元太
}

MEMORY: Set[str] = {
    "2344",  # 華邦電
    "2408",  # 南亞科
    "3260",  # 威剛
    "4967",  # 十銓
    "5289",  # 宜鼎
    "8299",  # 群聯
}

_NAMED = {
    "被動元件": PASSIVE_COMPONENTS,
    "面板": PANEL,
    "記憶體": MEMORY,
}


def classify(ticker: str, industry_code: Optional[str]) -> Optional[str]:
    """回傳循環股類別名稱，非循環股回 None。"""
    for label, members in _NAMED.items():
        if ticker in members:
            return label

    code = (industry_code or "").strip()
    if code and code in CYCLICAL_INDUSTRY_CODES:
        return CYCLICAL_INDUSTRY_CODES[code]
    return None
