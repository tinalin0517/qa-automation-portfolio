# AI Test Assistant — 技術文件

## 目錄

1. [專案概述](#1-專案概述)
2. [技術架構](#2-技術架構)
3. [專案結構](#3-專案結構)
4. [環境設定](#4-環境設定)
5. [功能模組：Bug Analyzer](#5-功能模組bug-analyzer)
6. [功能模組：Spec-Based Test Automation](#6-功能模組spec-based-test-automation)
7. [API 文件](#7-api-文件)
8. [前端架構](#8-前端架構)
9. [截圖貼上功能實作](#9-截圖貼上功能實作)
10. [Excel 匯出實作](#10-excel-匯出實作)
11. [依賴套件](#11-依賴套件)

---

## 1. 專案概述

AI Test Assistant 是一個 AI 驅動的測試輔助工具，整合 Anthropic Claude API 與 OpenSearch，提供兩大核心功能：

| 功能 | 說明 |
|------|------|
| **Bug Analyzer** | 輸入關鍵字或貼上 error log，自動查詢 OpenSearch 並透過 Claude 分析 root cause 與排查建議 |
| **Spec-Based Test Automation** | 上傳規格文件或貼上 User Story，Claude 自動產出完整測試場景清單，可匯出為 Markdown 或 Excel |

---

## 2. 技術架構

```
┌─────────────────────────────────────────────┐
│                  Browser                    │
│  index.html  +  static/style.css            │
│  (單頁應用，三個主要頁面)                     │
└──────────────────┬──────────────────────────┘
                   │ HTTP
┌──────────────────▼──────────────────────────┐
│              Flask 3.x (app.py)             │
│  GET /        POST /analyze                 │
│  POST /spec-analyze  POST /spec-export-excel│
└──────┬────────────────────┬─────────────────┘
       │                    │
┌──────▼──────┐    ┌────────▼────────────────┐
│  analyzer.py│    │   opensearch_client.py  │
│             │    │   refresh_cookie.py     │
│  Claude API │    │                         │
│  (Anthropic)│    │   OpenSearch Dashboard  │
└─────────────┘    └─────────────────────────┘
```

**技術選型：**

| 層 | 技術 | 版本 |
|----|------|------|
| 語言 | Python | 3.9+ |
| Web 框架 | Flask | 3.1.3 |
| AI 模型 | claude-sonnet-4-6 | Anthropic API |
| Log 查詢 | OpenSearch | — |
| Word 解析 | python-docx | — |
| PDF 解析 | pypdf | — |
| Excel 匯出 | openpyxl | 3.1.5 |
| 前端 Icons | Tabler Icons | 3.x (CDN) |

---

## 3. 專案結構

```
ai-qa-assistant/
├── app.py                  # Flask 主程式，定義所有路由
├── analyzer.py             # Claude AI 分析邏輯
├── opensearch_client.py    # OpenSearch 查詢（選用，本機 demo）
├── refresh_cookie.py       # 本機 demo session 更新
├── requirements.txt        # Python 依賴
├── .env                    # 環境變數（不進版控）
├── .env.example            # 環境變數範本
├── templates/
│   └── index.html          # 前端單頁應用（HTML + JS）
└── static/
    └── style.css           # 前端樣式
```

---

## 4. 環境設定

### 4.1 環境變數

複製 `.env.example` 為 `.env` 並填入以下參數：

```env
ANTHROPIC_API_KEY=your_anthropic_api_key       # Anthropic API 金鑰
OPENSEARCH_HOST=opensearch-demo.example.com  # OpenSearch 主機（不含 https://）
OPENSEARCH_COOKIE=your_session_cookie # OpenSearch Dashboard session cookie
```

### 4.2 安裝與啟動

```bash
# 建立虛擬環境
python3 -m venv venv
source venv/bin/activate

# 安裝依賴
pip install -r requirements.txt

# 啟動伺服器（預設 port 5001）
python app.py
```

前端入口：`http://127.0.0.1:5001`

---

## 5. 功能模組：Bug Analyzer

### 流程

```
使用者輸入關鍵字 / error log
        │
        ▼
  opensearch_client.py
  search_logs(keyword, time_range)
        │
        ▼ raw log 字串
  analyzer.analyze_log(log_content, context)
        │
        ▼ JSON
  前端渲染結果（root cause / details / solutions）
```

### `analyze_log` 輸出格式

```json
{
  "rootCause": "一句話說明核心問題",
  "details": ["錯誤意思", "最常見原因"],
  "solutions": ["方案 1：...", "方案 2：..."],
  "recommendation": "建議採用方案 X，理由..."
}
```

### Claude client 設定

```python
# timeout 30s，適合快速的 log 分析
client = anthropic.Anthropic(api_key=..., timeout=30.0)
```

---

## 6. 功能模組：Spec-Based Test Automation

### 6.1 支援的輸入格式

| 格式 | 解析方式 |
|------|----------|
| `.docx` | python-docx 提取段落文字 |
| `.pdf` | pypdf PdfReader 提取每頁文字 |
| `.md` / `.txt` / `.yaml` / `.yml` | UTF-8 直接讀取 |
| `.png` / `.jpg` / `.jpeg` / `.webp` | Claude Vision API 提取文字 |
| 剪貼簿截圖 | 瀏覽器 Clipboard API → 自動命名 → 同圖片流程 |

### 6.2 三步驟流程

```
Step 1：上傳規格文件（支援多檔 + 截圖貼上 + 文字輸入）
        │
        ▼
Step 2：設定產出規則（測試類型 / BDD / 優先級 / 測試資料）
        │
        ▼
Step 3：產出測試場景 → 渲染結果 → 匯出 Excel / Markdown
```

### 6.3 測試場景類型

| 類型 | ID 前綴 | Badge 顏色 |
|------|---------|-----------|
| Happy Path | TC-HP | 綠色 (success) |
| Edge Cases | TC-EC | 橘色 (warning) |
| Error Handling | TC-EH | 紅色 (danger) |
| Security | TC-SEC | 藍色 (info) |
| Performance | TC-PERF | 灰色 (secondary) |
| Regression | TC-REG | 灰色 (secondary) |

### 6.4 `analyze_spec` 輸出格式

```json
{
  "groups": [
    {
      "name": "Happy Path",
      "badgeLabel": "正常流程",
      "badgeType": "success",
      "cases": [
        {
          "id": "TC-HP-001",
          "name": "測試案例名稱",
          "exp": "Given ... When ... Then ...",
          "tags": ["tag1", "tag2"],
          "priority": "P1"
        }
      ]
    }
  ],
  "stats": {
    "total": 18,
    "p1": 5,
    "types": 3,
    "specs": 42
  }
}
```

### 6.5 進階選項

| 選項 | 預設 | 效果 |
|------|------|------|
| BDD 格式 | ON | `exp` 欄位使用 Given/When/Then |
| 優先級標記 | ON | 依風險填入 P1/P2/P3 |
| 測試資料 | OFF | `exp` 結尾加具體輸入值與預期輸出 |

### 6.6 Claude client 設定

```python
# timeout 120s，spec 分析產出較慢
spec_client = anthropic.Anthropic(api_key=..., timeout=120.0)
```

---

## 7. API 文件

### `GET /`

回傳前端 HTML 頁面。

---

### `POST /analyze`

Bug 分析。

**Request body（JSON）：**

```json
{
  "keyword": "OOM error",
  "errorLog": "java.lang.OutOfMemoryError: ...",
  "context": "這發生在每天 02:00 的排程任務",
  "timeRange": "24h"
}
```

> `keyword` 和 `errorLog` 至少提供一個。`timeRange` 選填，傳給 OpenSearch 過濾時間範圍。

**Response（JSON）：**

```json
{
  "rootCause": "...",
  "details": ["...", "..."],
  "solutions": ["...", "..."],
  "recommendation": "...",
  "rawLogs": "OpenSearch 原始查詢結果"
}
```

---

### `POST /spec-analyze`

Spec 轉測試場景。Content-Type: `multipart/form-data`

**Form fields：**

| 欄位 | 類型 | 說明 |
|------|------|------|
| `files` | File（可多個） | 規格文件（.docx/.pdf/.md/.txt/.yaml/.png/.jpg/.webp） |
| `specText` | string | 手動貼上的規格文字（選填） |
| `types` | JSON string | 測試類型陣列，如 `["Happy Path","Edge Cases"]` |
| `bdd` | `"true"/"false"` | 是否使用 BDD 格式，預設 `"true"` |
| `priority` | `"true"/"false"` | 是否標記優先級，預設 `"true"` |
| `testData` | `"true"/"false"` | 是否加測試資料，預設 `"false"` |

> `files` 和 `specText` 至少提供一個。

**Response：** 見 [6.4 analyze_spec 輸出格式](#64-analyze_spec-輸出格式)

---

### `POST /spec-export-excel`

將測試場景 JSON 匯出為樣式化 Excel。Content-Type: `application/json`

**Request body：**

```json
{
  "groups": [ ... ]
}
```

> 格式與 `/spec-analyze` 回傳的 `groups` 相同。

**Response：** `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
下載檔名：`test-scenarios.xlsx`

---

## 8. 前端架構

### 8.1 頁面結構

```
index.html（單頁應用）
├── homePage         首頁，選擇工具
├── inputPage        Bug Analyzer 輸入 + 結果頁
└── specPage         Spec 工具
    ├── spp1 (Step 1) 上傳規格文件
    ├── spp2 (Step 2) 設定產出規則
    └── spp3 (Step 3) 進度顯示 + 結果 + 匯出
```

### 8.2 命名規範

前端所有 Spec 相關的 JS / HTML / CSS 都帶有前綴，避免命名衝突：

| 層 | 前綴 | 範例 |
|----|------|------|
| JavaScript 函數 | `sp` | `spGoStep()`, `spGenerateTests()` |
| HTML id | `sp` | `spDropZone`, `spFileItems` |
| CSS class | `sp-` | `sp-page`, `sp-prog-step` |
| CSS 作用域 | `#specPage` | `#specPage .drop-zone { ... }` |

### 8.3 多檔上傳實作

```javascript
const spSelectedFiles = [];  // 全域陣列，跨函數共享

// 事件委派：刪除按鈕用 data-del attribute 而非 inline onclick
items.addEventListener('click', e => {
  const btn = e.target.closest('[data-del]');
  if (!btn) return;
  spRemoveFile(parseInt(btn.dataset.del, 10));
});
```

檔案 → `spHandleFiles()` → `spSelectedFiles[]` → `spRenderFileList()` → DOM 更新

上傳時：
```javascript
spSelectedFiles.forEach(file => form.append('files', file));
```

### 8.4 樣式架構

CSS 分離至 `static/style.css`，透過 Jinja2 `url_for` 引入：

```html
<link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
```

CSS 分區（按頁面/元件）：

```
Reset & Variables → Layout → Topbar → Home Page →
Input Page → Output Page → Spec Page
  ├── Steps  ├── Drop Zone  ├── File Preview
  ├── Config Cards  ├── Toggle Rows
  ├── Output Stats  ├── Test Case Groups
  └── Progress Steps
```

---

## 9. 截圖貼上功能實作

### 9.1 功能說明

在 Spec 工具第一步，使用者可直接按 `⌘V`（macOS）或 `Ctrl+V`（Windows）貼上：
- **截圖**（Cmd+Shift+4、系統截圖工具）
- **從 Finder 複製的檔案**

### 9.2 前端實作

```javascript
// 在 spInitDropZone() 內註冊，只在 specPage Step 1 生效
document.addEventListener('paste', e => {
  if (!document.getElementById('specPage').classList.contains('active')) return;
  if (!document.getElementById('spp1').classList.contains('active')) return;

  const clipItems = e.clipboardData?.items;
  if (!clipItems) return;

  const files = [];
  for (const item of clipItems) {
    if (item.kind !== 'file') continue;
    const file = item.getAsFile();
    if (!file) continue;

    // 截圖沒有名稱，自動命名為 screenshot_YYYY-MM-DDTHH-MM-SS.png
    if (!file.name || file.name === 'image.png') {
      const ts  = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-');
      const ext = file.type.split('/')[1] || 'png';
      files.push(new File([file], `screenshot_${ts}.${ext}`, { type: file.type }));
    } else {
      files.push(file);
    }
  }

  if (files.length) {
    e.preventDefault();
    spHandleFiles(files);
    // 閃爍 drop zone 提供視覺回饋
    dz.classList.add('drag-over');
    setTimeout(() => dz.classList.remove('drag-over'), 600);
  }
});
```

**關鍵設計決策：**

1. **條件觸發**：paste 事件在 `document` 上監聽，但用 `classList.contains('active')` 限制只在 Step 1 有效，不干擾其他頁面（如規格文字 textarea 的一般貼上）。

2. **自動命名**：系統截圖傳入 Clipboard API 時 `file.name` 為空或為 `"image.png"`，用 ISO 時間戳自動命名，確保多張截圖不重名也不被去重邏輯跳過。

3. **視覺回饋**：貼上成功後 drop zone 短暫套用 `drag-over` 樣式（綠色邊框）600ms，讓使用者確認操作生效。

4. **統一流程**：貼上的檔案直接傳入 `spHandleFiles()`，與拖曳、點擊選擇走完全相同的驗證、去重、渲染流程。

### 9.3 後端實作

`analyzer.py` — `extract_image_text()`：

```python
def extract_image_text(image_bytes: bytes, media_type: str) -> str:
    img_b64 = base64.b64encode(image_bytes).decode("utf-8")
    resp = spec_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,  # "image/png" / "image/jpeg" 等
                        "data": img_b64
                    }
                },
                {
                    "type": "text",
                    "text": "請完整提取這張圖片中所有可見的文字內容，保留原始結構與格式..."
                }
            ]
        }]
    )
    return resp.content[0].text
```

`app.py` — `/spec-analyze` 路由的圖片分支：

```python
elif ext in ("png", "jpg", "jpeg", "webp"):
    media_type = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    text = extract_image_text(uploaded.read(), media_type)
```

提取後的文字與其他檔案文字合併，一起送進 `analyze_spec()` 進行測試場景生成。

### 9.4 支援格式對照

| 輸入方式 | MIME type | 後端處理 |
|----------|-----------|----------|
| 截圖（Cmd+Shift+4） | `image/png` | Claude Vision → 文字 |
| JPEG 圖片 | `image/jpeg` | Claude Vision → 文字 |
| WebP 圖片 | `image/webp` | Claude Vision → 文字 |
| 從 Finder 複製的 .docx | `application/...` | python-docx |
| 從 Finder 複製的 .pdf | `application/pdf` | pypdf |

---

## 10. Excel 匯出實作

### 10.1 工作表結構

匯出的 `.xlsx` 包含兩個工作表：

**工作表一：測試場景**

| Row | 說明 |
|-----|------|
| 1 | 標題列（深綠底白字，合併 A~F） |
| 2 | 統計列（產生時間、總場景數、P1 數、類型數） |
| 3 | 分隔線（純黑色細條） |
| 4 | 欄位標題（開啟自動篩選、凍結此行以下） |
| 5+ | 每個 group 先一行 group header，再逐條 case |

欄位：`A 編號 | B 測試類型 | C 名稱 | D 驗證步驟 | E Tags | F 優先級`

**工作表二：摘要**

整體統計數字 + 各類型場景數量分佈。

### 10.2 深色主題色盤

```python
C = dict(
    title_bg="085041", title_fg="FFFFFF",   # 深綠色標題
    hdr_bg="0D6652",   hdr_fg="FFFFFF",     # 欄位標題
    row_a="1C1C1F",    row_b="141416",      # 交替行
    hp_bg="0D3326",  hp_fg="4ECB9A",        # Happy Path（綠）
    ec_bg="2A1E06",  ec_fg="E8B84B",        # Edge Cases（橘）
    eh_bg="2D1212",  eh_fg="F08080",        # Error Handling（紅）
    p1_bg="3D1510",  p1_fg="F08080",        # P1（紅）
    p2_bg="2A1E06",  p2_fg="E8B84B",        # P2（橘）
    p3_bg="0D1F38",  p3_fg="6AAEE8",        # P3（藍）
)
```

---

## 11. 依賴套件

```
Flask==3.1.3          Web 框架
anthropic==0.97.0     Claude API SDK（含 Vision 支援）
python-dotenv==1.2.1  環境變數讀取
openpyxl==3.1.5       Excel 生成
pypdf                 PDF 解析
python-docx           Word 解析
```

> **注意**：`pypdf` 為 `PyPDF2` 的繼任套件，import 語法為 `from pypdf import PdfReader`。
