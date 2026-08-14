"""輸出層：單一自包含 HTML（CLAUDE.md §7）。

與規格的一處刻意差異：帶狀圖用內嵌 SVG 畫，不走 Chart.js CDN。
規格同時要求「單一自包含」與「CDN + 離線退化為表格」，兩者互斥；
內嵌 SVG 兩個目標都滿足，離線一樣看得到圖，且不必再寫一份退化路徑。
"""
from __future__ import annotations

import datetime as dt
import html
from typing import List, Optional, Sequence

from . import config
from .analyze import SecurityAnalysis

CHIP_DISCLAIMER = (
    "籌碼層（三大法人、量能、MFI/OBV、分點）為 Sprint 3 範圍，本版尚未實作，"
    "因此不輸出任何觀察等級。"
)

METHOD_NOTE = (
    "估值為區間，非目標價。分位取自證交所官方逐日本益比／股價淨值比序列 —— "
    "該序列的分子分母在除權息當天同步變動，本身即為可比，"
    "故未另行以還原股價重算（見 CLAUDE.md 鐵則 4 的用意）。"
)


def _e(value) -> str:
    return html.escape(str(value)) if value is not None else ""


def _num(value: Optional[float], digits: int = 2) -> str:
    if value is None:
        return '<span class="missing">資料缺漏</span>'
    return "{:,.{}f}".format(value, digits)


def _date(value) -> str:
    return value.isoformat() if isinstance(value, dt.date) else "—"


def _band_svg(detail: dict, price: Optional[float]) -> str:
    """把 10/25/50/75/90 分位價格畫成帶狀圖，並標出現價位置。"""
    bands = detail.get("price_bands") or {}
    try:
        p10, p25, p50, p75, p90 = (float(bands[k]) for k in ("10", "25", "50", "75", "90"))
    except (KeyError, TypeError, ValueError):
        return ""

    lo, hi = p10, p90
    if price is not None:
        lo, hi = min(lo, price), max(hi, price)
    span = hi - lo
    if span <= 0:
        return ""

    # viewBox 刻意做窄（420 而非 640）：SVG 以 width:100% 縮放，
    # viewBox 越寬、在 375px 的 iPhone 上字就被縮得越小。
    # 搭配 .band 的 max-width 讓桌機不會反過來放大過頭。
    width, height = 420, 78
    pad = 30

    def x(value: float) -> float:
        return pad + (value - lo) / span * (width - 2 * pad)

    def label_x(value: float) -> float:
        """把文字錨點夾在畫布內，避免最左／最右的標籤被裁掉。"""
        return min(max(x(value), 22.0), width - 22.0)

    parts = ['<svg viewBox="0 0 {} {}" class="band" role="img" '
             'aria-label="估值分位帶狀圖">'.format(width, height)]
    parts.append('<rect x="{:.1f}" y="28" width="{:.1f}" height="16" rx="2" '
                 'class="b-outer"/>'.format(x(p10), max(x(p90) - x(p10), 1)))
    parts.append('<rect x="{:.1f}" y="28" width="{:.1f}" height="16" rx="2" '
                 'class="b-inner"/>'.format(x(p25), max(x(p75) - x(p25), 1)))
    parts.append('<line x1="{0:.1f}" y1="26" x2="{0:.1f}" y2="46" class="b-mid"/>'.format(x(p50)))

    for value, label in ((p10, "10%"), (p50, "50%"), (p90, "90%")):
        parts.append('<text x="{:.1f}" y="58" class="b-lab">{}</text>'.format(
            label_x(value), label))
        parts.append('<text x="{:.1f}" y="70" class="b-val">{:,.0f}</text>'.format(
            label_x(value), value))

    if price is not None:
        parts.append('<line x1="{0:.1f}" y1="18" x2="{0:.1f}" y2="52" '
                     'class="b-now"/>'.format(x(price)))
        parts.append('<text x="{:.1f}" y="13" class="b-now-lab">現價 {:,.0f}</text>'.format(
            label_x(price), price))

    parts.append("</svg>")
    return "".join(parts)


def _valuation_block(result, price: Optional[float]) -> str:
    rows = ['<div class="model">']
    rows.append('<div class="model-head"><b>{} · {}</b>{}</div>'.format(
        _e(result.model), _e(result.title),
        '' if result.applicable else '<span class="tag-na">不適用</span>'))

    if not result.applicable:
        rows.append('<p class="reason">{}</p>'.format(_e(result.reason)))
    else:
        detail = result.detail
        rows.append(_band_svg(detail, price))
        rows.append(
            '<table class="kv"><tr><th>估值區間（P25–P75）</th><td>{} – {}</td></tr>'
            '<tr><th>中位（P50）</th><td>{}</td></tr>'
            '<tr><th>目前{}</th><td>{}（位於近 {} 年第 {} 百分位）</td></tr>'
            '<tr><th>推算{}</th><td>{}</td></tr>'
            '<tr><th>樣本</th><td>{} 個交易日（{} ~ {}）</td></tr></table>'.format(
                _num(result.low), _num(result.high), _num(result.mid),
                _e(detail.get("ratio_label")), _num(detail.get("current_ratio")),
                config.RIVER_YEARS, _num(detail.get("current_percentile"), 1),
                _e(detail.get("per_share_label")), _num(detail.get("per_share_value")),
                _e(detail.get("samples")), _e(detail.get("period_start")),
                _e(detail.get("period_end"))))

    for warning in result.warnings:
        rows.append('<p class="warn">⚠ {}</p>'.format(_e(warning)))

    rows.append("</div>")
    return "".join(rows)


def _security_card(item: SecurityAnalysis) -> str:
    ticker = item.ticker
    parts = ['<section class="card">']
    parts.append('<h3>{} <span class="code">{}</span> <span class="mkt">{}</span></h3>'.format(
        _e(ticker.name), _e(ticker.ticker), _e(ticker.market)))

    parts.append('<div class="quote">收盤 <b>{}</b> <span class="asof">（{}）</span>'
                 '　本益比 {} <span class="asof">（{}）</span>　股價淨值比 {}　殖利率 {}%</div>'.format(
                     _num(item.price), _date(item.price_date),
                     _num(item.per), _date(item.ratio_date),
                     _num(item.pbr), _num(item.dividend_yield)))

    if item.mentions:
        parts.append('<div class="mentions"><b>來源與原文主張</b><ul>')
        for mention in item.mentions:
            parts.append('<li><span class="src">{}</span>（立場：{}，信心 {:.2f}）：{}</li>'.format(
                _e(mention.source), _e(mention.stance), mention.confidence, _e(mention.claim)))
        parts.append("</ul></div>")

    for result in item.valuations:
        parts.append(_valuation_block(result, item.price))

    divergence = item.divergence()
    if divergence:
        parts.append('<div class="diverge"><b>模型分歧度</b>　變異係數 {:.3f}'
                     '（採用 {} / {} 個模型）<br><span class="asof">{}</span></div>'.format(
                         divergence["cv"], divergence["models_used"],
                         divergence["models_total"], _e(divergence["note"])))

    under = item.undervalued_count()
    parts.append('<div class="under">現價低於 <b>{}</b> / {} 個可用模型的 P25 區間下緣'
                 '（Sprint 1 共 {} 個模型）</div>'.format(
                     under["count"], under["of"], under["sprint_total"]))

    if item.missing:
        parts.append('<div class="gaps"><b>本檔資料缺漏</b><ul>')
        for gap in item.missing:
            parts.append("<li>{}</li>".format(_e(gap)))
        parts.append("</ul></div>")

    parts.append("</section>")
    return "".join(parts)


STYLE = """
:root{--fg:#1a1a1a;--mut:#666;--line:#e2e2e2;--warn:#8a5a00;--warnbg:#fff8e6;
      --miss:#a3341f;--ok:#1e6b3a;--bg:#fff;--card:#fafafa;
      --band:#c9d9e8;--band2:#7ba3c9;--now:#c0392b}
@media (prefers-color-scheme:dark){:root{
      --fg:#e8e8e8;--mut:#9a9a9a;--line:#333;--warn:#e0b050;--warnbg:#3a2f14;
      --miss:#f08a70;--ok:#6fcf97;--bg:#151515;--card:#1e1e1e;
      --band:#33485c;--band2:#5b87ad;--now:#ff7a6b}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0 auto;padding:20px 16px 40px;background:var(--bg);color:var(--fg);
     font:16px/1.65 -apple-system,BlinkMacSystemFont,"PingFang TC","Noto Sans TC",sans-serif;
     max-width:940px;overflow-wrap:break-word}
h1{font-size:21px;margin:0 0 4px;letter-spacing:.01em}
h2{font-size:16px;margin:30px 0 12px;padding-bottom:6px;border-bottom:2px solid var(--line)}
h3{font-size:16px;margin:0 0 8px}
.sub{color:var(--mut);font-size:13px;margin:0 0 18px}
.note{background:color-mix(in srgb,var(--band) 22%,transparent);
      border-left:3px solid var(--band2);padding:10px 13px;
      font-size:13px;line-height:1.55;margin:10px 0;border-radius:0 5px 5px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
      padding:15px 14px;margin:0 0 16px}
.code{color:var(--mut);font-weight:400}
.mkt{font-size:11px;background:var(--line);color:var(--mut);padding:2px 7px;
     border-radius:10px;vertical-align:middle}
.quote{font-size:14px;padding:8px 0;border-bottom:1px dashed var(--line);margin-bottom:12px}
.asof{color:var(--mut);font-size:12px}
.missing{color:var(--miss);font-size:12px;font-weight:600}
.model{border-top:1px solid var(--line);padding:12px 0}
.model-head{font-size:14px;margin-bottom:6px}
.tag-na{background:var(--line);color:var(--mut);font-size:11px;padding:2px 7px;
        border-radius:10px;margin-left:8px}
.reason{color:var(--miss);font-size:13px;margin:4px 0}
.warn{background:var(--warnbg);color:var(--warn);font-size:12.5px;padding:8px 10px;
      border-radius:5px;margin:6px 0;line-height:1.5}
.kv{border-collapse:collapse;font-size:13.5px;width:100%}
.kv th{text-align:left;color:var(--mut);font-weight:500;padding:4px 12px 4px 0;
       white-space:nowrap;width:180px;vertical-align:top}
.kv td{padding:4px 0;font-variant-numeric:tabular-nums}
.band{display:block;width:100%;max-width:520px;height:auto;margin:6px auto 12px}
.b-outer{fill:var(--band);opacity:.6}
.b-inner{fill:var(--band2);opacity:.7}
.b-mid{stroke:var(--fg);stroke-width:1.6;opacity:.7}
.b-now{stroke:var(--now);stroke-width:2;stroke-dasharray:3 2}
.b-lab,.b-val{font-size:10px;fill:var(--mut);text-anchor:middle}
.b-val{font-weight:600}
.b-now-lab{font-size:11px;fill:var(--now);text-anchor:middle;font-weight:700}
.diverge,.under{font-size:13px;padding:9px 0;border-top:1px solid var(--line)}
.gaps,.mentions{font-size:13px;margin-top:10px}
.gaps{color:var(--miss)}
.gaps ul,.mentions ul{margin:4px 0;padding-left:19px}
.gaps li,.mentions li{margin:3px 0}
.src{color:var(--mut)}
.feed{border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:0 0 12px;
      background:var(--card)}
.feed-head{font-size:14.5px;font-weight:600;display:flex;flex-wrap:wrap;
           gap:6px;align-items:baseline}
.pill{font-size:11px;padding:2px 8px;border-radius:10px;font-weight:600}
.pill-ok{background:color-mix(in srgb,var(--ok) 18%,transparent);color:var(--ok)}
.pill-na{background:var(--line);color:var(--mut)}
.feed ul{margin:8px 0 0;padding-left:18px;font-size:13px}
.feed li{margin:4px 0}
.feed a{color:inherit;text-decoration:none;border-bottom:1px solid var(--line)}
.feed .when{color:var(--mut);font-size:12px;margin-right:6px;font-variant-numeric:tabular-nums}
.foot{margin-top:34px;padding-top:12px;border-top:1px solid var(--line);
      color:var(--mut);font-size:12px}
@media(max-width:560px){
  body{padding:16px 13px 36px;font-size:15px}
  h1{font-size:19px}
  .card{padding:13px 12px;border-radius:9px}
  .quote{font-size:13.5px}
  /* 窄螢幕把 key/value 疊起來，180px 的標題欄在 375px 上會把數字擠爆 */
  .kv,.kv tbody,.kv tr,.kv th,.kv td{display:block;width:auto}
  .kv tr{padding:5px 0;border-bottom:1px solid var(--line)}
  .kv tr:last-child{border-bottom:0}
  .kv th{padding:0;font-size:12px}
  .kv td{padding:1px 0 0;font-size:14px;font-weight:500}
}
"""


def _feed_section(feed_status: Sequence[dict]) -> str:
    if not feed_status:
        return "<p class='sub'>本次未抓取自動來源。</p>"

    blocks = []
    for status in feed_status:
        usable = status.get("usable_for_extraction")
        pill = ('<span class="pill pill-ok">供抽取</span>' if usable
                else '<span class="pill pill-na">僅顯示</span>')
        if not status.get("ok"):
            pill = '<span class="pill pill-na">抓取失敗</span>'

        blocks.append('<div class="feed"><div class="feed-head">{}{}'
                      '<span class="when">最新 {}　共 {} 則</span></div>'.format(
                          _e(status["name"]), pill,
                          _e(status.get("latest") or "—"), status.get("count", 0)))

        if status.get("note"):
            blocks.append('<p class="reason">{}</p>'.format(_e(status["note"])))

        items = status.get("items") or []
        if items:
            blocks.append("<ul>")
            for entry in items[:5]:
                title = _e(entry.get("title"))
                link = entry.get("link") or ""
                label = ('<a href="{}" target="_blank" rel="noopener">{}</a>'.format(_e(link), title)
                         if link else title)
                blocks.append('<li><span class="when">{}</span>{}</li>'.format(
                    _e(entry.get("date")), label))
            blocks.append("</ul>")
        blocks.append("</div>")
    return "".join(blocks)


def render_fragment(
    analyses: Sequence[SecurityAnalysis],
    unresolved: Sequence[dict],
    global_gaps: Sequence[str],
    feed_status: Sequence[dict] = (),
) -> str:
    """回傳 <style> + 內容，不含 doctype/html/head/body。

    給 Artifact 之類需要自行包外框的環境用；render() 會把它包成完整文件。
    """
    now = dt.datetime.now()
    twse_items = [a for a in analyses if a.ticker.market == "TWSE"]
    tpex_items = [a for a in analyses if a.ticker.market == "TPEX"]

    out: List[str] = [
        "<style>{}</style>".format(STYLE),
        "<h1>每日選股儀表板</h1>",
        "<p class='sub'>產出時間 {}　·　分析 {} 檔標的</p>".format(
            now.strftime("%Y-%m-%d %H:%M"), len(analyses)),
        "<div class='note'>{}</div>".format(_e(METHOD_NOTE)),
        "<div class='note'>{}</div>".format(_e(CHIP_DISCLAIMER)),
        "<h2>來源動態</h2>",
        _feed_section(feed_status),
    ]

    out.append("<h2>台股 · 上市</h2>")
    if twse_items:
        out.extend(_security_card(a) for a in twse_items)
    else:
        out.append("<p class='sub'>本次無上市標的。</p>")

    out.append("<h2>台股 · 上櫃</h2>")
    if tpex_items:
        out.extend(_security_card(a) for a in tpex_items)
    else:
        out.append("<p class='sub'>本次無上櫃標的。</p>")

    out.append("<h2>未解析標的</h2>")
    if unresolved:
        out.append("<ul>")
        for record in unresolved:
            out.append("<li><b>{}</b>（{}）— {}</li>".format(
                _e(record.get("name") or "（無簡稱）"),
                _e(record.get("ticker") or "無代號"),
                _e(record.get("reason"))))
        out.append("</ul>")
    else:
        out.append("<p class='sub'>無。</p>")

    out.append("<h2>資料缺漏清單</h2>")
    gaps: List[str] = list(global_gaps)
    for item in analyses:
        for gap in item.missing:
            gaps.append("{} {}：{}".format(item.ticker.ticker, item.ticker.name, gap))
    if gaps:
        out.append("<ul class='gaps'>")
        out.extend("<li>{}</li>".format(_e(g)) for g in gaps)
        out.append("</ul>")
    else:
        out.append("<p class='sub'>無。</p>")

    out.append("<p class='foot'>本報告輸出估值區間與資料出處，不輸出目標價，"
               "不構成任何買賣建議。資料源：臺灣證券交易所 OpenAPI、證券櫃檯買賣中心 OpenAPI、"
               "各作者公開 RSS。未使用任何 Facebook 自動化存取（CLAUDE.md 鐵則 1）。</p>")
    return "".join(out)


def render(
    analyses: Sequence[SecurityAnalysis],
    unresolved: Sequence[dict],
    global_gaps: Sequence[str],
    feed_status: Sequence[dict] = (),
) -> str:
    return (
        "<!doctype html><html lang='zh-Hant'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1,viewport-fit=cover'>"
        "<meta name='color-scheme' content='light dark'>"
        "<title>每日選股儀表板 {}</title></head><body>{}</body></html>".format(
            config.today().strftime("%Y-%m-%d"),
            render_fragment(analyses, unresolved, global_gaps, feed_status),
        )
    )


def write(analyses, unresolved, global_gaps, feed_status=()):
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = config.OUTPUT_DIR / "dashboard_{}.html".format(config.today().strftime("%Y%m%d"))
    path.write_text(render(analyses, unresolved, global_gaps, feed_status), encoding="utf-8")
    return path
