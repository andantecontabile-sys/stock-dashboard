"""自動來源層：公開 RSS / Atom feed。

為什麼不抓 Facebook：CLAUDE.md 鐵則 1 明文禁止自動化存取 FB（違反平台條款、有帳號風險）。
這裡改走各作者的公開出口，內容大致同源，且完全不需要人工介入 —— 老爺按一次執行就好。

各來源的實際可用度（2026-08-14 實測，原始回應在 debug/probe/）：

  股癌 Gooaye（SoundOn podcast）
    feed 活著，687 集。但標題只有「EP687 | 🐧」，description 幾乎全是業配
    （實測最新一集通篇中秋禮盒廣告，零個股票代號）。選股內容在音檔裡，
    要取得必須做語音轉文字 —— 見 TRANSCRIPTION_NOTE。

  游庭皓的財經皓角（YouTube）
    每日盤前直播，標題含當日總經主題，可直接用。

  JC財經觀點／財女珍妮（YouTube）
    標題直接帶股票代號（例：「訂單爆發，股價卻不漲？ #NBIS #CSCO #COHR #CBRS」），
    是目前訊號密度最高的自動來源。
"""
from __future__ import annotations

import datetime as dt
import html
import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import List, Optional

from .. import config
from ..http import FetchError

ATOM = "http://www.w3.org/2005/Atom"
MRSS = "http://search.yahoo.com/mrss/"

TRANSCRIPTION_NOTE = (
    "股癌的選股內容在音檔中（每集約 50 分鐘），RSS 的節目說明幾乎全是業配文案，"
    "無法據以抽出標的。要全自動取得需加上語音轉文字，尚未實作。"
)


class Feed:
    __slots__ = ("key", "name", "url", "kind", "note")

    def __init__(self, key: str, name: str, url: str, kind: str, note: str = ""):
        self.key = key
        self.name = name
        self.url = url
        self.kind = kind        # "podcast" | "youtube"
        self.note = note


FEEDS = [
    Feed(
        key="gooaye",
        name="股癌 Gooaye",
        url="https://feeds.soundon.fm/podcasts/954689a5-3096-43a4-a80b-7810b219cef3.xml",
        kind="podcast",
        note=TRANSCRIPTION_NOTE,
    ),
    Feed(
        key="yutinghao",
        name="游庭皓的財經皓角",
        url="https://www.youtube.com/feeds/videos.xml?channel_id=UC0lbAQVpenvfA2QqzsRtL_g",
        kind="youtube",
    ),
    Feed(
        key="jc",
        name="JC財經觀點（財女珍妮）",
        url="https://www.youtube.com/feeds/videos.xml?channel_id=UCdwPn2TO60Ec8QDIFRx50lQ",
        kind="youtube",
    ),
]

# 只看最近這麼多天的內容，避免把半年前的舊主張餵進今天的報告
LOOKBACK_DAYS = 10
MAX_ITEMS_PER_FEED = 8


class FeedEntry:
    __slots__ = ("feed_key", "feed_name", "title", "summary", "published", "link")

    def __init__(self, feed_key, feed_name, title, summary, published, link):
        self.feed_key = feed_key
        self.feed_name = feed_name
        self.title = title
        self.summary = summary
        self.published: Optional[dt.date] = published
        self.link = link

    @property
    def text(self) -> str:
        """餵給抽取器的文字。標題放前面 —— JC 的代號就寫在標題裡。"""
        return "{}\n\n{}".format(self.title, self.summary).strip()

    # 以下三個屬性讓 FeedEntry 能直接餵進 extract.run()，
    # 與 inbox.InboxItem 共用同一條抽取路徑。
    @property
    def source(self) -> str:
        return self.feed_name

    @property
    def date(self) -> Optional[dt.date]:
        return self.published

    @property
    def stance(self) -> str:
        return ""       # feed 沒有人工標註的立場，交給模型判斷


def _strip_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw or "")
    return re.sub(r"[ \t]{2,}", " ", html.unescape(text)).strip()


def _parse_date(raw: str) -> Optional[dt.date]:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:                                    # RSS：Wed, 12 Aug 2026 07:27:46 GMT
        return parsedate_to_datetime(raw).date()
    except (TypeError, ValueError):
        pass
    try:                                    # Atom：2026-08-14T00:00:00+00:00
        return dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _parse_rss(root, feed: Feed) -> List[FeedEntry]:
    channel = root.find("channel")
    if channel is None:
        return []
    entries = []
    for item in channel.findall("item"):
        entries.append(FeedEntry(
            feed_key=feed.key,
            feed_name=feed.name,
            title=(item.findtext("title") or "").strip(),
            summary=_strip_html(item.findtext("description") or ""),
            published=_parse_date(item.findtext("pubDate") or ""),
            link=(item.findtext("link") or "").strip(),
        ))
    return entries


def _parse_atom(root, feed: Feed) -> List[FeedEntry]:
    entries = []
    for entry in root.findall("{%s}entry" % ATOM):
        group = entry.find("{%s}group" % MRSS)
        summary = ""
        if group is not None:
            summary = _strip_html(group.findtext("{%s}description" % MRSS) or "")
        link_el = entry.find("{%s}link" % ATOM)
        entries.append(FeedEntry(
            feed_key=feed.key,
            feed_name=feed.name,
            title=(entry.findtext("{%s}title" % ATOM) or "").strip(),
            summary=summary,
            published=_parse_date(entry.findtext("{%s}published" % ATOM) or ""),
            link=link_el.get("href", "") if link_el is not None else "",
        ))
    return entries


def fetch(feed: Feed, lookback_days: int = LOOKBACK_DAYS) -> List[FeedEntry]:
    """抓單一 feed。失敗時丟 FetchError，由呼叫端轉成資料缺漏（鐵則 7）。"""
    import requests

    try:
        response = requests.get(
            feed.url, timeout=40,
            headers={"User-Agent": config.USER_AGENT},
        )
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except requests.RequestException as exc:
        raise FetchError("{} feed 取用失敗：{}".format(feed.name, exc)) from exc
    except ET.ParseError as exc:
        raise FetchError("{} feed 不是合法 XML：{}".format(feed.name, exc)) from exc

    entries = _parse_rss(root, feed) if root.tag == "rss" else _parse_atom(root, feed)

    cutoff = config.today() - dt.timedelta(days=lookback_days)
    recent = [e for e in entries if e.published and e.published >= cutoff]
    recent.sort(key=lambda e: e.published, reverse=True)
    return recent[:MAX_ITEMS_PER_FEED]


class FeedResult:
    def __init__(self):
        self.entries: List[FeedEntry] = []
        self.status: List[dict] = []     # 每個 feed 的抓取結果，會顯示在 HTML 上
        self.gaps: List[str] = []


def fetch_all(lookback_days: int = LOOKBACK_DAYS) -> FeedResult:
    result = FeedResult()

    for feed in FEEDS:
        try:
            entries = fetch(feed, lookback_days)
        except FetchError as exc:
            result.status.append({
                "name": feed.name, "count": 0, "latest": None,
                "ok": False, "note": str(exc),
            })
            result.gaps.append("資料缺漏：{}".format(exc))
            continue

        # feed.note 不為空 = 這個來源抓得到、但內容不足以抽出標的。
        # 仍然列在來源動態上（讓老爺知道它有在跑），但不餵進抽取器，
        # 並把原因寫進資料缺漏 —— 不能讓老爺以為它在貢獻選股訊號。
        usable = not feed.note
        if usable:
            result.entries.extend(entries)
        else:
            result.gaps.append("{}：{}".format(feed.name, feed.note))

        result.status.append({
            "name": feed.name,
            "count": len(entries),
            "latest": entries[0].published.isoformat() if entries else None,
            "ok": True,
            "note": feed.note,
            "usable_for_extraction": usable,
            "items": [{"title": e.title, "date": e.published.isoformat() if e.published else "",
                       "link": e.link} for e in entries],
        })

    return result
