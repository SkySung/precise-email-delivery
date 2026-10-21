import base64
import os
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from common import load_accounts

TOKEN_FILE = 'token_sender.json'
SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly'
]

RECIPIENT = load_accounts()['receiver']
SUBJECT = '精準時間測試信件'

def main():
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())

    service = build('gmail', 'v1', credentials=creds)

    # 1. 預熱連線 (提前建立 TLS 連線池)
    print("正在進行 TLS 連線預熱...")
    t_pre_start = time.time()
    service.users().getProfile(userId='me').execute()
    print(f"預熱完成，耗時: {(time.time() - t_pre_start)*1000:.2f} ms")

    # 2. 建立信件內容（內文寫入當前發送時間戳記供後續比對）
    send_ts = time.time()
    body_content = f"SEND_TS:{send_ts}\n這是一封精準發信的延遲校正測試信。"
    
    message = MIMEMultipart()
    message['to'] = RECIPIENT
    message['subject'] = SUBJECT
    message.attach(MIMEText(body_content, 'plain', 'utf-8'))
    raw_payload = {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')}

    # 3. 發送信件並計算 RTT
    t_send_start = time.time()
    res = service.users().messages().send(userId='me', body=raw_payload).execute()
    t_send_finish = time.time()

    rtt = (t_send_finish - t_send_start) * 1000

    print("\n--- 發送測試結果 ---")
    print(f"發信觸發時間 (Send TS)  : {send_ts:.6f}")
    print(f"API 回應完成時間         : {t_send_finish:.6f}")
    print(f"本次發信網路 RTT        : {rtt:.2f} ms")
    print(f"Message ID              : {res.get('id')}")

if __name__ == '__main__':
    main()
