from google_auth_oauthlib.flow import InstalledAppFlow

# A 帳號（寄件端）：同時申請發信與讀取權限（讀取供後續分析延遲使用）
SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly'
]
TOKEN_FILE = 'token_sender.json'

def authenticate():
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    creds = flow.run_local_server(port=0)
    with open(TOKEN_FILE, 'w') as token_file:
        token_file.write(creds.to_json())
    print(f"\n[成功] 授權完成，已生成 {TOKEN_FILE}！")

if __name__ == '__main__':
    authenticate()
