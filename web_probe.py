import argparse
import csv
import math
import random
import re
import statistics
import time
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

from common import READ_SCOPES, consensus_offset_ms, load_accounts, load_service
from send_precise_mail import TZ, fmt, mono_for_true, spin_until_mono, true_now

_accounts = load_accounts()
SENDER = _accounts['sender']
RECEIVER = _accounts['receiver']
CDP_URL = 'http://127.0.0.1:9222'
CSV_PATH = Path(__file__).with_name('web_probe_results.csv')
FIELDS = ['subject', 'weekday', 'hour', 'click', 'click_src', 'internal_date', 'arrival', 'd1_lo_s', 'd2_s']

INSTALL_KEY_LISTENER = """() => {
  window.__probeKey = null;
  document.addEventListener('keydown', e => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) window.__probeKey = Date.now();
  }, {capture: true, once: true});
}"""


def gmail_page(browser):
    for ctx in browser.contexts:
        for p in ctx.pages:
            if 'mail.google.com' in p.url:
                return p
    return browser.contexts[0].new_page()


def open_compose(page, subject, body):
    page.goto('https://mail.google.com/mail/u/0/?view=cm&fs=1'
              f'&to={quote(RECEIVER)}&su={quote(subject)}&body={quote(body)}')
    page.wait_for_function(f"document.title.includes('{SENDER}')", timeout=30000)
    box = page.locator('div[role="textbox"][contenteditable="true"]').first
    box.wait_for(timeout=30000)
    box.click()
    page.keyboard.press('End')
    page.evaluate(INSTALL_KEY_LISTENER)


def wait_arrival(receiver, subject, timeout=150):
    deadline = time.time() + timeout
    while time.time() < deadline:
        hits = receiver.users().messages().list(userId='me', q=f'subject:"{subject}"').execute().get('messages')
        if hits:
            m = receiver.users().messages().get(userId='me', id=hits[0]['id'], format='metadata',
                                                metadataHeaders=['X-Received']).execute()
            arrivals = [int(t) / 1000.0 for h in m['payload']['headers']
                        for t in re.findall(r'\.(\d{13});', h['value'])]
            if arrivals:
                return int(m['internalDate']) / 1000.0, max(arrivals)
        time.sleep(2)
    return None


def probe(rounds, gap):
    receiver = load_service('token_receiver.json', READ_SCOPES)
    offset_ms, _ = consensus_offset_ms()
    last_sync = time.monotonic()
    print(f"本機偏差 {offset_ms:+.1f} ms")
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(CDP_URL)
        page = gmail_page(browser)
        for i in range(1, rounds + 1):
            if time.monotonic() - last_sync > 120:
                offset_ms, _ = consensus_offset_ms()
                last_sync = time.monotonic()
            subject = f"WEBPROBE {uuid.uuid4().hex[:10]}"
            open_compose(page, subject, f"web probe {i}")

            fire_true = math.ceil(true_now(offset_ms)) + 2 + random.random()
            spin_until_mono(mono_for_true(fire_true, offset_ms))
            t_before = true_now(offset_ms)
            page.keyboard.press('Meta+Enter')
            try:
                js_ms = page.evaluate('window.__probeKey')
            except Exception:
                js_ms = None
            click, src = ((js_ms + offset_ms) / 1000.0, 'js') if js_ms else (t_before, 'py')

            got = wait_arrival(receiver, subject)
            if got is None:
                print(f"[{i:02d}] {subject} 150 秒內沒進 B 信箱，略過")
                continue
            idt, arrival = got
            d1_lo, d2 = idt - click, arrival - click
            now = datetime.fromtimestamp(click, TZ)
            row = dict(subject=subject, weekday=now.strftime('%a'), hour=now.hour,
                       click=f"{click:.3f}", click_src=src, internal_date=f"{idt:.0f}",
                       arrival=f"{arrival:.3f}", d1_lo_s=f"{d1_lo:.3f}", d2_s=f"{d2:.3f}")
            new_file = not CSV_PATH.exists()
            with CSV_PATH.open('a', newline='') as f:
                w = csv.DictWriter(f, fieldnames=FIELDS)
                if new_file:
                    w.writeheader()
                w.writerow(row)
            print(f"[{i:02d}] 按下 {fmt(click)[11:]}  Date {fmt(idt)[11:19]}  進信箱 {fmt(arrival)[11:]}"
                  f"  →  Δ1 ∈ [{d1_lo:+.2f}, {d1_lo + 1:+.2f}) s   Δ2 = {d2:.2f} s")
            if i < rounds:
                time.sleep(gap)


def wilson_upper(k, n, z=1.645):
    p = k / n
    return (p + z * z / (2 * n) + z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / (1 + z * z / n)


def report():
    rows = list(csv.DictReader(CSV_PATH.open()))
    if not rows:
        raise SystemExit("還沒有資料")
    d2 = sorted(float(r['d2_s']) for r in rows)
    d1 = [float(r['d1_lo_s']) for r in rows]
    n = len(d2)
    print(f"樣本數 {n}（{', '.join(sorted({r['weekday'] for r in rows}))}；時段 {sorted({int(r['hour']) for r in rows})} 點）")
    print(f"Δ2 按下→進信箱：最快 {d2[0]:.2f}  第5快 {d2[min(4, n - 1)]:.2f}  中位數 {statistics.median(d2):.2f}  最慢 {d2[-1]:.2f} s")
    print(f"Δ1 按下→Date 標頭：下限最小值 {min(d1):+.2f} s（負值代表 Date 可能早於按下的那一秒）\n")
    base = math.floor(d2[0] * 10) / 10
    for lead in sorted({base, base - 0.5, base - 1, base - 2, base - 3}, reverse=True):
        if lead <= 0:
            continue
        k = sum(d < lead for d in d2)
        upper = 1 - 0.05 ** (1 / n) if k == 0 else wilson_upper(k, n)
        print(f"整點前 {lead:5.1f} s 按下：歷史 {k}/{n} 次會早到，95% 信心早到率 ≤ {upper:.1%}"
              f"；Date 標頭約 {60 - lead:.0f} 秒（前一分鐘）")


def main():
    ap = argparse.ArgumentParser(description='自動在 Gmail 網頁版按下寄出，量測 按下→Date 與 按下→進 B 信箱 的延遲')
    ap.add_argument('-n', '--rounds', type=int, default=10)
    ap.add_argument('--gap', type=float, default=30.0, help='每輪間隔秒數')
    ap.add_argument('--report', action='store_true', help='只讀 CSV 印統計')
    args = ap.parse_args()
    report() if args.report else probe(args.rounds, args.gap)


if __name__ == '__main__':
    main()
