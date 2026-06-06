# AI Test Assistant

> Portfolio safety note: All data, endpoints, service names, API responses, logs, and code references in this repository are mock/demo data for portfolio demonstration only. Do not commit real company URLs, cookies, API keys, tokens, database credentials, customer data, or internal screenshots.


AI 驅動的測試輔助工具，整合 Anthropic Claude API 與 OpenSearch，提供四大核心功能，協助 QA 工程師加速 Bug 分析與測試場景產出。

---

## 功能總覽

### 🐛 Bug Analyzer
- 輸入 EventId（數字）、Hex UUID 或關鍵字，自動查詢 OpenSearch logs
- 支援手動貼上 error log / API response 直接分析
- 支援多檔上傳（.txt、.log）及圖片 OCR（.png / .jpg / .webp）
- 支援時間範圍篩選（15 分鐘 / 1 小時 / 24 小時 / 7 天）
- Claude 回傳 **root cause**、錯誤說明與具體排查方案，並標注參考的 Controller 程式碼（codeRefs）
- 分析結果可複製或匯出為 `.txt` 報告

### 📋 Spec-Based Test Automation
- 上傳規格文件（`.docx` / `.pdf` / `.md` / `.txt` / `.yaml`）或貼上 User Story / AC
- 支援多檔上傳，同時分析多份規格
- 選擇測試類型：Happy Path、Edge Cases、Error Handling、Security、Performance、Regression
- 進階選項：Gherkin BDD 格式、優先級標注（P1/P2/P3）、測試資料建議
- Claude 自動產出完整測試場景清單，附進度動畫（3 步驟進度卡）
- 匯出為 **Markdown** 或帶樣式的 **Excel**（`.xlsx`）

### 🔍 Test Case Deduplication
- 上傳現有測試案例，自動偵測重複或高度相似的項目
- Claude 回傳去重建議，保留覆蓋率最廣的案例

### ✨ Test Case Optimization
- 上傳測試案例，Claude 評估品質並提出改寫建議
- 優化描述、補充邊界條件、提升可讀性

---

## 技術架構

```
┌─────────────────────────────────────────────────────────┐
│                     Browser (SPA)                       │
│          Vanilla JS · 4-page single HTML app            │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP (JSON / multipart)
┌────────────────────────▼────────────────────────────────┐
│                    Flask 3.x (app.py)                   │
│   /analyze  /spec-analyze  /dedup-analyze               │
│   /optimize-analyze  /spec-export-excel                 │
└────┬──────────────────┬─────────────────────────────────┘
     │                  │
     ▼                  ▼
┌─────────┐    ┌────────────────────────────────────────┐
│OpenSearch│    │         analyzer.py                    │
│  Client  │    │  analyze_log()    analyze_spec()       │
│(cookie   │    │  deduplicate_cases()                   │
│ auth +   │    │  optimize_cases()                      │
│ auto-    │    │  build_code_index(*zips)               │
│ refresh) │    │  extract_image_text()  ← Claude vision │
└─────────┘    └────────────────┬───────────────────────┘
                                │
                         ┌──────▼──────┐
                         │ Claude API  │
                         │(Anthropic)  │
                         └─────────────┘
```

| 項目 | 技術 |
|------|------|
| 後端框架 | Flask 3.x (Python) |
| AI 分析 | Anthropic Claude API（claude-sonnet-4-6） |
| Log 查詢 | OpenSearch（選用：cookie 認證；預設可使用手動 / mock log） |
| 文件解析 | python-docx、pypdf |
| 圖片 OCR | Claude Vision API |
| Excel 匯出 | openpyxl |
| 程式碼索引 | 解析 Java zip 檔，提取 Spring Controller endpoint |
| Cookie 更新 | 選用，本機 demo 用 agent-browser |

---

## 專案結構

```
├── app.py                   # Flask 主程式，所有路由入口
├── analyzer.py              # 核心 AI 分析邏輯
│   ├── build_code_index()   # 解析 Java zip → Controller endpoint map
│   ├── analyze_log()        # Bug 分析（含 codeRefs）
│   ├── analyze_spec()       # Spec → 測試場景
│   ├── deduplicate_cases()  # 測試案例去重
│   ├── optimize_cases()     # 測試案例優化
│   └── extract_image_text() # Claude Vision OCR
├── opensearch_client.py     # OpenSearch 查詢（選用：EventId / UUID / keyword）
├── refresh_cookie.py        # 選用：本機 demo session 更新
├── templates/
│   └── index.html           # 前端 SPA（homePage / inputPage / outputPage / specPage）
├── static/
│   └── style.css            # 前端樣式
├── requirements.txt
├── .env.example             # 環境變數範本
└── .gitignore
```

---

## 快速開始

```bash
# 1. 建立虛擬環境並安裝套件
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. 設定環境變數
cp .env.example .env
# 編輯 .env，填入 ANTHROPIC_API_KEY 與 OpenSearch 連線資訊

# 3. 啟動伺服器（預設 port 5001）
python app.py
```

開啟瀏覽器前往 [http://127.0.0.1:5001](http://127.0.0.1:5001)

---

## 環境變數

| 變數 | 必要 | 說明 |
|------|------|------|
| `ANTHROPIC_API_KEY` | ✅ | Anthropic API 金鑰 |
| `OPENSEARCH_HOST` | 選用 | OpenSearch 主機位址（不含 `https://`） |
| `OPENSEARCH_COOKIE` | 選用 | OpenSearch Dashboard session cookie |
| `PAYMENT_CODE_ZIP` | 選用 | 支付模組 Java 原始碼 zip（用於 codeRefs） |
| `PRICING_CODE_ZIP` | 選用 | 定價模組 Java 原始碼 zip（用於 codeRefs） |
| `OPENSEARCH_SSO_PROVIDER` | 選用 | SSO provider 名稱（用於 cookie 自動更新） |
| `OPENSEARCH_SSO_AD_BUTTON` | 選用 | AD 登入按鈕文字（用於 cookie 自動更新） |

> 未設定 OpenSearch 相關變數時，Bug Analyzer 僅支援手動貼上 log，不支援自動查詢。

---

## API 路由

| 路由 | 方法 | 說明 |
|------|------|------|
| `GET /` | GET | 前端頁面 |
| `/analyze` | POST JSON | Bug 分析：keyword / errorLog / context / timeRange |
| `/spec-analyze` | POST multipart | Spec 轉測試場景：files / specText / types / bdd / priority / testData |
| `/spec-export-excel` | POST JSON | 測試場景 JSON 匯出為樣式化 Excel |
| `/dedup-analyze` | POST multipart | 測試案例去重分析 |
| `/optimize-analyze` | POST multipart | 測試案例品質優化分析 |

---

## codeRefs 功能說明

將 Java 後端程式碼（zip）放置於專案根目錄，啟動時自動建立 Controller endpoint 索引。
分析 Bug 或 Spec 時，Claude 會標注參考了哪些 Controller 方法，方便開發者追蹤問題根源。

支援的 domain 對應邏輯（依關鍵字自動分類）：
- `deposit`、`withdraw`、`transfer`、`fund`、`callback`、`pricing`

---

## Cookie 自動更新

OpenSearch integration is optional. For portfolio demo purposes, the project supports manual log input and mock log data by default. `refresh_cookie.py` is kept only as a local demo helper; do not commit real cookies, session files, or internal URLs.

初次使用需手動完成登入並儲存 session：

```bash
agent-browser --state .claude/opensearch-session.json open "https://<your-opensearch-host>/_dashboards/app/home"
```

若登入需要 MFA，自動更新會失敗並通知使用者手動重新登入。
