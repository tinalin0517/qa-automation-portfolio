#!/usr/bin/env python3
"""
自動更新 OpenSearch cookie。
偵測到 session 過期時，用 agent-browser 重新登入並更新 .env。
若需要 MFA，返回 False 讓 opensearch_client 通知使用者。
"""
import json
import os
import re
import subprocess
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_PATH = os.path.join(BASE_DIR, ".claude", "opensearch-session.json")
ENV_PATH = os.path.join(BASE_DIR, ".env")

# Load host from .env so no credentials are hardcoded
from dotenv import load_dotenv
load_dotenv()
OPENSEARCH_HOST = os.environ.get("OPENSEARCH_HOST", "opensearch-demo.example.com")
DASHBOARD_URL = f"https://{OPENSEARCH_HOST}/_dashboards/app/home"


def run(cmd, timeout=30):
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout.strip()


def is_on_dashboard(snapshot):
    """判斷目前是否真正在 Dashboard（非 auth error 頁）"""
    auth_error_signs = ["Sorry!", "Authentication Error", "Log in to OpenSearch", "Invalid signature"]
    return not any(s in snapshot for s in auth_error_signs)


def update_env_cookie(cookie_str):
    with open(ENV_PATH, "r") as f:
        content = f.read()
    new_content = re.sub(r"OPENSEARCH_COOKIE=.*", f"OPENSEARCH_COOKIE={cookie_str}", content)
    with open(ENV_PATH, "w") as f:
        f.write(new_content)


def extract_and_save_cookie():
    run(["agent-browser", "state", "save", SESSION_PATH])
    with open(SESSION_PATH) as f:
        data = json.load(f)
    cookies = [c for c in data.get("cookies", []) if OPENSEARCH_HOST.split("/")[0] in c.get("domain", "")]
    if not cookies:
        return False
    cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
    update_env_cookie(cookie_str)
    return True


def wait_for_dashboard(max_retries=3):
    """等待頁面完成，回傳 (snapshot, url)"""
    run(["agent-browser", "wait", "--load", "networkidle"], timeout=20)
    _, url = run(["agent-browser", "get", "url"])
    _, snapshot = run(["agent-browser", "snapshot", "-i"])
    return snapshot, url


def click_ref_containing(snapshot, keyword):
    """在 snapshot 中找含 keyword 的元素並點擊"""
    for line in snapshot.splitlines():
        if keyword.lower() in line.lower() and "ref=" in line:
            m = re.search(r"ref=(e\d+)", line)
            if m:
                run(["agent-browser", "click", f"@{m.group(1)}"])
                return True
    return False


def refresh():
    # 關掉舊 session，用 saved state 重新開
    run(["agent-browser", "close"])
    run(["agent-browser", "--state", SESSION_PATH, "open", DASHBOARD_URL], timeout=15)
    snapshot, url = wait_for_dashboard()

    # 已在真正的 Dashboard
    if is_on_dashboard(snapshot):
        return extract_and_save_cookie(), None

    # Auth error 頁：點 "Log in" 按鈕
    click_ref_containing(snapshot, "Log in")
    snapshot, url = wait_for_dashboard()

    # Cognito 記住上次登入：有「Sign in with <SSO provider>」
    SSO_PROVIDER = os.environ.get("OPENSEARCH_SSO_PROVIDER", "")
    if SSO_PROVIDER and SSO_PROVIDER.lower() in snapshot.lower():
        click_ref_containing(snapshot, SSO_PROVIDER)
        snapshot, url = wait_for_dashboard()

    # SSO 頁面：點 AD 登入選項（Microsoft SSO，通常不需密碼）
    SSO_AD_BUTTON = os.environ.get("OPENSEARCH_SSO_AD_BUTTON", "")
    if SSO_AD_BUTTON and SSO_AD_BUTTON in snapshot:
        click_ref_containing(snapshot, SSO_AD_BUTTON)
        snapshot, url = wait_for_dashboard()

    # 需要 MFA：無法自動完成
    if "核准登入要求" in snapshot or "Approve sign" in snapshot:
        return False, "需要 MFA 核准，請告知 Claude 重新登入"

    # 需要密碼：無法自動完成
    if "Password" in snapshot or "password" in snapshot or "密碼" in snapshot:
        return False, "需要輸入密碼，請告知 Claude 重新登入"

    # 選 tenant dialog
    if "Select your tenant" in snapshot or "Global" in snapshot:
        click_ref_containing(snapshot, "Confirm")
        snapshot, url = wait_for_dashboard()

    if is_on_dashboard(snapshot):
        return extract_and_save_cookie(), None

    return False, f"自動登入失敗（目前頁面：{url}），請告知 Claude 重新登入"


if __name__ == "__main__":
    success, msg = refresh()
    if success:
        print("Cookie 更新成功")
        sys.exit(0)
    else:
        print(msg or "失敗", file=sys.stderr)
        sys.exit(1)
