# 貢獻指南

感謝你對本專案的關注！歡迎任何形式的貢獻。

## 🐛 報告 Bug

1. 先搜尋 [Issues](https://github.com/ZhuLinsen/daily_stock_analysis/issues) 確認問題未被報告
2. 使用 Bug Report 模板建立新 Issue
3. 提供詳細的複現步驟和環境資訊

## 💡 功能建議

1. 先搜尋 Issues 確認建議未被提出
2. 使用 Feature Request 模板建立新 Issue
3. 詳細描述你的使用場景和期望功能

## 🔧 提交程式碼

### 開發環境

```bash
# 克隆倉庫
git clone https://github.com/ZhuLinsen/daily_stock_analysis.git
cd daily_stock_analysis

# 建立虛擬環境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 安裝依賴
pip install -r requirements.txt

# 配置環境變數
cp .env.example .env
```

### 提交流程

1. Fork 本倉庫
2. 建立特性分支：`git checkout -b feature/your-feature`
3. 提交改動：`git commit -m 'feat: add some feature'`
4. 推送分支：`git push origin feature/your-feature`
5. 建立 Pull Request

### Commit 規範

使用 [Conventional Commits](https://www.conventionalcommits.org/) 規範：

```
feat: 新功能
fix: Bug 修復
docs: 文檔更新
style: 程式碼格式（不影響功能）
refactor: 重構
perf: 性能優化
test: 測試相關
chore: 建置/工具相關
```

範例：
```
feat: 添加釘釘機器人支持
fix: 修復 429 限流重試邏輯
docs: 更新 README 部署說明
```

### 程式碼規範

- Python 程式碼遵循 PEP 8
- 函式和類別需要添加 docstring
- 重要邏輯添加註釋
- 新功能需要更新相關文檔

### CI 自動檢查

提交 PR 後，CI 會自動運行以下檢查：

| 檢查項 | 說明 | 必須通過 |
|--------|------|:--------:|
| 🐍 語法檢查 | Python 語法正確性 | ✅ |
| 📦 依賴安裝 | Python 3.10/3.11/3.12 多版本測試 | ✅ |
| 🐳 Docker 建置 | Docker 映像檔能正常建置 | ✅ |
| 🔍 程式碼規範 | Black/Flake8/isort 格式檢查 | ⚠️ 警告 |
| 🔒 安全檢查 | Bandit/Safety 漏洞掃描 | ⚠️ 警告 |
| 🧪 單元測試 | pytest 測試（如有） | ✅ |

**本地運行檢查：**

```bash
# 安裝檢查工具
pip install black flake8 isort bandit

# 程式碼格式化
black .
isort .

# 靜態檢查
flake8 .

# 安全掃描
bandit -r . -x ./test_*.py
```

## 📋 優先貢獻方向

查看 [Roadmap](README.md#-roadmap) 了解當前需要的功能：

- 🔔 新通知管道（釘釘、飛書、Telegram）
- 🤖 新 AI 模型支持（GPT-4、Claude）
- 📊 新數據源接入
- 🐛 Bug 修復和性能優化
- 📖 文檔完善和翻譯

## ❓ 問題解答

如有任何問題，歡迎：
- 建立 Issue 討論
- 查看已有 Issue 和 Discussion

再次感謝你的貢獻！ 🎉
