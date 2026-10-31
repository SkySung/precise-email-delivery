import argparse
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request

from common import (READ_SCOPES, SEND_SCOPES, build_gmail_like_raw,
                    consensus_offset_ms, load_accounts, load_service)

TZ = ZoneInfo('Asia/Taipei')


def log(msg, offset_ms=0.0):
    now = datetime.fromtimestamp(time.time() + offset_ms / 1000.0, TZ)
    print(f"[標準 {now.strftime('%H:%M:%S.%f')[:-3]}] {msg}", flush=True)


def fmt(epoch):
    return datetime.fromtimestamp(epoch, TZ).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]


def true_now(offset_ms):
    return time.time() + offset_ms / 1000.0


def sleep_until_true(target_true, offset_ms):
    # 粗等待用牆上時鐘（Mac 睡眠時仍會前進），每秒檢查一次
    while (rem := target_true - true_now(offset_ms)) > 0:
        time.sleep(min(rem, 1.0))


def spin_until_mono(target_mono):
    while (rem := target_mono - time.monotonic()) > 0:
        if rem > 0.05:
            time.sleep(min(rem - 0.05, 0.5))


def mono_for_true(target_true, offset_ms):
    return time.monotonic() + (target_true - true_now(offset_ms))


def main():
    ap = argparse.ArgumentParser(description='在指定的標準時間精準寄出 Gmail')
    ap.add_argument('--at', help='目標時間（台灣時間），如 "2027-01-15 10:00:00"')
    ap.add_argument('--to')
    ap.add_argument('--subject')
    ap.add_argument('--body-file', help='UTF-8 純文字內文檔')
    ap.add_argument('--lead-ms', type=float, default=0.0,
                    help='相對目標時間多少 ms 呼叫 send；0 即可：送出到蓋章的 d1 約 200 ms+，遠大於校時誤差')
    ap.add_argument('--rehearse', action='store_true', help='演練：寄給 B，目標為 90 秒後的下一個整分鐘')
    ap.add_argument('--yes', action='store_true', help='跳過啟動確認')
    args = ap.parse_args()

    # 執行期間阻止 Mac 進入睡眠
    subprocess.Popen(['caffeinate', '-dimsu', '-w', str(os.getpid())])

    log("交叉校時中…")
    # 校時失敗時不中止：改用系統時鐘並多延後 1 秒（寧可晚到，不可早到、不可沒寄）
    extra_s = 0.0
    try:
        offset_ms, detail = consensus_offset_ms()
        log(f"本機偏差 {offset_ms:+.1f} ms（標準 - 本機）  " +
            ", ".join(f"{k}={v:+.0f}" for k, v in detail.items()), offset_ms)
    except RuntimeError as e:
        offset_ms, extra_s = 0.0, 1.0
        log(f"[警告] 校時失敗（{e}），暫用系統時鐘並多延後 1 秒；T-45s 會再試一次")

    if args.rehearse:
        start = datetime.fromtimestamp(true_now(offset_ms) + 90, TZ)
        target_dt = (start + timedelta(minutes=1)).replace(second=0, microsecond=0)
        to = load_accounts()['receiver']
        tag = f"REHEARSAL {target_dt.strftime('%H:%M:%S')}"
        subject = f"[{tag}] {args.subject}" if args.subject else tag
        body = (Path(args.body_file).read_text(encoding='utf-8') if args.body_file
                else f"rehearsal for {target_dt.isoformat()}")
        if args.to:
            log(f"[演練] 忽略 --to {args.to}，一律寄給測試收件帳號 {to}")
    else:
        if not (args.at and args.to and args.subject and args.body_file):
            ap.error('正式模式需要 --at --to --subject --body-file（或用 --rehearse 演練）')
        target_dt = datetime.strptime(args.at, '%Y-%m-%d %H:%M:%S').replace(tzinfo=TZ)
        to, subject = args.to, args.subject
        body = Path(args.body_file).read_text(encoding='utf-8')

    t0 = target_dt.timestamp()
    fire_true = t0 + args.lead_ms / 1000.0
    lead_s = t0 - true_now(offset_ms)
    if lead_s < 70:
        sys.exit(f"距離目標只剩 {lead_s:.0f} 秒，至少需要 70 秒準備。")

    print("\n================ 發送內容 ================")
    print(f"目標時間 T0 : {fmt(t0)}（台灣）")
    print(f"實際發射   : {fmt(fire_true)}（T0 +{args.lead_ms:.0f} ms）")
    print(f"收件人     : {to}")
    print(f"主旨       : {subject}")
    print(f"內文       :\n{body}")
    print("==========================================\n")
    if not args.rehearse and not args.yes:
        if input("確認無誤請輸入 yes：").strip() != 'yes':
            sys.exit("已取消。")

    # 每個 API 請求最多等 8 秒，避免網路卡住時無限等待
    sender = load_service('token_sender.json', SEND_SCOPES, timeout=8)
    raw = build_gmail_like_raw(to, subject, body)

    # T-90s：刷新 access token，避免發送當下觸發 refresh；失敗只警告（啟動時載入的 token 仍有效 1 小時）
    sleep_until_true(t0 - 90, offset_ms)
    creds = sender._http.credentials
    try:
        base_req = Request()
        creds.refresh(lambda *a, **k: base_req(*a, **{**k, 'timeout': 15}))
        Path(__file__).with_name('token_sender.json').write_text(creds.to_json())
        log(f"Token 已刷新，有效至 {creds.expiry} UTC", offset_ms)
    except Exception as e:
        log(f"[警告] Token 刷新失敗（{e}），沿用目前 token（有效至 {creds.expiry} UTC）", offset_ms)

    # T-45s：重新交叉校時，之後全程改用 monotonic，不受系統時鐘跳動影響
    sleep_until_true(t0 - 45, offset_ms)
    try:
        offset_ms, detail = consensus_offset_ms()
        extra_s = 0.0
        log(f"最終校時 {offset_ms:+.1f} ms，鎖定 monotonic 發射點", offset_ms)
    except RuntimeError as e:
        extra_s = max(extra_s, 0.2)
        log(f"[警告] 最終校時失敗（{e}），沿用先前偏差並多延後 {extra_s * 1000:.0f} ms", offset_ms)
    fire_mono = mono_for_true(fire_true + extra_s, offset_ms)

    # T-10s：預熱 TLS 連線並記下 historyId（失敗時用來即時判斷是否已寄出，避免重複寄信）
    spin_until_mono(fire_mono - 10.0)
    start_hid = None
    for _ in range(2):
        t = time.monotonic()
        try:
            start_hid = sender.users().getProfile(userId='me').execute()['historyId']
            log(f"TLS 預熱完成（{(time.monotonic() - t) * 1000:.0f} ms）", offset_ms)
            break
        except Exception as e:
            log(f"[警告] 預熱失敗（{e}）", offset_ms)

    def sent_since_start():
        """回傳 T0 後寄件備份新增的訊息 id；無法確認時丟例外"""
        if start_hid:
            resp = sender.users().history().list(userId='me', startHistoryId=start_hid,
                                                 historyTypes=['messageAdded'], labelId='SENT').execute()
            ids = [a['message']['id'] for h in resp.get('history', []) for a in h.get('messagesAdded', [])]
        else:
            ids = [m['id'] for m in sender.users().messages().list(
                userId='me', q=f'in:sent to:{to} after:{int(t0) - 60}').execute().get('messages', [])]
        return ids[0] if ids else None

    def confirm_not_sent():
        """連續兩次確認寄件備份沒有新信才回傳 True；確認到已寄出回傳 msg id；無法確認回傳 False"""
        clean = 0
        for _ in range(10):
            time.sleep(3 if start_hid else 10)
            try:
                found = sent_since_start()
            except Exception as e:
                log(f"[警告] 無法查詢寄件備份（{e}）", offset_ms)
                continue
            if found:
                return found
            clean += 1
            if clean >= 2:
                return True
        return False

    spin_until_mono(fire_mono)
    t_fire_mono = time.monotonic()
    # 以 monotonic 換算，系統時鐘若在倒數期間跳動，紀錄仍正確
    t_fire_true = fire_true + extra_s + (t_fire_mono - fire_mono)
    msg_id = None
    for attempt in range(1, 6):
        try:
            msg_id = sender.users().messages().send(userId='me', body=raw).execute()['id']
            break
        except Exception as e:
            log(f"[錯誤] 第 {attempt} 次發送失敗：{e}", offset_ms)
        state = confirm_not_sent()
        if isinstance(state, str):
            msg_id = state
            log(f"寄件備份已有新信 {msg_id}，判定剛才其實已送出，不重試", offset_ms)
            break
        if state is False:
            sys.exit("❗ 無法確認信是否已寄出。為避免重複寄信，腳本停止重試。"
                     "請立刻打開寄件備份確認：沒有這封信才手動補寄。")
        log(f"確認寄件備份沒有這封信，立即第 {attempt + 1} 次重試", offset_ms)
    else:
        sys.exit("❗ 連續 5 次發送失敗且確認未寄出，請立刻用 Gmail 手動寄出。")
    rtt = (time.monotonic() - t_fire_mono) * 1000

    log(f"已送出 msg {msg_id}，發射於 {fmt(t_fire_true)}，從發射到完成 {rtt:.0f} ms", offset_ms)

    def verdict(epoch):
        diff = int(epoch) - int(t0)
        return '✅ 同一秒' if diff == 0 else ('❌ 早到！' if diff < 0 else f'⚠️ 晚 {diff} 秒')

    try:
        verify(sender, msg_id, args.rehearse, verdict)
    except Exception as e:
        log(f"[提示] 信已送出，但事後驗證失敗（{e}），請到寄件備份確認", offset_ms)


def verify(sender, msg_id, rehearse, verdict):
    sent = sender.users().messages().get(
        userId='me', id=msg_id, format='metadata', metadataHeaders=['Message-ID']).execute()
    a_stamp = int(sent['internalDate']) / 1000.0
    print(f"\nA 寄件備份 internalDate = {fmt(a_stamp)}  {verdict(a_stamp)}")

    if rehearse:
        msgid = sent['payload']['headers'][0]['value']
        receiver = load_service('token_receiver.json', READ_SCOPES)
        for _ in range(60):
            hits = receiver.users().messages().list(userId='me', q=f'rfc822msgid:{msgid}').execute().get('messages')
            if hits:
                break
            time.sleep(1)
        else:
            sys.exit("60 秒內 B 沒收到信。")
        m = receiver.users().messages().get(userId='me', id=hits[0]['id'], format='metadata',
                                            metadataHeaders=['X-Received']).execute()
        b_stamp = int(m['internalDate']) / 1000.0
        arrivals = [int(t) / 1000.0 for h in m['payload']['headers']
                    for t in re.findall(r'\.(\d{13});', h['value'])]
        print(f"B 收件匣 internalDate = {fmt(b_stamp)}  {verdict(b_stamp)}   ← 收件匣排序/顯示")
        if arrivals:
            print(f"B 實際進信箱 X-Received = {fmt(max(arrivals))}  {verdict(max(arrivals))}   ← 原始標頭")


if __name__ == '__main__':
    main()
