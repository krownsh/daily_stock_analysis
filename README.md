<div align="center">

# 📈 股票智能分析系統

[![GitHub stars](https://img.shields.io/github/stars/ZhuLinsen/daily_stock_analysis?style=social)](https://github.com/ZhuLinsen/daily_stock_analysis/stargazers)
[![CI](https://github.com/ZhuLinsen/daily_stock_analysis/actions/workflows/ci.yml/badge.svg)](https://github.com/ZhuLinsen/daily_stock_analysis/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-Ready-2088FF?logo=github-actions&logoColor=white)](https://github.com/features/actions)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://hub.docker.com/)

> 🤖 基於 AI 大模型的 A股/港股/美股自選股智能分析系統，每日自動分析並推送「決策儀表盤」到企業微信/飛書/Telegram/郵箱

[**功能特性**](#-功能特性) · [**快速開始**](#-快速開始) · [**推送效果**](#-推送效果) · [**完整指南**](docs/full-guide.md) · [**常見問題**](docs/FAQ.md) · [**更新日誌**](docs/CHANGELOG.md)

繁體中文 | [English](docs/README_EN.md)

</div>

## 💖 贊助商 (Sponsors)
<div align="center">
  <a href="https://serpapi.com/baidu-search-api?utm_source=github_daily_stock_analysis" target="_blank">
    <img src="./sources/serpapi_banner_zh.png" alt="輕鬆抓取搜尋引擎上的即時金融新聞數據 - SerpApi" height="160">
  </a>
</div>
<br>


## ✨ 功能特性

| 模組 | 功能 | 說明 |
|------|------|------|
| AI | 決策儀表盤 | 一句話核心結論 + 精確買賣點位 + 操作檢查清單 |
| 分析 | 多維度分析 | 技術面 + 籌碼分佈 + 輿情情報 + 即時行情 |
| 市場 | 全球市場 | 支持 A股、港股、美股 |
| 複盤 | 大盤複盤 | 每日市場概覽、板塊漲跌、北向資金 |
| 推送 | 多渠道通知 | 企業微信、飛書、Telegram、釘釘、郵件、Pushover |
| 自動化 | 定時運行 | GitHub Actions 定時執行，無需服務器 |

### 技術棧與數據來源

| 類型 | 支持 |
|------|------|
| AI 模型 | Gemini（免費）、OpenAI 兼容、DeepSeek、通義千問、Claude、Ollama |
| 行情數據 | AkShare、Tushare、Pytdx、Baostock、YFinance |
| 新聞搜尋 | Tavily、SerpAPI、Bocha |

### 內置交易紀律

| 規則 | 說明 |
|------|------|
| 嚴禁追高 | 乖離率 > 5% 自動提示風險 |
| 趨勢交易 | MA5 > MA10 > MA20 多頭排列 |
| 精確點位 | 買入價、止損價、目標價 |
| 檢查清單 | 每項條件以「滿足 / 注意 / 不滿足」標記 |

## 🚀 快速開始

### 方式一：GitHub Actions（推薦）

> 5 分鐘完成部署，零成本，無需服務器。


#### 1. Fork 本倉庫

點擊右上角 `Fork` 按鈕（順便點個 Star⭐ 支持一下）

#### 2. 配置 Secrets

`Settings` → `Secrets and variables` → `Actions` → `New repository secret`

**AI 模型配置（二選一）**

| Secret 名稱 | 說明 | 必填 |
|------------|------|:----:|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/) 獲取免費 Key | ✅* |
| `OPENAI_API_KEY` | OpenAI 兼容 API Key（支持 DeepSeek、通義千問等） | 可選 |
| `OPENAI_BASE_URL` | OpenAI 兼容 API 地址（如 `https://api.deepseek.com/v1`） | 可選 |
| `OPENAI_MODEL` | 模型名稱（如 `deepseek-chat`） | 可選 |

> 注：`GEMINI_API_KEY` 和 `OPENAI_API_KEY` 至少配置一個

<details>
<summary><b>通知渠道配置</b>（點擊展開，至少配置一個）</summary>


| Secret 名稱 | 說明 | 必填 |
|------------|------|:----:|
| `WECHAT_WEBHOOK_URL` | 企業微信 Webhook URL | 可選 |
| `FEISHU_WEBHOOK_URL` | 飛書 Webhook URL | 可選 |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token（@BotFather 獲取） | 可選 |
| `TELEGRAM_CHAT_ID` | Telegram Chat ID | 可選 |
| `EMAIL_SENDER` | 發件人郵箱（如 `xxx@qq.com`） | 可選 |
| `EMAIL_PASSWORD` | 郵箱授權碼（非登錄密碼） | 可選 |
| `EMAIL_RECEIVERS` | 收件人郵箱（多個用逗號分隔，留空則發給自己） | 可選 |
| `PUSHPLUS_TOKEN` | PushPlus Token（[獲取地址](https://www.pushplus.plus)，國內推送服務） | 可選 |
| `CUSTOM_WEBHOOK_URLS` | 自定義 Webhook（支持釘釘等，多個用逗號分隔） | 可選 |
| `CUSTOM_WEBHOOK_BEARER_TOKEN` | 自定義 Webhook 的 Bearer Token（用於需要認證的 Webhook） | 可選 |
| `SINGLE_STOCK_NOTIFY` | 單股推送模式：設為 `true` 則每分析完一隻股票立即推送 | 可選 |
| `REPORT_TYPE` | 報告類型：`simple`(精簡) 或 `full`(完整)，Docker環境推薦設為 `full` | 可選 |
| `ANALYSIS_DELAY` | 個股分析和大盤分析之間的延遲（秒），避免API限流，如 `10` | 可選 |

> 至少配置一個渠道，配置多個則同時推送。更多配置請參考 [完整指南](docs/full-guide.md)

</details>

**其他配置**

| Secret 名稱 | 說明 | 必填 |
|------------|------|:----:|
| `STOCK_LIST` | 自選股代碼，如 `600519,hk00700,AAPL,TSLA` | ✅ |
| `TAVILY_API_KEYS` | [Tavily](https://tavily.com/) 搜尋 API（新聞搜尋） | 推薦 |
| `SERPAPI_API_KEYS` | [SerpAPI](https://serpapi.com/baidu-search-api?utm_source=github_daily_stock_analysis) 全渠道搜尋 | 可選 |
| `BOCHA_API_KEYS` | [博查搜尋](https://open.bocha.cn/) Web Search API（中文搜尋優化，支持AI摘要，多個key用逗號分隔） | 可選 |
| `TUSHARE_TOKEN` | [Tushare Pro](https://tushare.pro/weborder/#/login?reg=834638 ) Token | 可選 |
| `WECHAT_MSG_TYPE` | 企微消息類型，默認 markdown，支持配置 text 類型，發送純 markdown 文本 | 可選 |

#### 3. 啟用 Actions

`Actions` 標籤 → `I understand my workflows, go ahead and enable them`

#### 4. 手動測試

`Actions` → `每日股票分析` → `Run workflow` → `Run workflow`

#### 完成

默認每個**工作日 18:00（台北時間）**自動執行，也可手動觸發

### 方式二：本地運行 / Docker 部署

```bash
# 克隆項目
git clone https://github.com/ZhuLinsen/daily_stock_analysis.git && cd daily_stock_analysis

# 安裝依賴
pip install -r requirements.txt

# 配置環境變量
cp .env.example .env && vim .env

# 運行分析
python main.py
```

> Docker 部署、定時任務配置請參考 [完整指南](docs/full-guide.md)

## 📱 推送效果

![運行效果演示](./sources/all_2026-01-13_221547.gif)

### 決策儀表盤
```
📊 2026-01-10 決策儀表盤
3隻股票 | 🟢買入:1 🟡觀望:2 🔴賣出:0

🟢 買入 | 貴州茅台(600519)
📌 縮量回踩MA5支撐，乖離率1.2%處於最佳買點
💰 狙擊: 買入1800 | 止損1750 | 目標1900
✅多頭排列 ✅乖離安全 ✅量能配合

🟡 觀望 | 寧德時代(300750)
📌 乖離率7.8%超過5%警戒線，嚴禁追高
⚠️ 等待回調至MA5附近再考慮

---
生成時間: 18:00
```

### 大盤複盤

![大盤複盤推送效果](./sources/dapan_2026-01-13_22-14-52.png)

```
🎯 2026-01-10 大盤複盤

📊 主要指數
- 上證指數: 3250.12 (🟢+0.85%)
- 深證成指: 10521.36 (🟢+1.02%)
- 創業板指: 2156.78 (🟢+1.35%)

📈 市場概況
上漲: 3920 | 下跌: 1349 | 漲停: 155 | 跌停: 3

🔥 板塊表現
領漲: 互聯網服務、文化傳媒、小金屬
領跌: 保險、航空機場、光伏設備
```
## ⚙️ 配置說明

> 📖 完整環境變量、定時任務配置請參考 [完整配置指南](docs/full-guide.md)


## 🖥️ 本地 WebUI（可選）

```bash
python main.py --webui       # 啟動 WebUI + 執行分析
python main.py --webui-only  # 僅啟動 WebUI
```

訪問 `http://127.0.0.1:8000` 可進行配置管理、觸發分析、查看任務狀態。

> 詳細說明請參考 [完整指南 - WebUI](docs/full-guide.md#本地-webui-管理界面)

## 🗺️ Roadmap

查看已支持的功能和未來規劃：[更新日誌](docs/CHANGELOG.md)

> 有建議？歡迎 [提交 Issue](https://github.com/ZhuLinsen/daily_stock_analysis/issues)


---

## ☕ 支撐項目

如果本项目對你有幫助，歡迎支持項目的持續維護與迭代，感謝支持 🙏  
贊賞可備註聯繫方式，祝股市長虹

| 支付寶 (Alipay) | 微信支付 (WeChat) | Ko-fi |
| :---: | :---: | :---: |
| <img src="./sources/alipay.jpg" width="200" alt="Alipay"> | <img src="./sources/wechatpay.jpg" width="200" alt="WeChat Pay"> | <a href="https://ko-fi.com/mumu157" target="_blank"><img src="./sources/ko-fi.png" width="200" alt="Ko-fi"></a> |

---

## 🤝 貢獻

歡迎提交 Issue 和 Pull Request！

詳見 [貢獻指南](docs/CONTRIBUTING.md)

## 📄 License
[MIT License](LICENSE) © 2026 ZhuLinsen

如果你在項目中使用或基於本项目進行二次開發，
非常歡迎在 README 或文檔中註明來源並附上本倉庫連結。
這將有助於項目的持續維護和社區發展。

## 📬 聯繫與合作
- GitHub Issues：[提交 Issue](https://github.com/ZhuLinsen/daily_stock_analysis/issues)

## ⭐ Star History
**如果覺得有用，請給個 ⭐ Star 支持一下！**

<a href="https://star-history.com/#ZhuLinsen/daily_stock_analysis&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=ZhuLinsen/daily_stock_analysis&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=ZhuLinsen/daily_stock_analysis&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=ZhuLinsen/daily_stock_analysis&type=Date" />
 </picture>
</a>

## ⚠️ 免責聲明

本项目僅供學習和研究使用，不構成任何投資建議。股市有風險，投資需謹慎。作者不對使用本项目產生的任何損失負責。

---