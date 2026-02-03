# ❓ 常見問題解答 (FAQ)

本文檔整理了用戶在使用過程中遇到的常見問題及解決方案。

---

## 📊 數據相關

### Q1: 美股代碼（如 AMD, AAPL）分析時價格顯示不正確？

**現象**：輸入美股代碼後，顯示的價格明顯不對（如 AMD 顯示 7.33 元），或被誤識別為 A 股。

**原因**：早期版本程式碼匹配邏輯優先嘗試國內 A 股規則，導致代碼衝突。

**解決方案**：
1. 已在 v2.3.0 修復，系統現在支持美股代碼自動識別
2. 如仍有問題，可在 `.env` 中設置：
   ```bash
   YFINANCE_PRIORITY=0
   ```
   這將優先使用 Yahoo Finance 數據源獲取美股數據

> 📌 相關 Issue: [#153](https://github.com/ZhuLinsen/daily_stock_analysis/issues/153)

---

### Q2: 報告中 "量比" 欄位顯示為空或 N/A？

**現象**：分析報告中量比數據缺失，影響 AI 對縮放量的判斷。

**原因**：默認的某些即時行情源（如新浪介面）不提供量比欄位。

**解決方案**：
1. 已在 v2.3.0 修復，騰訊介面現已支持量比解析
2. 推薦配置即時行情源優先級：
   ```bash
   REALTIME_SOURCE_PRIORITY=tencent,akshare_sina,efinance,akshare_em
   ```
3. 系統已內置 5 日均量計算作為保底邏輯

> 📌 相關 Issue: [#155](https://github.com/ZhuLinsen/daily_stock_analysis/issues/155)

---

### Q3: Tushare 獲取數據失敗，提示 Token 不對？

**現象**：日誌顯示 `Tushare 獲取數據失敗: 您的token不對，請確認`

**解決方案**：
1. **無 Tushare 帳號**：無需配置 `TUSHARE_TOKEN`，系統會自動使用免費數據源（AkShare、Efinance）
2. **有 Tushare 帳號**：確認 Token 是否正確，可在 [Tushare Pro](https://tushare.pro/weborder/#/login?reg=834638 ) 個人中心查看
3. 本專案所有核心功能均可在無 Tushare 的情況下正常運行

---

### Q4: 數據獲取被限流或返回為空？

**現象**：日誌顯示 `熔斷器觸發` 或數據返回 `None`

**原因**：免費數據源（東方財富、新浪等）有反爬機制，短時間大量請求會被限流。

**解決方案**：
1. 系統已內置多數據源自動切換和熔斷保護
2. 減少自選股數量，或增加請求間隔
3. 避免頻繁手動觸發分析

---

## ⚙️ 配置相關

### Q5: GitHub Actions 運行失敗，提示找不到環境變數？

**現象**：Actions 日誌顯示 `GEMINI_API_KEY` 或 `STOCK_LIST` 未定義

**原因**：GitHub 區分 `Secrets`（加密）和 `Variables`（普通變數），配置位置不對會導致讀取失敗。

**解決方案**：
1. 進入倉庫 `Settings` → `Secrets and variables` → `Actions`
2. **Secrets**（點擊 `New repository secret`）：存放敏感資訊
   - `GEMINI_API_KEY`
   - `OPENAI_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - 各類 Webhook URL
3. **Variables**（點擊 `Variables` 標籤）：存放非敏感配置
   - `STOCK_LIST`
   - `GEMINI_MODEL`
   - `REPORT_TYPE`

---

### Q6: 修改 .env 文件後配置沒有生效？

**解決方案**：
1. 確保 `.env` 文件位於專案根目錄
2. **Docker 部署**：修改後需重啟容器
   ```bash
   docker-compose down && docker-compose up -d
   ```
3. **GitHub Actions**：`.env` 文件不生效，必須在 Secrets/Variables 中配置
4. 檢查是否有多個 `.env` 文件（如 `.env.local`）導致覆蓋

---

### Q7: 如何配置代理訪問 Gemini/OpenAI API？

**解決方案**：

在 `.env` 中配置：
```bash
USE_PROXY=true
PROXY_HOST=127.0.0.1
PROXY_PORT=10809
```

> ⚠️ 注意：代理配置僅對本地運行生效，GitHub Actions 環境無需配置代理。

---

## 📱 推送相關

### Q8: 機器人推送失敗，提示消息過長？

**現象**：分析成功但未收到推送，日誌顯示 400 錯誤或 `Message too long`

**原因**：不同平台消息長度限制不同：
- 企業微信：4KB
- 飛書：20KB
- 釘釘：20KB

**解決方案**：
1. **自動分段**：最新版本已實現長消息自動切割
2. **單股推送模式**：設置 `SINGLE_STOCK_NOTIFY=true`，每分析完一隻股票立即推送
3. **精簡報告**：設置 `REPORT_TYPE=simple` 使用精簡格式

---

### Q9: Telegram 推送收不到消息？

**解決方案**：
1. 確認 `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID` 都已配置
2. 獲取 Chat ID 方法：
   - 給 Bot 發送任意消息
   - 訪問 `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - 在返回的 JSON 中找到 `chat.id`
3. 確保 Bot 已被添加到目標群組（如果是群聊）
4. 本地運行時需要能訪問 Telegram API（可能需要代理）

---

### Q10: 企業微信 Markdown 格式顯示不正常？

**解決方案**：
1. 企業微信對 Markdown 支持有限，可嘗試設置：
   ```bash
   WECHAT_MSG_TYPE=text
   ```
2. 這將發送純文本格式的消息

---

## 🤖 AI 模型相關

### Q11: Gemini API 返回 429 錯誤（請求過多）？

**現象**：日誌顯示 `Resource has been exhausted` 或 `429 Too Many Requests`

**解決方案**：
1. Gemini 免費版有速率限制（約 15 RPM）
2. 減少同時分析的股票數量
3. 增加請求延遲：
   ```bash
   GEMINI_REQUEST_DELAY=5
   ANALYSIS_DELAY=10
   ```
4. 或切換到 OpenAI 兼容 API 作為備選

---

### Q12: 如何使用 DeepSeek 等模型？

**配置方法**：

```bash
# 不需要配置 GEMINI_API_KEY
OPENAI_API_KEY=sk-xxxxxxxx
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-chat
```

支持的模型服務：
- DeepSeek: `https://api.deepseek.com/v1`
- 通義千問: `https://dashscope.aliyuncs.com/compatible-mode/v1`
- Moonshot: `https://api.moonshot.cn/v1`

---

## 🐳 Docker 相關

### Q13: Docker 容器啟動後立即退出？

**解決方案**：
1. 查看容器日誌：
   ```bash
   docker logs <container_id>
   ```
2. 常見原因：
   - 環境變數未正確配置
   - `.env` 文件格式錯誤（如有多餘空格）
   - 依賴包版本衝突

---

### Q14: Docker 中 WebUI 無法訪問？

**解決方案**：
1. 確保 `WEBUI_HOST=0.0.0.0`（不能是 127.0.0.1）
2. 檢查端口映射是否正確：
   ```yaml
   ports:
     - "8000:8000"
   ```

---

## 🔧 其他問題

### Q15: 如何只運行大盤複盤，不分析個股？

**方法**：
```bash
# 本地運行
python main.py --market-only

# GitHub Actions
# 手動觸發時選擇 mode: market-only
```

---

### Q16: 分析結果中買入/觀望/賣出數量統計不對？

**原因**：早期版本使用正則匹配統計，可能與實際建議不一致。

**解決方案**：已在最新版本中修復，AI 模型現在會直接輸出 `decision_type` 欄位用於準確統計。

---

## 💬 還有問題？

如果以上內容沒有解決你的問題，歡迎：
1. 查看 [完整配置指南](full-guide.md)
2. 搜尋或提交 [GitHub Issue](https://github.com/ZhuLinsen/daily_stock_analysis/issues)
3. 查看 [更新日誌](CHANGELOG.md) 了解最新修復

---

*最後更新：2026-02-01*
