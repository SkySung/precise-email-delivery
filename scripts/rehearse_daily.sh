#!/bin/zsh
# launchd 在 HH:58:00 呼叫：讓 --rehearse 瞄準下一個整點寄給測試收件帳號
# --rehearse 目標 = 現在 +90 秒後的下一個整分鐘，所以只有 HH:57:30～HH:58:29 啟動才會落在整點
set -u
cd "$(dirname "$0")/.."
mkdir -p logs
log="logs/rehearse_$(date +%Y%m%d_%H).log"

# 以目標整點（幾分鐘後）的日期判斷，避免 10/31 23:5x 那輪在 11/1 00:00 寄出
today=$(date -v+5M +%Y%m%d)
if [[ $today < 20261022 || $today > 20261031 ]]; then
  echo "$(date '+%F %T') 不在演練期間（10/22～10/31），略過" >> logs/rehearse_skipped.log
  exit 0
fi

# 睡眠中錯過排程時 launchd 會在喚醒後補跑，此時已瞄不到整點，直接略過
ms=$(date +%M%S)
if [[ $ms < 5730 || $ms > 5829 ]]; then
  echo "$(date '+%F %T') 啟動時間不在 HH:57:30～HH:58:29，略過" >> logs/rehearse_skipped.log
  exit 0
fi

/opt/homebrew/bin/uv run python -u send_precise_mail.py --rehearse >> "$log" 2>&1
