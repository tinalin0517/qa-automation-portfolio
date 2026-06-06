import os
import json
import subprocess
import requests
from dotenv import load_dotenv

load_dotenv()

OPENSEARCH_HOST = os.environ.get('OPENSEARCH_HOST', '').strip()
OPENSEARCH_BASE = f"https://{OPENSEARCH_HOST}/_dashboards" if OPENSEARCH_HOST else ''


def _make_headers():
    load_dotenv(override=True)
    return {
        "Cookie": os.environ.get("OPENSEARCH_COOKIE"),
        "Content-Type": "application/json",
        "osd-xsrf": "true",
    }


def _is_auth_error(res):
    if res.status_code in (401, 403):
        return True
    content_type = res.headers.get("Content-Type", "")
    if "text/html" in content_type:
        return True
    if any(s in res.text[:500] for s in ["Authentication Error", "Sign-in", "Log in to OpenSearch"]):
        return True
    return False


def _try_refresh_cookie():
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "refresh_cookie.py")
    result = subprocess.run(["python", script], capture_output=True, text=True, timeout=90)
    return result.returncode == 0, result.stderr.strip() or result.stdout.strip()


def search_logs(keyword, size=50, time_range=""):
    headers = _make_headers()

    import re
    kw = keyword.strip()
    is_numeric_id = kw.isdigit()
    is_hex_id = bool(re.fullmatch(r'[0-9a-fA-F]{16,64}', kw))

    sort = [{"time": {"order": "desc", "missing": "_last", "unmapped_type": "keyword"}}]
    range_filter = [{"range": {"@timestamp": {"gte": time_range, "lte": "now"}}}] if time_range else []

    if is_numeric_id:
        base_query = {"term": {"EventId": int(kw)}}
        query = {
            "size": size,
            "sort": sort,
            "query": {"bool": {"must": [base_query], "filter": range_filter}} if range_filter else {"term": {"EventId": int(kw)}}
        }
    elif is_hex_id:
        search_terms = [kw]
        if len(kw) == 32:
            uuid_fmt = f"{kw[0:8]}-{kw[8:12]}-{kw[12:16]}-{kw[16:20]}-{kw[20:]}"
            search_terms.append(uuid_fmt)
        should_clauses = (
            [{"term": {"EventId.keyword": f"[{t}]"}} for t in search_terms] +
            [{"match_phrase": {"log": t}} for t in search_terms]
        )
        query = {
            "size": size,
            "sort": sort,
            "track_total_hits": True,
            "query": {
                "bool": {
                    "should": should_clauses,
                    "minimum_should_match": 1,
                    "filter": range_filter
                }
            }
        }
    else:
        query = {
            "size": size,
            "sort": sort,
            "query": {
                "bool": {
                    "must": [{"multi_match": {"query": kw, "fields": ["message", "log", "error", "msg"]}}],
                    "filter": range_filter
                }
            }
        }

    if not OPENSEARCH_BASE:
        raise ValueError("OPENSEARCH_HOST is not configured. Use manual log input or set OPENSEARCH_HOST in .env for local demo.")

    url = f"{OPENSEARCH_BASE}/api/console/proxy?path=*/_search&method=POST"
    res = requests.post(url, headers=headers, json=query, timeout=30)

    # Cookie 過期時自動重新整理並重試一次
    if _is_auth_error(res):
        success, msg = _try_refresh_cookie()
        if not success:
            raise Exception(f"Session 過期且自動更新失敗：{msg}")
        headers = _make_headers()
        res = requests.post(url, headers=headers, json=query, timeout=30)

    data = res.json()
    hits = data.get("hits", {}).get("hits", [])
    logs = [h["_source"] for h in hits]

    simplified = []
    for log in logs:
        simplified.append({
            "time": log.get("@timestamp") or log.get("time", ""),
            "service": log.get("source_service") or log.get("service", ""),
            "level": log.get("level", ""),
            "EventId": log.get("EventId", ""),
            "message": log.get("message") or log.get("msg") or log.get("log", ""),
            "error": log.get("error", "")
        })

    log_text = json.dumps(simplified, ensure_ascii=False, indent=2)
    if len(log_text) > 12000:
        log_text = log_text[:12000] + "\n... (截斷，僅顯示前 12000 字元)"

    return log_text
