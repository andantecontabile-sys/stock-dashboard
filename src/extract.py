"""標的抽取層（CLAUDE.md §3）。

用 LLM 做命名實體辨識，不用 regex —— 中文個股簡稱（華新科／華新、聯電／聯發科）
用字串比對必定出錯，這是規格明文禁止的作法。

沒有 API 金鑰時的降級策略：不猜。改成只接受貼文開頭 metadata 明寫的 ::ticker=，
其餘一律進 unresolved.json 並在 HTML 上標示原因。寧可少抽，不可抽錯。
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional, Sequence

from . import config
from .inbox import InboxItem
from .tickers import Ticker, resolve

MODEL = "claude-opus-4-8"

MENTION_SCHEMA = {
    "type": "object",
    "properties": {
        "mentions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "股票代號，如 2330。不確定則留空字串"},
                    "name": {"type": "string", "description": "個股簡稱，如 台積電"},
                    "market": {"type": "string", "enum": ["TWSE", "TPEX", "US", "UNKNOWN"]},
                    "stance": {"type": "string", "enum": ["bullish", "bearish", "neutral", "unclear"]},
                    "claim": {"type": "string", "description": "原文主張的一句話摘要，用原文語言"},
                    "confidence": {"type": "number", "description": "0 到 1"},
                },
                "required": ["ticker", "name", "market", "stance", "claim", "confidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["mentions"],
    "additionalProperties": False,
}

SYSTEM = """你是台股與美股的命名實體辨識器。從貼文中抽出被討論的「個股」。

規則：
- 只抽個股，不抽產業、族群、指數、ETF（例如「被動元件族群」不是標的，「國巨」才是）。
- 中文簡稱容易撞名，務必依上下文判斷：華新（1605）與華新科（2492）是兩家不同公司；
  聯電（2303）與聯發科（2454）也是。無法確定是哪一家時，ticker 留空字串、
  confidence 給 0.3 以下，讓下游走人工確認，不要猜一個代號。
- stance 是「該貼文作者對這檔標的的立場」，不是你的看法。
- claim 用原文語言寫一句話，不要加入原文沒有的推論。
- 找不到任何個股時回傳空陣列。"""


class Mention:
    __slots__ = ("ticker", "name", "market", "source", "stance", "claim", "confidence", "resolved")

    def __init__(self, ticker, name, market, source, stance, claim, confidence):
        self.ticker = ticker
        self.name = name
        self.market = market
        self.source = source
        self.stance = stance
        self.claim = claim
        self.confidence = confidence
        self.resolved: Optional[Ticker] = None

    def to_dict(self) -> Dict:
        return {
            "ticker": self.ticker,
            "name": self.name,
            "market": self.market,
            "source": self.source,
            "stance": self.stance,
            "claim": self.claim,
            "confidence": self.confidence,
        }


class ExtractionResult:
    def __init__(self, mentions: List[Mention], unresolved: List[Dict], degraded_reason: str = ""):
        self.mentions = mentions            # 已對上 ticker_master 的
        self.unresolved = unresolved        # 對不上的，必須顯示在 HTML（CLAUDE.md §3）
        self.degraded_reason = degraded_reason


def _extract_with_llm(items: Sequence[InboxItem], api_key: str) -> List[Mention]:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    mentions: List[Mention] = []

    for item in items:
        header = "來源：{}".format(item.source)
        if item.date:
            header += "　日期：{}".format(item.date.isoformat())
        if item.stance:
            header += "　作者立場（人工標註）：{}".format(item.stance)

        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "medium",
                "format": {"type": "json_schema", "schema": MENTION_SCHEMA},
            },
            messages=[{"role": "user", "content": "{}\n\n---\n{}".format(header, item.text)}],
        )

        if response.stop_reason == "refusal":
            continue

        text = next((b.text for b in response.content if b.type == "text"), "")
        if not text:
            continue

        payload = json.loads(text)
        for raw in payload.get("mentions", []):
            mentions.append(Mention(
                ticker=(raw.get("ticker") or "").strip(),
                name=(raw.get("name") or "").strip(),
                market=raw.get("market") or "UNKNOWN",
                source="{} {}".format(item.source, item.date.isoformat() if item.date else "").strip(),
                stance=raw.get("stance") or "unclear",
                claim=raw.get("claim") or "",
                confidence=float(raw.get("confidence") or 0.0),
            ))

    return mentions


def _extract_without_llm(items: Sequence[InboxItem]) -> List[Mention]:
    """降級路徑：不做任何文字比對，一律回空。

    刻意不實作 regex 版本。抽錯標的會讓整份估值報告指向錯誤的公司，
    比抽不到更糟 —— 這正是 CLAUDE.md §3 禁止 regex 的理由。
    """
    return []


def run(items: Sequence[InboxItem], master: Dict[str, Ticker]) -> ExtractionResult:
    if not items:
        return ExtractionResult([], [])

    api_key = config.anthropic_api_key()
    degraded_reason = ""

    if api_key:
        raw_mentions = _extract_with_llm(items, api_key)
    else:
        raw_mentions = _extract_without_llm(items)
        degraded_reason = (
            "未設定 ANTHROPIC_API_KEY，標的抽取停用。"
            "CLAUDE.md §3 禁止用 regex 比對中文個股簡稱，因此不做退化猜測 —— "
            "請在專案根目錄建立 .env 並填入 ANTHROPIC_API_KEY=，或直接分析指定標的。"
        )

    mentions: List[Mention] = []
    unresolved: List[Dict] = []

    for mention in raw_mentions:
        ticker = resolve(master, mention.ticker, mention.name)
        if ticker is None:
            record = mention.to_dict()
            record["reason"] = "代號與簡稱皆無法在 ticker_master.csv 中對應"
            unresolved.append(record)
            continue
        mention.resolved = ticker
        mention.ticker = ticker.ticker
        mention.market = ticker.market
        mentions.append(mention)

    return ExtractionResult(mentions, unresolved, degraded_reason)
