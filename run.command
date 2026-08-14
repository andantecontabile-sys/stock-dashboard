#!/bin/bash
# 每日選股儀表板 — macOS 一鍵執行
# 首次執行會自動建立 venv 並安裝相依套件，之後直接沿用。

cd "$(dirname "$0")" || exit 1
set -e

PY=python3
VENV=.venv

if [ ! -d "$VENV" ]; then
  echo "首次執行，建立 Python 環境（約需一分鐘）…"
  "$PY" -m venv "$VENV"
  "$VENV/bin/pip" install --quiet --upgrade pip
  "$VENV/bin/pip" install --quiet -r requirements.txt
  echo "環境建好了。"
fi

"$VENV/bin/python" -m src.main "$@"
STATUS=$?

if [ $STATUS -ne 0 ]; then
  echo
  echo "執行失敗（代碼 $STATUS）。上面的訊息就是原因。"
  echo "按 Enter 關閉這個視窗。"
  read -r _
fi

exit $STATUS
