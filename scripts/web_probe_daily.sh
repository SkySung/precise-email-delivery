#!/bin/zsh
# launchd 在 HH:59:00 呼叫：網頁版在 HH:59:49 按下寄出，讓信大約在下一個整點抵達
# 需要專用 Chrome（--remote-debugging-port=9222）已登入寄件帳號；沒開就先開
set -u
cd "$(dirname "$0")/.."
mkdir -p logs
log="logs/web_probe_$(date +%Y%m%d_%H).log"

# 以目標整點（幾分鐘後）的日期判斷，避免 10/31 23:5x 那輪在 11/1 00:00 寄出
today=$(date -v+5M +%Y%m%d)
if [[ $today < 20261022 || $today > 20261031 ]]; then
  echo "$(date '+%F %T') 網頁版：不在量測期間（10/22～10/31），略過" >> logs/rehearse_skipped.log
  exit 0
fi

# 睡眠中錯過排程時 launchd 會在喚醒後補跑，此時來不及在 HH:59:49 按下，直接略過
ms=$(date +%M%S)
if [[ $ms < 5900 || $ms > 5920 ]]; then
  echo "$(date '+%F %T') 網頁版：啟動時間不在 HH:59:00～HH:59:20，略過" >> logs/rehearse_skipped.log
  exit 0
fi

if ! curl -s -m 1 http://127.0.0.1:9222/json/version > /dev/null; then
  # 關閉背景／被遮住視窗的節流：螢幕鎖定時頁面不會被當成隱藏而拖慢取消傳送的計時器
  open -na "Google Chrome" --args --remote-debugging-port=9222 \
    --user-data-dir="$HOME/.gmail-web-probe-chrome" \
    --disable-background-timer-throttling --disable-backgrounding-occluded-windows \
    --disable-renderer-backgrounding "https://mail.google.com/"
  sleep 8
fi

# 防止螢幕關閉：Chrome 視窗被隱藏時計時器會被節流，可能拉長取消傳送的等待
/usr/bin/caffeinate -dimsu /opt/homebrew/bin/uv run python -u web_probe.py -n 1 --lead 11 >> "$log" 2>&1
