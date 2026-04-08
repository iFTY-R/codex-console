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
