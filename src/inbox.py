"""inbox/ 的掃描、metadata 解析與歸檔（CLAUDE.md §2.1）。"""
from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path
from typing import List, Optional

from . import config

TEXT_SUFFIXES = {".txt", ".md"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}


class InboxItem:
    __slots__ = ("path", "text", "source", "date", "stance")

    def __init__(self, path: Path, text: str, source: str, date: Optional[dt.date], stance: str):
        self.path = path
        self.text = text
        self.source = source          # ::source= 或檔名
        self.date = date              # ::date=
        self.stance = stance          # ::stance=


def _parse_metadata_line(line: str):
    """解析 "::source=粉專名稱 ::date=2026-08-10 ::stance=看多"。

    只認以 :: 開頭的行；缺省欄位留空，由模型推斷（CLAUDE.md §2.1）。
    """
    fields = {}
    for token in line.split("::"):
        token = token.strip()
        if not token or "=" not in token:
            continue
        key, value = token.split("=", 1)
        fields[key.strip().lower()] = value.strip()
    return fields


def _parse_date(raw: str) -> Optional[dt.date]:
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return dt.datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


def scan() -> List[InboxItem]:
    """讀取 inbox/ 下的文字檔。archive/ 與 README.md 跳過。"""
    items: List[InboxItem] = []
    if not config.INBOX_DIR.exists():
        return items

    for path in sorted(config.INBOX_DIR.rglob("*")):
        if not path.is_file():
            continue
        if config.INBOX_ARCHIVE_DIR in path.parents:
            continue
        if path.name.lower() == "readme.md":
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue

        raw = path.read_text(encoding="utf-8", errors="replace").strip()
        if not raw:
            continue

        lines = raw.splitlines()
        meta = {}
        if lines and lines[0].lstrip().startswith("::"):
            meta = _parse_metadata_line(lines[0])
            lines = lines[1:]

        items.append(InboxItem(
            path=path,
            text="\n".join(lines).strip(),
            source=meta.get("source") or path.stem,
            date=_parse_date(meta.get("date", "")),
            stance=meta.get("stance", ""),
        ))

    return items


def pending_images() -> List[Path]:
    """尚未處理的截圖。目前不做 OCR，只回報數量讓 HTML 標示（鐵則 7）。"""
    if not config.INBOX_DIR.exists():
        return []
    return [
        p for p in sorted(config.INBOX_DIR.rglob("*"))
        if p.is_file()
        and p.suffix.lower() in IMAGE_SUFFIXES
        and config.INBOX_ARCHIVE_DIR not in p.parents
    ]


def archive(items: List[InboxItem]) -> None:
    """處理完的檔案移到 inbox/archive/YYYYMMDD/。"""
    if not items:
        return
    target = config.INBOX_ARCHIVE_DIR / config.today().strftime("%Y%m%d")
    target.mkdir(parents=True, exist_ok=True)
    for item in items:
        destination = target / item.path.name
        counter = 1
        while destination.exists():
            destination = target / "{}_{}{}".format(item.path.stem, counter, item.path.suffix)
            counter += 1
        shutil.move(str(item.path), str(destination))
