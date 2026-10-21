from google_auth_oauthlib.flow import InstalledAppFlow

# B 帳號（收件端兼延遲回讀）：只需要讀取權限來取得 internalDate
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly'
]
TOKEN_FILE = 'token_receiver.json'

def authenticate():
    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
    creds = flow.run_local_server(port=0)
    with open(TOKEN_FILE, 'w') as token_file:
        token_file.write(creds.to_json())
    print(f"\n[成功] 授權完成，已生成 {TOKEN_FILE}！")

if __name__ == '__main__':
    authenticate()
