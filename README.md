# precise-email-delivery

在指定的**標準時間**（例如某天 10:00:00 整）讓一封信進到對方的 Gmail 收件匣，而且**絕不能早到**。
適用於「名額有限、先到先得、早於開放時間寄出視同無效」的申請信。

提供兩條寄信路徑，並附上量測工具來比較利弊：

| 路徑 | 腳本 | 特性 |
|---|---|---|
| Gmail API | `send_precise_mail.py` | 發射時間精準到毫秒；寄出 → 進信箱約 1.5～2.1 秒 |
| Gmail 網頁版（自動按下寄出） | `web_probe.py` | 與人工手動寄信完全相同的流程（含「取消傳送」等待）；目前用於量測延遲 |

---

## 已用實驗驗證的 Gmail 時間規則

以下皆由「A 帳號寄 → B 帳號收」實測得出，判斷一律以 **B 收到的那封**為準。

| 項目 | 依據 | 精度 |
|---|---|---|
| 收件匣列表 / 點開信件 / 手機 App 顯示的時間 | **實際進信箱的時間**，捨去到分鐘 | 分鐘 |
| 收件匣排序 | **實際進信箱的時間** | — |
| `internalDate`（= `Date` 標頭，只有「顯示原始郵件」看得到） | Google 接受寄出的那一秒，捨去 | 秒（毫秒恆為 000） |
| B 端 `X-Received` 標頭的 SMTP id 結尾 13 位數 | 實際進信箱的 epoch 毫秒 | 毫秒 |

驗證方式：
- **顯示**：在 `:59.3`、`:29.3`、`:45.0` 發射三封，讓 `internalDate` 與進信箱時間跨不同分鐘 / 半分鐘，排除「`internalDate` + 捨去」「`internalDate` + 四捨五入」「進信箱 + 四捨五入」三種假設。
- **排序**：網頁信（`internalDate` :40、進信箱 :53.3）與 API 信（`internalDate` :50、進信箱 :51.2）在收件匣中網頁信排在上面（較新）→ 依進信箱時間排序。

已觀察到的延遲（樣本少，僅供參考）：
- API：發射 → `internalDate` 約 210～350 ms；發射 → 進信箱 1.51～2.08 s（8 封）。
- 網頁版（取消傳送預設 5 秒）：`internalDate` 疑似等於按下寄出的時間（1 個乾淨樣本，**未確認**）；`internalDate` → 進信箱約 12～14 s。
- 網頁版（2026-10-22，5 輪）：按下 → 進信箱 11.62～12.24 s，平均 11.84 s，標準差 0.25 s。

2026-10-22 補充驗證（詳見 [`docs/2026-10-22-研究紀錄.md`](docs/2026-10-22-研究紀錄.md)）：
- 網頁版的 `Date` 標頭用**寄件端電腦的時鐘**蓋（本機慢 122 ms，按下在標準 :54.069，`Date` 為 :53）；API 的 `Date` 由 Google 伺服器蓋。
- 收件人回信時的引用行（「X 於 … 寫道」）顯示的是**收件端進信箱時間**，捨去到分鐘。
- 「取消傳送」最小 5 秒，無法關閉。

### API 路徑的發射策略

在標準時間 **T0 整** 呼叫 send：`Date` 標頭必定 ≥ T0（信不可能在送出前被接受），
送出到蓋章的 d1（約 200 ms+）遠大於校時誤差（約 ±15 ms），因此不需要額外餘裕。
提前超過 d1 下限就會讓 `Date` 標頭變成前一秒。

---

## 檔案

| 檔案 | 用途 |
|---|---|
| `common.py` | 共用：載入 token / 帳號設定、組 Gmail 網頁版格式的信、多伺服器 SNTP 交叉校時 |
| `auth.py` | 寄件帳號授權 → `token_sender.json`（`gmail.send` + `gmail.readonly`） |
| `auth_receiver.py` | 測試收件帳號授權 → `token_receiver.json`（`gmail.readonly`） |
| `send_precise_mail.py` | API 精準發送；`--rehearse` 演練模式會寄給測試收件帳號並驗證 B 端時間 |
| `web_probe.py` | 透過 Chrome 除錯通道在 Gmail 網頁版按下寄出，量測 按下→`Date`、按下→進信箱 的延遲並累積成 CSV |
| `test_send.py` | 最早期的單次發送基準測試 |
| `accounts.example.json` | 帳號設定範本 |

---

## 在新電腦上設定

### 1. 安裝

```bash
git clone https://github.com/SkySung/precise-email-delivery.git
cd precise-email-delivery
uv sync
```

### 2. 放入不在 git 裡的檔案

- **`credentials.json`**：Google Cloud Console → 你的專案 → API 與服務 → 憑證 → OAuth 2.0 用戶端 ID（類型：桌面應用程式）→ 下載 JSON，改名為 `credentials.json`。
- **`accounts.json`**：

  ```bash
  cp accounts.example.json accounts.json
  ```

  填入寄件帳號（`sender`）與測試收件帳號（`receiver`）。

GCP 專案需啟用 Gmail API；OAuth 同意畫面若是 **Testing** 模式，兩個帳號都要加入「測試使用者」。

### 3. 授權

```bash
uv run python auth.py            # 用寄件帳號登入
uv run python auth_receiver.py   # 用測試收件帳號登入
```

授權時會在 `localhost` 起一個暫時的伺服器接收回呼；完成後程式會自行結束。

> **Testing 模式的 refresh token 只有 7 天效期。** 正式寄送前 7 天內一定要重新跑一次 `auth.py`。

### 4. 確認時鐘

```bash
sntp time.google.com
```

偏差應在 ±0.05 秒內。腳本本身會用 `time.google.com`、`time1.google.com`、`time.stdtime.gov.tw`、`time.cloudflare.com` 交叉校時並補償，不依賴系統時鐘；但系統時間正確可避免當天肉眼判斷混亂。
若 macOS 預設的 `time.apple.com` 連不到，到「系統設定 → 一般 → 日期與時間」改用 `time.google.com`。

---

## 使用

### API 演練

```bash
uv run python send_precise_mail.py --rehearse
```

自動瞄準約 90 秒後的下一個整分鐘寄給測試收件帳號，結束時印出 A 寄件備份與 **B 收件匣**的 `internalDate`，以及 B 實際進信箱時間。

### API 正式發送

```bash
uv run python send_precise_mail.py --at "YYYY-MM-DD 10:00:00" --to 對方信箱 --subject "主旨" --body-file body.txt
```

流程：交叉校時 → `caffeinate` 防睡眠 → T−90 s 刷新 token → T−45 s 重新校時並改用 monotonic 時鐘倒數（不受系統校時跳秒影響）→ T−5 s TLS 預熱 → T0 送出 → 回讀時間戳。
送出失敗時會先查寄件備份，確認沒寄出才重試一次，避免重複寄信。
當天：插電、不要闔上螢幕。

### 網頁版延遲量測

1. 開一個專用的 Chrome（獨立設定檔，不影響平常使用的 Chrome）：

   ```bash
   open -na "Google Chrome" --args --remote-debugging-port=9222 --user-data-dir="$HOME/.gmail-web-probe-chrome"
   ```

2. 在該視窗**手動**登入寄件帳號的 Gmail，「取消傳送」維持與正式當天相同的設定。
3. 量測（每輪會真的寄一封信給測試收件帳號）：

   ```bash
   uv run python web_probe.py -n 20
   uv run python web_probe.py --report
   ```

`--report` 會列出 按下→進信箱 的最快 / 中位數 / 最慢延遲，以及「整點前 L 秒按下」的歷史早到次數與 95% 信心早到率上限（0 次早到時為 `1 - 0.05^(1/n)`，約 3/n）。

---

## 安全

`.gitignore` 已排除 `credentials.json`、`token*.json`、`clientid.txt`、`accounts.json`、量測 CSV 與 `.eml`。
這些檔案含 OAuth client secret、存取權杖與個人帳號，**不要提交**。換電腦時請另外安全地傳送 `credentials.json`，或直接重新下載；token 在新電腦重新授權即可。
