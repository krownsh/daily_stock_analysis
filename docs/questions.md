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
