@echo off
REM 每日選股儀表板 — Windows 一鍵執行
REM 首次執行會自動建立 venv 並安裝相依套件，之後直接沿用。

cd /d "%~dp0"

if not exist ".venv" (
  echo 首次執行，建立 Python 環境（約需一分鐘）...
  python -m venv .venv
  .venv\Scripts\python.exe -m pip install --quiet --upgrade pip
  .venv\Scripts\python.exe -m pip install --quiet -r requirements.txt
  echo 環境建好了。
)

.venv\Scripts\python.exe -m src.main %*

if errorlevel 1 (
  echo.
  echo 執行失敗。上面的訊息就是原因。
  pause
)
