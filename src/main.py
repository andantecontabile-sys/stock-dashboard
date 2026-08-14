"""進入點：讀 inbox → 抽標的 → 抓數據 → 算估值 → 產 HTML → 開瀏覽器。"""
from __future__ import annotations

import argparse
import sys
import time
import webbrowser
from typing import Dict, List

from . import analyze, config, extract, inbox, report, tickers
from .sources import feeds


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="每日選股儀表板",
        description="讀 inbox/ 的貼文抽出標的，抓官方數據算估值區間，產出單一 HTML。",
    )
    parser.add_argument("--ticker", action="append", default=[], metavar="代號",
                        help="直接指定標的（可重複），略過 inbox 抽取。例：--ticker 2330")
    parser.add_argument("--no-open", action="store_true", help="產出後不要自動開瀏覽器")
    parser.add_argument("--no-archive", action="store_true",
                        help="不要把 inbox/ 的檔案移到 archive/（除錯用）")
    parser.add_argument("--rebuild-tickers", action="store_true",
                        help="強制重建 data/ticker_master.csv")
    parser.add_argument("--no-feeds", action="store_true",
                        help="不要抓自動來源（股癌 Podcast、兩個 YouTube 頻道）")
    parser.add_argument("--fragment", metavar="路徑",
                        help="另外輸出不含 doctype/html/body 的片段，供 Artifact 等環境嵌入")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    config.ensure_dirs()
    started = time.monotonic()

    print("讀取上市上櫃公司清單…")
    master = tickers.load(force_rebuild=args.rebuild_tickers)
    print("  {} 檔在案。".format(len(master)))

    global_gaps: List[str] = []
    mentions_by_ticker: Dict[str, List] = {}
    targets: List = []

    feed_result = feeds.FeedResult()
    if not args.no_feeds:
        print("抓取自動來源…")
        feed_result = feeds.fetch_all()
        for status in feed_result.status:
            print("  {}：{} 則{}".format(
                status["name"], status["count"],
                "" if status.get("usable_for_extraction") else "（僅顯示，不供抽取）"))
        global_gaps.extend(feed_result.gaps)

    if args.ticker:
        for code in args.ticker:
            found = tickers.resolve(master, code)
            if found is None:
                global_gaps.append("指定的標的 {} 不在 ticker_master.csv 中，已略過".format(code))
                continue
            targets.append(found)
        unresolved: List[dict] = []
    else:
        items = inbox.scan()
        print("inbox 有 {} 則貼文，自動來源 {} 則。".format(len(items), len(feed_result.entries)))

        pending = inbox.pending_images()
        if pending:
            global_gaps.append(
                "資料缺漏：inbox/ 有 {} 張截圖未處理（OCR／視覺模型為後續範圍）：{}".format(
                    len(pending), "、".join(p.name for p in pending)))

        # inbox 貼文與自動來源走同一條抽取路徑（FeedEntry 與 InboxItem 介面相容）
        result = extract.run(list(items) + list(feed_result.entries), master)
        unresolved = result.unresolved
        if result.degraded_reason:
            global_gaps.append(result.degraded_reason)

        for mention in result.mentions:
            mentions_by_ticker.setdefault(mention.ticker, []).append(mention)
        seen = set()
        for mention in result.mentions:
            if mention.ticker not in seen:
                seen.add(mention.ticker)
                targets.append(mention.resolved)

        if not targets:
            print("沒有抽到任何標的。可用 --ticker 2330 直接指定，或把貼文放進 inbox/。")

        if not args.no_archive:
            inbox.archive(items)

    analyses = []
    for index, ticker in enumerate(targets, 1):
        print("[{}/{}] 分析 {} {}…".format(index, len(targets), ticker.ticker, ticker.name))
        item = analyze.analyze(ticker)
        item.mentions = mentions_by_ticker.get(ticker.ticker, [])
        analyses.append(item)

    path = report.write(analyses, unresolved, global_gaps, feed_result.status)

    if args.fragment:
        from pathlib import Path
        fragment_path = Path(args.fragment)
        fragment_path.parent.mkdir(parents=True, exist_ok=True)
        fragment_path.write_text(
            report.render_fragment(analyses, unresolved, global_gaps, feed_result.status),
            encoding="utf-8")
        print("片段：{}".format(fragment_path))

    elapsed = time.monotonic() - started
    print("\n完成，耗時 {:.0f} 秒。".format(elapsed))
    print("報告：{}".format(path))

    if not args.no_open:
        webbrowser.open(path.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())
