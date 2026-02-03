# 問題與解釋紀錄 (Questions & Explanations)

本文件紀錄開發過程中的提問、解釋與重點提示。

---

## 報告書發送程式邏輯 (2026-02-03)

**問題：** 有關報告書發送的程式邏輯寫在哪裡？

**解釋：**
報告書發送的邏輯主要封裝在 `src/notification.py` 的 `NotificationService` 類別中，關鍵組件如下：

1. **進入點函數**：`send_daily_report` (位於文件末尾)，負責協調整合。
2. **內容生成**：`NotificationService.generate_daily_report`
   - 將個股分析數據格式化為 Markdown 報告書。
3. **統一發送接口**：`NotificationService.send`
   - 自動識別已配置的管道（微信、飛書、Email、LINE 等）並逐一調用對應的發送函數。
4. **分塊處理 (Messaging Chunking)**：
   - 由於 API 限制（如飛書 30KB、LINE 1000~5000字），程式內包含 `_send_xxx_chunked` 邏輯，會自動按有效長度將長報告安全地拆分發送。

## 新增 LINE 通知配置 (2026-02-03)

**問題：** 如何配置 LINE 通知發送？

**解釋：**
系統目前支援兩套 LINE 發送機制，依照需求配置 `.env` 即可：
1. **LINE Notify** (簡單快速)：只需一個 Token，適合個人開發者，僅支援純文字。
2. **LINE Messaging API** (正式機器人模式)：支援機器人頭像與更完整的訊息格式，需要配置 Channel Access Token 與 User ID。
## LINE Messaging API 為什麼需要 USER_ID？ (2026-02-03)

**問題：** 配置 LINE Messaging API 時，除了 Token 為何還要提供 ID？

**解釋：**
這是因為兩種 LINE 推送方式的機制不同：
1. **LINE Notify**：Token 本身就已經綁定了接收對象（在申請時選擇），所以程式只需提供 Token 即可發送。
2. **LINE Messaging API (機器人模式)**：
   - **Token** 代表機器人的「權限」和「身分」（發送者）。
   - **ID (User ID/Group ID)** 代表具體的「接收對象」。
   - 因為一個機器人可以服務很多人，系統必須知道要把日報推播給哪一個特定的用戶或群組，因此必須顯式指定 ID。
   - **如何獲取 ID？** 通常可以在 LINE Developers 控制台的 Messaging API Channel 設定頁面最下方找到 `Your user ID`。

## GitHub Actions 為何沒收到 LINE 訊息？ (2026-02-03)

**問題：** 如果是在 GitHub Actions 執行，改了程式碼為何還是沒收到訊息？

**解釋：**
GitHub Actions 運作在隔離環境，不能直接讀取本地的 `.env`。您必須將 Token 存入 GitHub 的 **Secrets** 中：
1. 前往 GitHub 倉庫的 `Settings` -> `Secrets and variables` -> `Actions`。
2. 點擊 `New repository secret`。
3. 名稱填入 `LINE_NOTIFY_TOKEN` (或 `LINE_CHANNEL_ACCESS_TOKEN` 等)，數值貼入您的金鑰。
4. 修正後的 `.github/workflows/daily_analysis.yml` 會在執行時將這些 Secrets 映射為程式可讀取的環境變數。

## LINE 通知的配置位置確認 (2026-02-03)

**問題：** LINE 的相關 Token 是不是跟其他的配置放在同一個位置？

**解釋：**
是的。所有的 LINE 通知配置都應該放在專案根目錄下的 **`.env`** 檔案中，與 `GEMINI_API_KEY`、`STOCK_LIST` 等配置並列。

**配置範例：**
```env
# 放在 .env 檔案中
LINE_NOTIFY_TOKEN=xxxxxxxxxxxx
```
系統在啟動時會統一載入 `.env` 中的環境變數。

## 分析台股所需的關鍵資訊 (2026-02-03)

**問題：** 如果要分析台灣市場及臺灣個股，至少需要抓取的資訊有哪些？

**解釋：**
針對台股特性，除了基礎的價量(OHLCV)外，必須優先抓取以下三類核心數據：
1. **三大法人動態**：外資（權值股指標）、投信（內資飆股指標）、自營商。
2. **信用交易籌碼**：融資（散戶力道）、融券（軋空力道）及券資比。
3. **分級持股與營收**：400/1000張大戶持股比例（籌碼集中度）及每月營收YoY（基本面催化劑）。
## 台股整合：為何選擇 yfinance 作為主要來源？ (2026-02-03)

**問題：** 為什麼在台股整合中選擇 `yfinance` 而非 `Akshare` 或 `efinance`？

**解釋：**
經過實測與調研，選擇 `yfinance` 作為台股（上市/上櫃）整合的核心來源有以下原因：
1. **穩定性與相容性**：`yfinance` 原生支援台灣交易所（`.TW` 與 `.TWO`），能穩定獲取 OHLCV 歷史數據，且格式與系統現有的美股邏輯一致。
2. **基本面數據**：透過 `yf.Ticker.info` 可以直接獲取台股的 **PE (本益比)**、**PB (股淨比)**、**Market Cap (市值)** 等關鍵指標，無需額外爬蟲。
3. **繞過限制**：TWSE 官方 API 具有嚴格的頻率限制與設備指紋識別，直接抓取容易被封鎖；而 `yfinance` 提供了相對穩定的緩衝層。
4. **自動識別**：系統現在能自動識別 4 位數代碼（如 2330），並優先嘗試 `TaiwanFetcher` 進行處理。

**後續擴展：**
關於「三大法人」與「融資券」數據，由於公開 API 獲取難度較高，目前的做法是在資料庫中 **預留欄位 (foreign_buy, margin_buy 等)**，並在 AI 的 Prompt 中加入對應的 placeholder。未來可進一步對接付費 API（如 FinMind）或實作更複雜的盤後網頁爬蟲來填充這些數據。
