"""帶快取與節流的 HTTP 取用層。

CLAUDE.md §4.3：所有 API 回應寫入 cache/{source}/{date}/{key}.json，同日重跑讀快取。
CLAUDE.md §10：新接端點時原始回應要留在 debug/ 供人工核對欄位。
"""
from __future__ import annotations

import datetime as dt
import json
import re
import threading
import time
from typing import Any, Dict, Optional

import requests

from . import config


class FetchError(RuntimeError):
    """取不到資料。呼叫端必須把它變成「資料缺漏」，不得靜默填值（鐵則 7）。"""


_last_call: Dict[str, float] = {}
_lock = threading.Lock()

_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": config.USER_AGENT})


def _throttle(source: str, interval: float) -> None:
    with _lock:
        previous = _last_call.get(source)
        now = time.monotonic()
        if previous is not None:
            wait = interval - (now - previous)
            if wait > 0:
                time.sleep(wait)
                now = time.monotonic()
        _last_call[source] = now


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)


def _cache_path(source: str, key: str, cache_date: dt.date):
    return config.CACHE_DIR / _safe(source) / cache_date.isoformat() / (_safe(key) + ".json")


def _find_fresh_cache(source: str, key: str, ttl_days: int) -> Optional[Any]:
    """在 ttl_days 內由新到舊找一份可用快取。"""
    today = config.today()
    for age in range(ttl_days + 1):
        path = _cache_path(source, key, today - dt.timedelta(days=age))
        if path.exists():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                # 壞掉的快取當作沒有，重抓。
                path.unlink(missing_ok=True)
    return None


def get_json(
    source: str,
    key: str,
    url: str,
    params: Optional[Dict[str, Any]] = None,
    ttl_days: int = 0,
    interval: float = config.TWSE_REQUEST_INTERVAL_SEC,
    debug_dump: bool = False,
) -> Any:
    """取 JSON。ttl_days=0 代表只認當日快取。

    debug_dump=True 時把原始回應另存一份到 debug/raw/，方便人工核對欄位名。
    """
    cached = _find_fresh_cache(source, key, ttl_days)
    if cached is not None:
        return cached

    _throttle(source, interval)
    try:
        response = _SESSION.get(url, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        raise FetchError("{} {} 取用失敗：{}".format(source, key, exc)) from exc
    except ValueError as exc:
        raise FetchError("{} {} 回應不是合法 JSON：{}".format(source, key, exc)) from exc

    path = _cache_path(source, key, config.today())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    if debug_dump:
        dump = config.DEBUG_DIR / "raw" / _safe(source) / (_safe(key) + ".json")
        dump.parent.mkdir(parents=True, exist_ok=True)
        dump.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return payload
