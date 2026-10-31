# precise-email-delivery

在指定的**標準時間**（例如某天 10:00:00 整）讓一封信進到對方的 Gmail 收件匣，而且**絕不能早到**。
適用於「名額有限、先到先得、早於開放時間寄出視同無效」的申請信。

提供兩條寄信路徑，並附上量測工具來比較利弊：

| 路徑 | 腳本 | 特性 |
|---|---|---|
| Gmail API | `send_precise_mail.py` | 發射時間精準到毫秒；寄出 → 進信箱約 1.5～2.1 秒 |
| Gmail 網頁版（自動按下寄出） | `web_probe.py` | 與人工手動寄信完全相同的流程（含「取消傳送」等待）；目前用於量測延遲 |

---

## 2026-11-01 正式寄送（愛爾蘭打工度假 Email 登記）

| 項目 | 內容 |
|---|---|
| 時間 | **2026-11-01（週日）09:00:00**（台灣時間） |
| 收件人 | 蔡小姐 `corina.mc.tsai@gmail.com` |
| 規則 | 名額 400，依收到先後取前 400 份有效申請；**提前或重複登記無效** |
| 寄法 | Gmail API，在標準時間 T0 整發射（理由見 [`docs/2026-10-22-研究紀錄.md`](docs/2026-10-22-研究紀錄.md) 的決策矩陣） |

### 信件內容（只需三項資料）

主旨：

```
愛爾蘭打工度假簽證申請－<護照英文姓名>
```

內文（存成 `body.txt`，已被 `.gitignore` 排除，因為含個資）：

```
蔡小姐您好：

我欲申請台灣－愛爾蘭打工度假簽證，申請資料如下：

① Passport English name：<護照英文姓名，與護照一致>
② Email address：<申請人 Gmail>
③ Phone number：<手機號碼>

敬請查收，謝謝您！

<護照英文姓名> 敬上
```

### 兩台電腦分工

- 每台電腦負責**一位申請人**，用**該申請人自己的 Gmail** 寄出，**每個帳號只寄一次**。
- 每個寄件帳號各自建立 GCP 專案與 OAuth 用戶端（見下方「新增寄件帳號」）；測試收件帳號可以共用。
- 正式收件人只在當天的指令裡出現；所有演練一律寄給 `accounts.json` 的測試收件帳號（`--rehearse` 會強制覆蓋 `--to`）。

### 當天流程

1. 前一晚確認：`git pull`、`body.txt` 內容與護照一致、token 在 7 天內授權過。
2. **08:50 前**啟動（電腦插電、不要闔上螢幕、確認網路可用；公司電腦注意夜間自動更新重開機）：

   ```bash
   uv run python send_precise_mail.py --at "2026-11-01 09:00:00" \
     --to corina.mc.tsai@gmail.com \
     --subject "愛爾蘭打工度假簽證申請－<護照英文姓名>" \
     --body-file body.txt
   ```

3. 核對畫面上的收件人、主旨、內文，輸入 `yes`。之後不用再操作。
   畫面會先印出「✅ 已收到確認…開始倒數」，底部有一行每秒更新的狀態列（現在時間、距離 T0、下一步），代表程式在跑。
4. 結束時畫面會印出寄件備份的 `internalDate`；看到 `✅ 同一秒` 即完成。
5. **不論發生什麼事都不要再執行第二次**。若畫面出現 `❗`，先打開寄件備份確認，沒有這封信才手動補寄。
6. 08:50～09:05 不要用寄件帳號寄其他信（重試前用寄件備份是否有新信判斷是否已寄出）。
7. 發射前按 Ctrl+C 可安全取消（不會寄出、不殘留 process）；腳本會依按下時機提示信是否已寄出。

正式信**不用排程**，一定在「終端機」App 前親自啟動：排程看不到畫面，也會跳過輸入 `yes` 的核對。
最終決策（API vs 手動）、10/22～10/31 量測總結、朋友 2025 年信件分析見 [`docs/2026-11-01-最終決策與當天流程.md`](docs/2026-11-01-最終決策與當天流程.md)。

---

## 2026-10-31：「一定要寄到、而且只寄一封」的強化

原則：在 T0 整發射時，`Date` 由 Google 伺服器蓋，就算本機時間差 0.5 秒也不會早到（送出到蓋章本身還有約 200 ms 以上）。
所以真正的風險不是早到，而是**因為例外而沒寄出**，或**重試造成重複寄信（取消資格）**。

| # | 舊行為 | 後果 | 修正 |
|---|---|---|---|
| 1 | 啟動時校時失敗（UDP 123 被擋、伺服器不一致）直接拋例外 | 腳本結束 | 改用系統時鐘並多延後 1 秒；T−45 s 會再試一次，成功就恢復正常 |
| 2 | 四台伺服器任一台離群（差 > 50 ms）就整次校時作廢 | 誤觸後備方案 | 先排除偏離中位數 > 50 ms 的伺服器，剩 ≥ 2 台取中位數 |
| 3 | T−90 s 刷新 token 失敗會拋例外；連線卡住要等 120 秒 | 當掉 / 錯過 T0 | 失敗只警告（啟動時的 token 仍有效 1 小時），刷新請求逾時 15 秒 |
| 4 | T−5 s 預熱 `getProfile` 失敗會拋例外 | 發射前當掉 | 改在 T−10 s 預熱，失敗只警告，最多試 2 次 |
| 5 | API 請求沒有逾時 | 網路卡住時永遠等下去 | 每個請求逾時 8 秒 |
| 6 | 送出失敗只重試 1 次，且用「搜尋寄件備份」判斷（搜尋索引有延遲） | 沒寄出 / 重複寄出 | 預熱時記下 `historyId`，失敗後用 history API（即時）連續兩次確認寄件備份沒有新信才重試，最多 5 次；**無法確認時停止並請人工檢查，絕不冒重複寄信的風險** |
| 7 | 事後驗證出錯會拋例外 | 已寄出卻看似失敗 | 驗證失敗只提示 |

### 故障注入測試（2026-10-31，全部寄給測試收件帳號）

| 情境 | 結果 | send 呼叫次數 | 收件數 |
|---|---|---|---|
| 正常（正式主旨與內文） | `Date` = T0 ✅ | 1 | 1 |
| 送出前網路錯誤 | 確認未寄出後重試，`Date` = T0 + 7 s | 2 | **1** |
| 已送出但回應遺失 | 判定已寄出、不重試，`Date` = T0 ✅ | 1 | **1** |
| 時間伺服器全部連不上 | 系統時鐘 + 1 s，`Date` = T0 + 1 s | 1 | 1 |

送出前失敗時，從失敗到重試約 7 秒（兩次確認各間隔 3 秒），這是為了避免重複寄信刻意保留的代價。

### 這台寄件電腦的實測（公司網路）

- 本機時鐘慢 0.28～0.46 秒，而且會跳動（系統用 `time.apple.com` 同步）；腳本自動補償，T−45 s 後改用 monotonic 倒數，不受跳動影響。
- TLS 預熱 0.5～1.7 s、API 來回約 0.9～1.1 s；發射 → 進信箱 1.6～3.4 s（舊電腦約 1.5～2.1 s）。

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
| `scripts/rehearse_daily.sh`、`scripts/web_probe_daily.sh` | 10/22～10/31 每小時量測用的 launchd 包裝腳本（含日期與啟動時間檢查；11/1 已卸載排程） |
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

#### 新增寄件帳號（用該帳號登入 GCP Console）

1. 建立新專案（例如 `precise-email-delivery`）。
2. API 程式庫 → 啟用 **Gmail API**。
3. Google Auth Platform → 開始：填應用程式名稱、支援信箱；目標對象選「**外部**」；填聯絡信箱；同意使用者資料政策 → 建立。
4. 目標對象 → 測試使用者 → **Add users**：加入寄件帳號與測試收件帳號 → 儲存。
5. 用戶端 → 建立用戶端 → 類型「**電腦版應用程式**」→ 建立 → 下載 JSON（或複製用戶端 ID 與密碼），存成 `credentials.json`。密碼只在建立當下顯示一次。
6. 執行授權：`auth.py` 用寄件帳號、`auth_receiver.py` 用測試收件帳號。授權頁出現「這個應用程式未經 Google 驗證」時按「繼續」。

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

用正式內容演練（主旨會加上 `[REHEARSAL HH:MM:SS]` 前綴，收件人仍強制為測試收件帳號）：

```bash
uv run python send_precise_mail.py --rehearse --subject "正式主旨" --body-file body.txt
```

### API 正式發送

```bash
uv run python send_precise_mail.py --at "YYYY-MM-DD HH:MM:SS" --to 對方信箱 --subject "主旨" --body-file body.txt
```

流程：交叉校時（失敗則系統時鐘 + 1 s）→ `caffeinate` 防睡眠 → T−90 s 刷新 token → T−45 s 重新校時並改用 monotonic 時鐘倒數（不受系統校時跳秒影響）→ T−10 s TLS 預熱並記下 `historyId` → T0 送出 → 回讀時間戳。
送出失敗時用 history API 確認寄件備份沒有新信才重試（最多 5 次），詳見上方「一定要寄到」一節。
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

`.gitignore` 已排除 `credentials.json`、`token*.json`、`clientid.txt`、`accounts.json`、`body.txt`、量測 CSV 與 `.eml`。
這些檔案含 OAuth client secret、存取權杖與個人帳號，**不要提交**。換電腦時請另外安全地傳送 `credentials.json`，或直接重新下載；token 在新電腦重新授權即可。
