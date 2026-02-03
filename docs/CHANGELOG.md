# Changelog

所有重要更改都會紀錄在此文件中。

格式基於 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本號遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [2.3.0] - 2026-02-01

### 新增
- 🇺🇸 **增強美股支援** (Issue #153)
  - 實現基於 Akshare 的美股歷史數據獲取 (`ak.stock_us_daily()`)
  - 實現基於 Yfinance 的美股即時行情獲取（優先策略）
  - 增加對不支持數據源（Tushare/Baostock/Pytdx/Efinance）的美股代碼過濾和快速降級

### 修復
- 🐛 修復 AMD 等美股代碼被誤識別為 A 股的問題 (Issue #153)

## [2.2.5] - 2026-02-01

### 新增
- 🤖 **AstrBot 消息推送** (PR #217)
  - 新增 AstrBot 通知管道，支持推送到 QQ 和微信
  - 支持 HMAC SHA256 簽名驗證，確保通信安全
  - 通過 `ASTRBOT_URL` 和 `ASTRBOT_TOKEN` 配置

## [2.2.4] - 2026-02-01

### 新增
- ⚙️ **可配置數據源優先級** (PR #215)
  - 支持通過環境變數（如 `YFINANCE_PRIORITY=0`）動態調整數據源優先級
  - 無需修改程式碼即可優先使用特定數據源（如 Yahoo Finance）

## [2.2.3] - 2026-01-31

### 修復
- 📦 更新 requirements.txt，增加 `lxml_html_clean` 依賴以解決相容性問題

## [2.2.2] - 2026-01-31

### 修復
- 🐛 修復代理配置區分大小寫問題 (fixes #211)

## [2.2.1] - 2026-01-31

### 修復
- 🐛 **YFinance 相容性修復** (PR #210, fixes #209)
  - 修復新版 yfinance 返回 MultiIndex 欄位名導致的數據解析錯誤

## [2.2.0] - 2026-01-31

### 新增
- 🔄 **多源回退策略增強**
  - 實現了更強健的數據獲取回退機制 (feat: multi-source fallback strategy)
  - 優化了數據源故障時的自動切換邏輯

### 修復
- 🐛 修復 analyzer 運行後無法通過改 .env 文件的 stock_list 內容調整跟蹤的股票

## [2.1.14] - 2026-01-31

### 文檔
- 📝 更新 README 和優化 auto-tag 規則

## [2.1.13] - 2026-01-31

### 修復
- 🐛 **Tushare 優先級與即時行情** (Fixed #185)
  - 修復 Tushare 數據源優先級設置問題
  - 修復 Tushare 即時行情獲取功能

## [2.1.12] - 2026-01-30

### 修復
- 🌐 修復代理配置在某些情況下的區分大小寫問題
- 🌐 修復本地環境禁用代理的邏輯

## [2.1.11] - 2026-01-30

### 優化
- 🚀 **飛書消息流優化** (PR #192)
  - 優化飛書 Stream 模式的消息類型處理
  - 修改 Stream 消息模式默認為關閉，防止配置錯誤運行時報錯

## [2.1.10] - 2026-01-30

### 合併
- 📦 合併 PR #154 貢獻

## [2.1.9] - 2026-01-30

### 新增
- 93: 💬 **微信文本消息支持** (PR #137)
  - 新增微信推送的純文本消息類型支持
  - 添加 `WECHAT_MSG_TYPE` 配置項

## [2.1.8] - 2026-01-30

### 修復
- 🐛 修正日誌中 API 提供商顯示錯誤 (PR #197)

## [2.1.7] - 2026-01-30

### 修復
- 🌐 禁用本地環境的代理設置，避免網路連接問題

## [2.1.6] - 2026-01-29

### 新增
- 📡 **Pytdx 數據源 (Priority 2)**
  - 新增通達信數據源，免費無需註冊
  - 多伺服器自動切換
  - 支持即時行情和歷史數據
- 🏷️ **多源股票名稱解析**
  - DataFetcherManager 新增 `get_stock_name()` 方法
  - 新增 `batch_get_stock_names()` 批量查詢
  - 自動在多數據源間回退
  - Tushare 和 Baostock 新增股票名稱/列表方法
- 🔍 **增強搜尋回退**
  - 新增 `search_stock_price_fallback()` 用於數據源全部失敗時
  - 新增搜尋維度：市場分析、行業分析
  - 最大搜尋次數從 3 增加到 5
  - 改進搜尋結果格式（每維度 4 條結果）

### 改進
- 更新搜尋查詢模板以提高相關性
- 增強 `format_intel_report()` 輸出結構

## [2.1.5] - 2026-01-29

### 新增
- 📡 新增 Pytdx 數據源和多源股票名稱解析功能

## [2.1.4] - 2026-01-29

### 文檔
- 📝 更新贊助商資訊

## [2.1.3] - 2026-01-28

### 文檔
- 📝 重構 README 佈局
- 🌐 新增繁體中文翻譯 (README_CHT.md)

### 修復
- 🐛 修復 WebUI 無法輸入美股代碼問題
  - 輸入框邏輯改成所有字母都轉換成大寫
  - 支持 `.` 的輸入（如 `BRK.B`）

## [2.1.2] - 2026-01-27

### 修復
- 🐛 修復個股分析推送失敗和報告路徑問題 (fixes #166)
- 🐛 修改 CR 錯誤，確保微信消息最大字節配置生效

## [2.1.1] - 2026-01-26

### 新增
- 🔧 添加 GitHub Actions auto-tag 工作流
- 📡 添加 yfinance 保底數據源及數據缺失警告

### 修復
- 🐳 修復 docker-compose 路徑和文檔命令
- 🐳 Dockerfile 補充 copy src 資料夾 (fixes #145)

## [2.1.0] - 2026-01-25

### 新增
- 🇺🇸 **美股分析支持**
  - 支持美股代碼直接輸入（如 `AAPL`, `TSLA`）
  - 使用 YFinance 作為美股數據源
- 📈 **MACD 和 RSI 技術指標**
  - MACD：趨勢確認、金叉死叉訊號（零軸上金叉⭐、金叉✅、死叉❌）
  - RSI：超買超賣判斷（超賣⭐、強勢✅、超買⚠️）
  - 指標訊號納入綜合評分系統
- 🎮 **Discord 推送支持** (PR #124, #125, #144)
  - 支持 Discord Webhook 和 Bot API 兩種方式
  - 通過 `DISCORD_WEBHOOK_URL` 或 `DISCORD_BOT_TOKEN` + `DISCORD_CHANNEL_ID` 配置
- 🤖 **機器人命令交互**
  - 釘釘機器人支持 `/分析 股票代碼` 命令觸發分析
  - 支持 Stream 長連接模式
- 🌡️ **AI 溫度參數可配置** (PR #142)
  - 支持自定義 AI 模型溫度參數
- 🐳 **Zeabur 部署支持**
  - 添加 Zeabur 映像檔部署工作流
  - 支持 commit hash 和 latest 雙標籤

### 重構
- 🏗️ **專案結構優化**
  - 核心程式碼移至 `src/` 目錄，根目錄更清爽
  - 文檔移至 `docs/` 目錄
  - Docker 配置移至 `docker/` 目錄
  - 修復所有 import 路徑，保持向後相容
- 🔄 **數據源架構升級**
  - 新增數據源熔斷機制，單數據源連續失敗自動切換
  - 即時行情快取優化，批量預取減少 API 調用
  - 網路代理智能分流，國內介面自動直通
- 🤖 Discord 機器人重構為平台適配器架構

### 修復
- 🌐 **網路穩定性增強**
  - 自動檢測代理配置，對國內行情介面強制直通
  - 修復 EfinanceFetcher 偶發的 `ProtocolError`
  - 增加對底層網路錯誤的捕獲和重試機制
- 📧 **郵件渲染優化**
  - 修復郵件中表格不渲染問題 (#134)
  - 優化郵件排版，更緊湊美觀
- 📢 **企業微信推送修復**
  - 修復大盤複盤推送不完整問題
  - 增強消息分割邏輯，支持更多標題格式
  - 增加分批發送間隔，避免限流丟失
- 👷 **CI/CD 修復**
  - 修復 GitHub Actions 中路徑引用的錯誤

## [2.0.0] - 2026-01-24

### 新增
- 🇺🇸 **美股分析支持**
  - 支持美股代碼直接輸入（如 `AAPL`, `TSLA`）
  - 使用 YFinance 作為美股數據源
- 🤖 **機器人命令交互** (PR #113)
  - 釘釘機器人支持 `/分析 股票代碼` 命令觸發分析
  - 支持 Stream 長連接模式
  - 支持選擇精簡報告或完整報告
- 🎮 **Discord 推送支持** (PR #124)
  - 支持 Discord Webhook 推送
  - 添加 Discord 環境變數到工作流

### 修復
- 🐳 修復 WebUI 在 Docker 中綁定 0.0.0.0 (fixed #118)
- 🔔 修復飛書長連接通知問題
- 🐛 修復 `analysis_delay` 未定義錯誤
- 🔧 啟動時 config.py 檢測通知管道，修復已配置自定義管道情況下仍然提示未配置問題

### 改進
- 🔧 優化 Tushare 優先級判斷邏輯，提升封裝性
- 🔧 修復 Tushare 優先級提升後仍排在 Efinance 之後的問題
- ⚙️ 配置 TUSHARE_TOKEN 時自動提升 Tushare 數據源優先級
- ⚙️ 實現 4 個用戶回饋 issue (#112, #128, #38, #119)

## [1.6.0] - 2026-01-19

### 新增
- 🖥️ WebUI 管理介面及 API 支持（PR #72）
  - 全新 Web 架構：分層設計（Server/Router/Handler/Service）
  - 核心 API：支持 `/analysis` (觸發分析), `/tasks` (查詢進度), `/health` (健康檢查)
  - 交互介面：支持頁面直接輸入代碼並觸發分析，即時展示進度
  - 運行模式：新增 `--webui-only` 模式，僅啟動 Web 服務
  - 解決了 [#70](https://github.com/ZhuLinsen/daily_stock_analysis/issues/70) 的核心需求（提供觸發分析的介面）
- ⚙️ GitHub Actions 配置靈活性增強（[#79](https://github.com/ZhuLinsen/daily_stock_analysis/issues/79)）
  - 支持從 Repository Variables 讀取非敏感配置（如 STOCK_LIST, GEMINI_MODEL）
  - 保持對 Secrets 的向下相容

### 修復
- 🐛 修復企業微信/飛書報告截斷問題（[#73](https://github.com/ZhuLinsen/daily_stock_analysis/issues/73)）
  - 移除 notification.py 中不必要的長度硬截斷邏輯
  - 依賴底層自動分片機制處理長消息

### 修復
- 🐛 修復 GitHub Workflow 環境變數缺失（[#80](https://github.com/ZhuLinsen/daily_stock_analysis/issues/80)）
  - 修復 `CUSTOM_WEBHOOK_BEARER_TOKEN` 未正確傳遞到 Runner 的問題

## [1.5.0] - 2026-01-17

### 新增
- 📲 單股推送模式（[#55](https://github.com/ZhuLinsen/daily_stock_analysis/issues/55)）
  - 每分析完一隻股票立即推送，不用等全部分析完
  - 命令行參數：`--single-notify`
  - 環境變數：`SINGLE_STOCK_NOTIFY=true`
- 🔐 自定義 Webhook Bearer Token 認證（[#51](https://github.com/ZhuLinsen/daily_stock_analysis/issues/51)）
  - 支持需要 Token 認證的 Webhook 端點
  - 環境變數：`CUSTOM_WEBHOOK_BEARER_TOKEN`

## [1.4.0] - 2026-01-17

### 新增
- 📱 Pushover 推送支持（PR #26）
  - 支持 iOS/Android 跨平台推送
  - 通過 `PUSHOVER_USER_KEY` 和 `PUSHOVER_API_TOKEN` 配置
- 🔍 博查搜尋 API 集成（PR #27）
  - 中文搜尋優化，支持 AI 摘要
  - 通過 `BOCHA_API_KEYS` 配置
- 📊 Efinance 數據源支持（PR #59）
  - 新增 efinance 作為數據源選項
- 🇭🇰 港股支持（PR #17）
  - 支持 5 位代碼或 HK 前綴（如 `hk00700`、`hk1810`）

### 修復
- 🔧 飛書 Markdown 渲染優化（PR #34）
  - 使用交互卡片和格式化器修復渲染問題
- ♻️ 股票列表熱重載（PR #42 修復）
  - 分析前自動重載 `STOCK_LIST` 配置
- 🐛 釘釘 Webhook 20KB 限制處理
  - 長消息自動分塊發送，避免被截斷
- 🔄 AkShare API 重試機制增強
  - 添加失敗快取，避免重複請求失敗介面

### 改進
- 📝 README 精簡優化
  - 高級配置移至 `docs/full-guide.md`


## [1.3.0] - 2026-01-12

### 新增
- 🔗 自定義 Webhook 支持
  - 支持任意 POST JSON 的 Webhook 端點
  - 自動識別釘釘、Discord、Slack、Bark 等常見服務格式
  - 支持配置多個 Webhook（逗號分隔）
  - 通過 `CUSTOM_WEBHOOK_URLS` 環境變數配置

### 修復
- 📝 企業微信長消息分批發送
  - 解決自選股過多時內容超過 4096 字符限制導致推送失敗的問題
  - 智能按股票分析塊分割，每批添加分頁標記（如 1/3, 2/3）
  - 批次間隔 1 秒，避免觸發頻率限制

## [1.2.0] - 2026-01-11

### 新增
- 📢 多管道推送支持
  - 企業微信 Webhook
  - 飛書 Webhook（新增）
  - 郵件 SMTP（新增）
  - 自動識別管道類型，配置更簡單

### 改進
- 統一使用 `NOTIFICATION_URL` 配置，相容舊的 `WECHAT_WEBHOOK_URL`
- 郵件支持 Markdown 轉 HTML 渲染

## [1.1.0] - 2026-01-11

### 新增
- 🤖 OpenAI 兼容 API 支持
  - 支持 DeepSeek、通義千問、Moonshot、智譜 GLM 等
  - Gemini 和 OpenAI 格式二選一
  - 自動降級重試機制

## [1.0.0] - 2026-01-10

### 新增
- 🎯 AI 決策儀表板分析
  - 一句話核心結論
  - 精確買入/止損/目標點位
  - 檢查清單（✅⚠️❌）
  - 分持倉建議（空倉者 vs 持倉者）
- 📊 大盤複盤功能
  - 主要指數行情
  - 漲跌統計
  - 板塊漲跌榜
  - AI 生成複盤報告
- 🔍 多數據源支持
  - AkShare（主數據源，免費）
  - Tushare Pro
  - Baostock
  - YFinance
- 📰 新聞搜尋服務
  - Tavily API
  - SerpAPI
- 💬 企業微信機器人推送
- ⏰ 定時任務調度
- 🐳 Docker 部署支持
- 🚀 GitHub Actions 零成本部署

### 技術特性
- Gemini AI 模型（gemini-3-flash-preview）
- 429 限流自動重試 + 模型切換
- 請求間延時防封禁
- 多 API Key 負載均衡
- SQLite 本地數據存儲

---

[Unreleased]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.3.0...HEAD
[2.3.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.2.5...v2.3.0
[2.2.5]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.2.4...v2.2.5
[2.2.4]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.2.3...v2.2.4
[2.2.3]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.2.2...v2.2.3
[2.2.2]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.2.1...v2.2.2
[2.2.1]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.2.0...v2.2.1
[2.2.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.14...v2.2.0
[2.1.14]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.13...v2.1.14
[2.1.13]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.12...v2.1.13
[2.1.12]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.11...v2.1.12
[2.1.11]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.10...v2.1.11
[2.1.10]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.9...v2.1.10
[2.1.9]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.8...v2.1.9
[2.1.8]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.7...v2.1.8
[2.1.7]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.6...v2.1.7
[2.1.6]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.5...v2.1.6
[2.1.5]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.4...v2.1.5
[2.1.4]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.3...v2.1.4
[2.1.3]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.2...v2.1.3
[2.1.2]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.1...v2.1.2
[2.1.1]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.1.0...v2.1.1
[2.1.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.6.0...v2.0.0
[1.6.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.5.0...v1.6.0
[1.5.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.3.0...v1.4.0
[1.3.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/ZhuLinsen/daily_stock_analysis/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/ZhuLinsen/daily_stock_analysis/releases/tag/v1.0.0
