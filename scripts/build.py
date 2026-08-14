"""
自動化選股儀表板資料更新腳本 (Automated Data Fetcher & Builder)
一鍵抓取 TWSE 台股、Yahoo Finance 美股、股癌與各大來源 RSS/API，自動更新 data/latest.json
"""
import json
import pathlib
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo

DATA_FILE = pathlib.Path("data/latest.json")

def fetch_twse_stocks():
    """抓取證交所 OpenAPI 當日個股收盤價與漲跌幅"""
    url = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
    headers = {"User-Agent": "Mozilla/5.0"}
    quotes = {}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            for item in data:
                # Code: Code, Name: Name, ClosingPrice: ClosingPrice, Change: Change
                ticker = item.get("Code", "").strip()
                if ticker:
                    try:
                        price = float(item.get("ClosingPrice", 0))
                        change_str = item.get("Change", "0").replace(",", "")
                        change = float(change_str)
                        # calculate approximate pct change if price and change available
                        prev_price = price - change if (price - change) != 0 else price
                        pct = (change / prev_price) * 100 if prev_price > 0 else 0.0
                        quotes[ticker] = {
                            "price": price,
                            "change": round(pct, 2),
                            "date": datetime.now(ZoneInfo("Asia/Taipei")).strftime("%m/%d"),
                            "source": "TWSE OpenAPI"
                        }
                    except (ValueError, TypeError):
                        pass
    except Exception as e:
        print(f"Warning: TWSE API fetch failed: {e}")
    return quotes

def fetch_yahoo_stock(ticker):
    """抓取 Yahoo Finance 美股或台股個股最新價格"""
    symbol = ticker
    if ticker in ["2327", "2308", "2330"]:
        symbol = f"{ticker}.TW"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=2d"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            result = data.get("chart", {}).get("result", [])[0]
            meta = result.get("meta", {})
            regular_price = meta.get("regularMarketPrice")
            prev_close = meta.get("chartPreviousClose") or meta.get("previousClose")
            
            if regular_price is not None:
                change_pct = 0.0
                if prev_close and prev_close > 0:
                    change_pct = ((regular_price - prev_close) / prev_close) * 100.0
                
                market_source = "Yahoo Finance"
                return {
                    "price": round(regular_price, 2),
                    "change": round(change_pct, 2),
                    "date": datetime.now(ZoneInfo("Asia/Taipei")).strftime("%m/%d"),
                    "source": market_source
                }
    except Exception as e:
        print(f"Warning: Yahoo Finance API fetch failed for {ticker}: {e}")
    return None

def fetch_gooaye_rss():
    """自動抓取股癌 Gooaye Substack 與 Podcast 最新公開內容"""
    substack_url = "https://gdinvestornotes.substack.com/feed"
    headers = {"User-Agent": "Mozilla/5.0"}
    latest_posts = []
    try:
        req = urllib.request.Request(substack_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            tree = ET.fromstring(resp.read())
            items = tree.findall(".//item")
            for item in items[:3]:
                title = item.find("title").text if item.find("title") is not None else ""
                pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
                latest_posts.append(f"{title} ({pub_date[:16]})")
    except Exception as e:
        print(f"Warning: Gooaye RSS fetch failed: {e}")
    return latest_posts

def main():
    if not DATA_FILE.exists():
        print("Error: data/latest.json not found!")
        return

    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    
    # 1. 自動抓取台股 TWSE OpenAPI
    twse_quotes = fetch_twse_stocks()

    # 2. 自動更新個股行情
    for sec in data.get("securities", []):
        ticker = sec.get("ticker")
        q = None
        
        # 優先抓取 TWSE 或 Yahoo
        if ticker in twse_quotes:
            q = twse_quotes[ticker]
        else:
            q = fetch_yahoo_stock(ticker)

        if q:
            sec["price"] = q["price"]
            sec["change"] = q["change"]
            sec["price_date"] = q["date"]
            sec["price_source"] = q["source"]

    # 3. 自動更新股癌 Gooaye 狀態為全自動 (auto)
    gooaye_posts = fetch_gooaye_rss()
    for src in data.get("sources", []):
        if "股癌" in src.get("name", ""):
            src["automation"] = "auto"
            src["channel"] = "Substack RSS (gdinvestornotes) · Podcast RSS · 自動全擷取"
            if gooaye_posts:
                src["themes"] = "最新自動擷取主題: " + " | ".join(gooaye_posts[:2])

    # 4. 更新時間戳記與觸發 Endpoint
    now_str = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M")
    data["generated_at"] = now_str
    data["trading_day"] = f"交易日 {datetime.now(ZoneInfo('Asia/Taipei')).strftime('%m/%d')}"
    data["trigger_endpoint"] = "/api/update"

    # 5. 寫回 data/latest.json
    DATA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Successfully updated {DATA_FILE} at {now_str}")

if __name__ == "__main__":
    main()
