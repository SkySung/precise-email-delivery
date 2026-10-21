import base64
import html
import json
import secrets
import socket
import statistics
import struct
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

BASE_DIR = Path(__file__).resolve().parent


def load_accounts():
    path = BASE_DIR / 'accounts.json'
    if not path.exists():
        raise SystemExit("找不到 accounts.json：請複製 accounts.example.json 並填入寄件 / 測試收件帳號。")
    return json.loads(path.read_text())

SEND_SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly',
]
READ_SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

_NTP_EPOCH_DELTA = 2208988800


def load_service(token_file, scopes):
    path = BASE_DIR / token_file
    if not path.exists():
        raise SystemExit(f"找不到 {token_file}，請先執行對應的授權腳本。")
    creds = Credentials.from_authorized_user_file(str(path), scopes)
    if not creds.valid:
        try:
            creds.refresh(Request())
        except RefreshError as e:
            raise SystemExit(
                f"{token_file} 的 refresh token 已失效（Testing 模式 7 天過期）：{e}\n請重新授權。"
            )
        path.write_text(creds.to_json())
    return build('gmail', 'v1', credentials=creds, cache_discovery=False)


def build_raw(to, subject, body):
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['to'] = to
    msg['subject'] = subject
    return {'raw': base64.urlsafe_b64encode(msg.as_bytes()).decode('ascii')}


def build_gmail_like_raw(to, subject, text):
    """組出與 Gmail 網頁版相同的 multipart/alternative（純文字 + <div dir="ltr"> HTML）結構"""
    lines = text.rstrip('\n').split('\n')
    esc = lambda s: html.escape(s, quote=False)
    body_html = '<div dir="ltr">' + esc(lines[0]) + ''.join(
        f"<div>{esc(l) if l.strip() else '<br>'}</div>" for l in lines[1:]) + '</div>\n'
    msg = MIMEMultipart('alternative', boundary='000000000000' + secrets.token_hex(8))
    msg['To'] = to
    msg['Subject'] = subject
    msg.attach(MIMEText(text if text.endswith('\n') else text + '\n', 'plain', 'utf-8'))
    msg.attach(MIMEText(body_html, 'html', 'utf-8'))
    return {'raw': base64.urlsafe_b64encode(msg.as_bytes()).decode('ascii')}


TIME_SERVERS = ['time.google.com', 'time1.google.com', 'time.stdtime.gov.tw', 'time.cloudflare.com']


def consensus_offset_ms(max_spread_ms=50.0):
    """多台伺服器交叉校時，回傳 (中位數 offset_ms, {server: offset_ms})；不一致或不足 2 台時丟 RuntimeError"""
    results = {}
    for server in TIME_SERVERS:
        r = sntp_offset_ms(server, samples=5)
        if r is not None:
            results[server] = r[0]
    if len(results) < 2:
        raise RuntimeError(f"可用時間伺服器不足 2 台：{results}")
    vals = sorted(results.values())
    if vals[-1] - vals[0] > max_spread_ms:
        raise RuntimeError(f"時間伺服器彼此不一致（差 {vals[-1] - vals[0]:.0f} ms）：{results}")
    return statistics.median(vals), results


def sntp_offset_ms(server='time.google.com', samples=7):
    """回傳 (offset_ms, rtt_ms)；offset = 標準時間 - 本機時間。取 RTT 最小的樣本，失敗回傳 None。"""
    best = None
    for _ in range(samples):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.settimeout(2)
                t1 = time.time()
                s.sendto(b'\x1b' + 47 * b'\0', (server, 123))
                data, _ = s.recvfrom(512)
                t4 = time.time()
        except OSError:
            continue
        if len(data) < 48:
            continue
        w = struct.unpack('!12I', data[:48])
        t2 = w[8] - _NTP_EPOCH_DELTA + w[9] / 2**32
        t3 = w[10] - _NTP_EPOCH_DELTA + w[11] / 2**32
        rtt = (t4 - t1) - (t3 - t2)
        offset = ((t2 - t1) + (t3 - t4)) / 2
        if best is None or rtt < best[1]:
            best = (offset, rtt)
    if best is None:
        return None
    return best[0] * 1000.0, best[1] * 1000.0
