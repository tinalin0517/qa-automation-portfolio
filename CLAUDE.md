# 專案簡介
AI 驅動的測試輔助工具，整合 Anthropic Claude API 與 OpenSearch，提供兩大核心功能：
1. **Bug Analyzer**：輸入關鍵字或貼上 error log，自動查詢 OpenSearch 並透過 Claude 分析 root cause 與排查建議。
2. **Spec-Based Test Automation**：上傳規格文件或貼上 User Story，Claude 自動產出完整測試場景清單，可匯出為 Markdown 或 Excel。

# 技術架構
- 語言：Python 3.9+
- 框架：Flask 3.x
- AI：Anthropic Claude API（claude-sonnet-4-6）
- Log 查詢：OpenSearch
- 文件解析：python-docx（.docx）、PyPDF2（.pdf）
- Excel 匯出：openpyxl
- Cookie 自動更新：agent-browser

# 專案結構
- app.py               # Flask 主程式，路由：/analyze、/spec-analyze、/spec-export-excel
- analyzer.py          # Claude 分析邏輯（Bug 分析 / Spec 轉測試場景）
- opensearch_client.py # OpenSearch 查詢（選用，本機 demo）
- refresh_cookie.py    # 本機 demo session 更新
- templates/index.html # 前端 UI（單頁應用，含 Bug Analyzer 與 Spec 工具兩個頁面）

# 環境變數（參考 .env.example）
- ANTHROPIC_API_KEY   # Anthropic API 金鑰
- OPENSEARCH_HOST     # OpenSearch 主機位址（不含 https://）
- OPENSEARCH_COOKIE   # OpenSearch Dashboard session cookie

# 常用指令
- 啟動伺服器：python app.py（預設 port 5001）
- 前端入口：http://127.0.0.1:5001

# API 路由
- GET  /                  # 前端頁面
- POST /analyze           # Bug 分析（JSON body：keyword / errorLog / context / timeRange）
- POST /spec-analyze      # Spec 轉測試場景（multipart：file / specText / types / bdd / priority / testData）
- POST /spec-export-excel # 測試場景 JSON 匯出為樣式化 Excel（JSON body：groups）

# analyzer.py 函數說明

## analyze_log(log_content, context)
回傳 JSON：
- rootCause      # 一句話說明核心問題
- details        # 錯誤說明 + 常見原因（list）
- solutions      # 具體解法列表（list）
- recommendation # 建議採用哪個方案

## analyze_spec(spec_content, types, bdd, priority, test_data)
- types：測試類型清單（Happy Path / Edge Cases / Error Handling / Security / Performance / Regression）
- bdd：True 時 exp 欄位使用 Gherkin 格式（Given / When / Then）
- priority：True 時依風險填入 P1/P2/P3
- test_data：True 時在 exp 結尾加上具體測試資料範例

回傳 JSON：
- groups[].name / badgeLabel / badgeType / cases[]
- cases[].id / name / exp / tags / priority
- stats.total / p1 / types / specs

# Anthropic client 設定
- client（timeout=30s）：用於 Bug 分析
- spec_client（timeout=120s）：用於 Spec 分析（AI 產出需較長時間）

# 前端架構（templates/index.html）
單頁應用，三個主要頁面（page）：
- homePage：首頁，選擇工具
- inputPage：Bug Analyzer 輸入與結果頁
- specPage：Spec 工具，分三步驟：
  - Step 1：上傳規格文件（支援拖曳/點擊，.docx / .pdf / .md / .txt / .yaml）
  - Step 2：選擇測試類型與進階選項
  - Step 3：顯示分析進度（三步驟進度卡 + 進度條）、結果（依 group 展示測試案例）、匯出按鈕

前端 JS 命名規範：
- Spec 頁面所有函數以 sp 為前綴（spGoStep、spGenerateTests、spRenderResults、spExportExcel 等）
- Spec 頁面所有 HTML id 以 sp 為前綴（spDropZone、spFileInput、spExportBtns 等）
- Spec 頁面所有 CSS class 以 sp- 為前綴（sp-page、sp-steps、sp-prog-step 等），並以 #specPage 作用域隔離

# 開發規範
- 技術名詞、class 名稱、服務名稱、HTTP 方法保留英文
- 說明文字用繁體中文
- JSON 欄位字串不可包含換行符號
- 不可將 error log 解釋為正常現象
