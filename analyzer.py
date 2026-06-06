import os
import re
import io
import base64
import json
import zipfile
import anthropic
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY"),
    timeout=30.0
)

# spec 分析需要更長時間
spec_client = anthropic.Anthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY"),
    timeout=120.0
)

# ══════════════════════════════════════════════════════════════
#  程式碼索引層
# ══════════════════════════════════════════════════════════════

CODE_INDEX = {}

DOMAIN_MAP = {
    "deposit":  ["deposit", "moneyIn", "cashier", "funddeposit", "userfunddeposit"],
    "withdraw": ["withdraw", "withdrawal", "moneyOut", "fundwithdraw"],
    "transfer": ["transfer", "wallet", "ibportal", "clientportal"],
    "fund":     ["fund", "balance", "account", "fundchange"],
    "callback": ["callback", "notify", "payback", "checkOut"],
    "pricing":  ["price", "pricing", "snapshot", "cache", "backend"],
}

SKIP_PATTERNS = ["test", "mock", "vendor", "node_modules", ".git", "dist", "build"]


def _extract_java_endpoints(source_code):
    mapping_pattern = re.compile(
        r'@(Get|Post|Put|Delete|Patch|Request)?Mapping\s*\(\s*(?:value\s*=\s*)?["\']([^"\']+)["\']'
    )
    method_pattern = re.compile(
        r'(public|private|protected)\s+\S+\s+(\w+)\s*\(([^)]*)\)'
    )
    lines = source_code.split("\n")
    endpoints = []
    for i, line in enumerate(lines):
        m = mapping_pattern.search(line)
        if m:
            method_type = m.group(1) or "Request"
            path = m.group(2)
            for j in range(i, min(i + 5, len(lines))):
                mm = method_pattern.search(lines[j])
                if mm:
                    endpoints.append({
                        "method": method_type.upper(),
                        "path":   path,
                        "name":   mm.group(2),
                        "params": mm.group(3).strip()[:120],
                    })
                    break
    return endpoints


def _infer_domain(text):
    tl = text.lower()
    for domain, keywords in DOMAIN_MAP.items():
        if any(kw.lower() in tl for kw in keywords):
            return domain
    return "other"


def build_code_index(*zip_paths):
    global CODE_INDEX
    CODE_INDEX = {}

    for zip_path in zip_paths:
        if not os.path.exists(zip_path):
            print(f"[Code Index] 找不到 {zip_path}，跳過")
            continue

        # 從 zip 路徑推斷 project prefix（取檔名去除 .zip）
        project_name = os.path.basename(zip_path).replace(".zip", "")

        with zipfile.ZipFile(zip_path) as zf:
            java_files = [
                n for n in zf.namelist()
                if n.endswith(".java")
                and "controller" in n.lower()
                and not any(s in n.lower() for s in SKIP_PATTERNS)
                and not n.startswith("__MACOSX")
            ]
            count = 0
            for path in java_files:
                try:
                    code = zf.read(path).decode("utf-8", errors="replace")
                except Exception:
                    continue
                endpoints = _extract_java_endpoints(code)
                if not endpoints:
                    continue
                short_path = path.split(f"{project_name}/")[-1]
                entry = {
                    "path":      short_path,
                    "endpoints": endpoints,
                    "snippet":   code[:1200],
                }
                domain = _infer_domain(path)
                CODE_INDEX.setdefault(domain, []).append(entry)
                count += 1
            print(f"[Code Index] {project_name}：{count} 個 Controller")

    total = sum(len(v) for v in CODE_INDEX.values())
    print(f"[Code Index] 完成：共 {total} 個 Controller，涵蓋領域：{list(CODE_INDEX.keys())}")


def _get_code_context_with_meta(feature, hint_text="", max_files=4):
    """
    回傳 (context_str, entries_meta)
    entries_meta: [{path, endpoints}] 供層次一 log 與層次二 codeRefs 使用
    """
    if not CODE_INDEX:
        return "", []

    domain = _infer_domain(hint_text)

    if feature == "bug":
        entries = CODE_INDEX.get(domain, [])[:max_files]
        if not entries:
            entries = CODE_INDEX.get("other", [])[:max_files]
    elif feature == "spec":
        entries = CODE_INDEX.get(domain, [])[:max_files]
        if len(entries) < max_files:
            for d, lst in CODE_INDEX.items():
                if d != domain:
                    entries += lst[:2]
                if len(entries) >= max_files:
                    break
        entries = entries[:max_files]
    else:
        entries = []
        for lst in CODE_INDEX.values():
            if lst:
                entries.append(lst[0])
        entries = entries[:max_files]

    if not entries:
        return "", []

    # ── 層次一：terminal log ──────────────────────────────────
    token_est = sum(len(e["snippet"]) // 4 + len(json.dumps(e["endpoints"])) // 4
                    for e in entries)
    print(f"[Code Context] feature={feature}  domain={domain}  hint={hint_text[:60]!r}")
    for e in entries:
        print(f"  → {e['path'].split('/')[-1]}  ({len(e['endpoints'])} endpoints)")
    print(f"[Code Context] token estimate: ~{token_est:,} tokens injected")

    # ── 組 context 字串 ───────────────────────────────────────
    sections = []
    for e in entries:
        ep_json = json.dumps(e["endpoints"], ensure_ascii=False, indent=2)
        sections.append(
            f"### {e['path']}\n"
            f"```json\n{ep_json}\n```\n"
            f"```java\n{e['snippet']}\n```"
        )
    ctx_str = "\n\n".join(sections)

    # entries_meta 供層次二使用（只帶必要欄位，不含 snippet）
    entries_meta = [{"path": e["path"], "endpoints": e["endpoints"]} for e in entries]

    return ctx_str, entries_meta


# ══════════════════════════════════════════════════════════════
#  層次二：codeRefs prompt 片段
# ══════════════════════════════════════════════════════════════

def _code_refs_prompt(entries_meta):
    """
    要求 Claude 在 JSON 結果最後加上 codeRefs，
    說明實際參考了哪些 Controller 及原因。
    """
    if not entries_meta:
        return ""
    files_hint = "\n".join(f"- {e['path']}" for e in entries_meta)
    return f"""
請在 JSON 最後加上 codeRefs 欄位，列出你實際參考了哪些程式碼：
"codeRefs": [
  {{
    "file": "檔案路徑（從上方程式碼中選）",
    "endpoint": "具體的 API 路徑（如 /init_deposit）",
    "method": "HTTP 方法（GET/POST/...）",
    "reason": "一句話說明為什麼這個檔案與此分析相關（繁體中文）"
  }}
]
可選的檔案：
{files_hint}
若某個檔案未被實際參考，不要列入 codeRefs。"""



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
                    "source": {"type": "base64", "media_type": media_type, "data": img_b64}
                },
                {
                    "type": "text",
                    "text": "請完整提取這張圖片中所有可見的文字內容，保留原始結構與格式（標題、列表、表格等），不要添加說明或解釋。若圖片為截圖，請完整轉錄畫面中的文字。"
                }
            ]
        }]
    )
    return resp.content[0].text


# ══════════════════════════════════════════════════════════════
#  Bug Analyzer
# ══════════════════════════════════════════════════════════════

def analyze_log(log_content, context="", keyword=""):
    hint = keyword or context or log_content[:300]
    code_ctx, entries_meta = _get_code_context_with_meta("bug", hint)

    code_section = ""
    if code_ctx:
        code_section = f"""
## 相關程式碼（sample-payment-service）
以下是與此錯誤最相關的 Controller，請對照 endpoint 路徑與參數分析根因：
{code_ctx}
"""

    refs_prompt = _code_refs_prompt(entries_meta)
    context_section = f"## 補充說明\n{context}" if context else ""

    prompt = f"""你是一個幫助開發者快速理解並解決系統錯誤的助手。請分析以下 log，以 JSON 格式回應，只回傳 JSON 不要有其他文字：
{{
  "rootCause": "一句話說明這個錯誤的核心問題是什麼（技術名詞保留英文）",
  "details": [
    "這個錯誤的意思是：解釋錯誤訊息本身代表什麼",
    "最常見的原因是：說明這類錯誤最典型的發生原因"
  ],
  "solutions": [
    "方案 1：具體說明第一種解法，包含要修改的地方和預期效果",
    "方案 2：具體說明第二種解法（如果有的話）"
  ],
  "recommendation": "建議採用哪個方案，以及理由",
  "codeRefs": []
}}

規則：
- 技術名詞、服務名稱、class 名稱、protocol 保留英文
- 說明文字用繁體中文，清楚精簡
- 絕對不可以將 error log 解釋為正常現象
- 每個欄位的字串不可包含換行符號
- solutions 若只有一個方案就只寫一個元素
- 若有提供程式碼，請對照 Controller 路徑與方法名稱說明錯誤位置
{refs_prompt}

## Error Log
{log_content}
{context_section}
{code_section}"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2200,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response.content[0].text
    clean = raw.replace("```json", "").replace("```", "").strip()
    clean = _sanitize_json_strings(clean)
    result = json.loads(clean)

    # 若 Claude 沒有回傳 codeRefs，補空陣列避免前端錯誤
    result.setdefault("codeRefs", [])

    # 層次一：印出 codeRefs 摘要
    if result["codeRefs"]:
        print(f"[codeRefs] Claude 實際參考了 {len(result['codeRefs'])} 個檔案：")
        for r in result["codeRefs"]:
            print(f"  ✓ {r.get('method','')} {r.get('endpoint','')}  ({r.get('file','').split('/')[-1]})")
    else:
        print("[codeRefs] Claude 未回傳程式碼參考（可能 log 與程式碼無直接關聯）")

    return result


# ══════════════════════════════════════════════════════════════
#  Spec-to-Test
# ══════════════════════════════════════════════════════════════

def analyze_spec(spec_content, types, bdd=True, priority=True, test_data=False):
    type_list = "、".join(types) if types else "Happy Path、Edge Cases、Error Handling"
    bdd_rule  = "每個測試場景的 exp 欄位必須使用 Gherkin 格式（Given ... When ... Then ...）" if bdd else "exp 欄位用自然語言描述驗證重點"
    prio_rule = "priority 欄位依風險高低填入 P1/P2/P3（P1 最高）" if priority else "priority 欄位一律填 P2"
    data_rule = "exp 欄位結尾加上【測試資料】具體輸入值與預期輸出範例" if test_data else ""

    code_ctx, entries_meta = _get_code_context_with_meta("spec", spec_content[:400])
    code_section = ""
    if code_ctx:
        code_section = f"""
## 實際程式碼（sample-payment-service Controller）
請根據以下 Controller 的實際 API 路徑、參數名稱與邏輯，確保測試場景與實作一致：
{code_ctx}
"""

    refs_prompt = _code_refs_prompt(entries_meta)

    prompt = f"""你是一個資深 QA 工程師。根據以下規格文件內容，產出完整的測試場景清單，以 JSON 格式回應，只回傳 JSON 不要有其他文字。

需要涵蓋的測試類型：{type_list}

## 規格內容
{spec_content}
{code_section}

JSON 格式如下：
{{
  "groups": [
    {{
      "name": "Happy Path",
      "cases": [
        {{
          "id": "TC-HP-001",
          "name": "測試案例名稱（簡明扼要）",
          "exp": "驗證描述",
          "tags": ["tag1", "tag2"],
          "priority": "P1"
        }}
      ]
    }}
  ],
  "codeRefs": []
}}

規則：
- groups 的 name 只能從以下選：{type_list}
- 每個 group 產出 3～6 個 cases
- {bdd_rule}
- {prio_rule}
- {data_rule}
- 技術名詞、class 名稱、HTTP 方法保留英文
- 說明文字用繁體中文
- 每個字串欄位不可包含換行符號（\\n）
- tags 每個元素最多 15 個字
- 若有提供程式碼，API 路徑與參數必須與程式碼一致
- id 格式：TC-{{類型縮寫}}-{{三位數字}}
{refs_prompt}"""

    response = spec_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4200,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response.content[0].text
    clean = raw.replace("```json", "").replace("```", "").strip()
    clean = _sanitize_json_strings(clean)
    data = json.loads(clean)

    data.setdefault("codeRefs", [])

    # 層次一：印出 codeRefs 摘要
    if data["codeRefs"]:
        print(f"[codeRefs] Claude 實際參考了 {len(data['codeRefs'])} 個檔案：")
        for r in data["codeRefs"]:
            print(f"  ✓ {r.get('method','')} {r.get('endpoint','')}  ({r.get('file','').split('/')[-1]})")
    else:
        print("[codeRefs] Claude 未回傳程式碼參考")

    type_badge_map = {
        "Happy Path":     ("正常流程", "success"),
        "Edge Cases":     ("邊界條件", "warning"),
        "Error Handling": ("錯誤處理", "danger"),
        "Security":       ("安全性",   "info"),
        "Performance":    ("效能",     "secondary"),
        "Regression":     ("迴歸",     "secondary"),
    }
    for g in data.get("groups", []):
        label, btype = type_badge_map.get(g["name"], (g["name"], "secondary"))
        g["badgeLabel"] = label
        g["badgeType"]  = btype

    all_cases = [c for g in data.get("groups", []) for c in g.get("cases", [])]
    p1_count  = sum(1 for c in all_cases if c.get("priority") == "P1")
    data["stats"] = {
        "total": len(all_cases),
        "p1":    p1_count,
        "types": len(data.get("groups", [])),
        "specs": len(spec_content.split("\n")),
    }
    return data


# ══════════════════════════════════════════════════════════════
#  Test Case Deduplicator
# ══════════════════════════════════════════════════════════════

def deduplicate_cases(cases_text):
    code_ctx, entries_meta = _get_code_context_with_meta("dedup", cases_text[:300])
    code_section = ""
    if code_ctx:
        code_section = f"""
## 系統 API 端點（sample-payment-service）
請參考以下端點，判斷功能重疊的測試案例：
{code_ctx}
"""
    refs_prompt = _code_refs_prompt(entries_meta)

    prompt = f"""你是資深 QA 工程師，擅長識別重複或高度相似的測試案例。
請分析以下測試案例，找出重複或可合併的項目，以 JSON 格式回應，只回傳 JSON 不要有其他文字。
{code_section}

測試案例：
{cases_text}

JSON 格式：
{{
  "original_count": 原始測試案例數量,
  "deduplicated_count": 去重後數量,
  "removed_count": 移除數量,
  "groups": [
    {{
      "kept": {{"id": "TC-001", "name": "保留的代表案例名稱", "reason": "保留原因"}},
      "removed": [{{"id": "TC-002", "name": "被合併的案例名稱", "similarity": "相似原因"}}]
    }}
  ],
  "final_cases": [
    {{"id": "TC-001", "name": "最終保留的案例名稱", "note": "涵蓋說明"}}
  ],
  "codeRefs": []
}}

規則：
- 語意相同但描述不同的案例視為重複
- 相同功能不同參數的案例考慮合併
- 若有程式碼參考，以 API endpoint 為單位判斷功能重複性
- 說明文字用繁體中文
- 每個字串欄位不可包含換行符號
{refs_prompt}"""

    response = spec_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response.content[0].text
    clean = raw.replace("```json", "").replace("```", "").strip()
    clean = _sanitize_json_strings(clean)
    result = json.loads(clean)
    result.setdefault("codeRefs", [])

    if result["codeRefs"]:
        print(f"[codeRefs] Claude 實際參考了 {len(result['codeRefs'])} 個檔案")
        for r in result["codeRefs"]:
            print(f"  ✓ {r.get('method','')} {r.get('endpoint','')}  ({r.get('file','').split('/')[-1]})")

    return result


# ══════════════════════════════════════════════════════════════
#  Test Case Optimizer
# ══════════════════════════════════════════════════════════════

def optimize_cases(cases_text):
    code_ctx, entries_meta = _get_code_context_with_meta("optimize", cases_text[:300])
    code_section = ""
    if code_ctx:
        code_section = f"""
## 系統 API 端點（sample-payment-service）
請參考以下端點，確保精簡後仍覆蓋所有核心功能路徑：
{code_ctx}
"""
    refs_prompt = _code_refs_prompt(entries_meta)

    prompt = f"""你是資深 QA 工程師，專精測試策略優化。
請分析以下大量測試案例，產出精簡但高覆蓋的最終版本，以 JSON 格式回應，只回傳 JSON 不要有其他文字。
{code_section}

原始測試案例：
{cases_text}

JSON 格式：
{{
  "original_count": 原始數量,
  "optimized_count": 精簡後數量,
  "coverage_rate": "覆蓋率估計（如 96%）",
  "groups": [
    {{
      "name": "分類名稱",
      "cases": [
        {{"id": "TC-OPT-001", "name": "精簡後案例名稱", "priority": "P1", "covers": "涵蓋說明", "exp": "Given ... When ... Then ..."}}
      ]
    }}
  ],
  "codeRefs": []
}}

規則：
- 保留所有 P1 高優先案例
- 合併功能相似的 P2/P3 案例
- 確保每個核心業務流程至少有一個案例覆蓋
- 若有程式碼，確保每個 API endpoint 至少有一個對應案例
- 說明文字用繁體中文
- 每個字串欄位不可包含換行符號
{refs_prompt}"""

    response = spec_client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response.content[0].text
    clean = raw.replace("```json", "").replace("```", "").strip()
    clean = _sanitize_json_strings(clean)
    result = json.loads(clean)
    result.setdefault("codeRefs", [])

    if result["codeRefs"]:
        print(f"[codeRefs] Claude 實際參考了 {len(result['codeRefs'])} 個檔案")
        for r in result["codeRefs"]:
            print(f"  ✓ {r.get('method','')} {r.get('endpoint','')}  ({r.get('file','').split('/')[-1]})")

    return result


# ══════════════════════════════════════════════════════════════
#  共用工具
# ══════════════════════════════════════════════════════════════

def _sanitize_json_strings(s):
    result = []
    in_string = False
    escape = False
    for ch in s:
        if escape:
            result.append(ch)
            escape = False
        elif ch == "\\":
            result.append(ch)
            escape = True
        elif ch == '"':
            result.append(ch)
            in_string = not in_string
        elif ch in ("\n", "\r") and in_string:
            result.append(" ")
        else:
            result.append(ch)
    return "".join(result)
