from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_accounts_page_contains_manual_login_entry_and_modal():
    content = (ROOT / "templates" / "accounts.html").read_text(encoding="utf-8")
    assert "manual-login-open-btn" in content
    assert "manual-login-modal" in content
    assert "manual-login-log" in content
    assert "manual-login-start-btn" in content


def test_accounts_js_contains_manual_login_endpoints():
    content = (ROOT / "static" / "js" / "accounts.js").read_text(encoding="utf-8")
    assert "/accounts/manual-login/start" in content
    assert "/accounts/manual-login/tasks/" in content
    assert "/accounts/manual-login/inbox-code" in content


def test_accounts_page_contains_inbox_preview_modal():
    content = (ROOT / "templates" / "accounts.html").read_text(encoding="utf-8")
    assert "account-inbox-modal" in content
    assert "account-inbox-list" in content
    assert "refresh-account-inbox-btn" in content


def test_accounts_js_contains_inbox_preview_entrypoints():
    content = (ROOT / "static" / "js" / "accounts.js").read_text(encoding="utf-8")
    assert "openAccountInbox" in content
    assert "toggleAccountInboxMessageDetails" in content
    assert "/accounts/${currentAccountInboxId}/inbox?limit=5" in content


def test_accounts_js_contains_per_account_relogin_entry():
    content = (ROOT / "static" / "js" / "accounts.js").read_text(encoding="utf-8")
    assert "reloginAccount(" in content
    assert "已为 ${account.email} 填充重新登录信息" in content
    assert ">重新登录<" in content


def test_accounts_js_contains_workspace_monitor_rendering():
    content = (ROOT / "static" / "js" / "accounts.js").read_text(encoding="utf-8")
    assert "renderManualLoginWorkspaceSummary" in content
    assert "当前选中：" in content
    assert "可见数量：" in content
