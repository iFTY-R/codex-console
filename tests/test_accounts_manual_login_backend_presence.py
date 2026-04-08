from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_accounts_route_contains_manual_login_endpoints():
    content = (ROOT / "src" / "web" / "routes" / "accounts.py").read_text(encoding="utf-8")
    assert '/manual-login/start' in content
    assert '/manual-login/tasks/{task_id}' in content
    assert '/manual-login/tasks/{task_id}/confirm-overwrite' in content
    assert '/manual-login/inbox-code' in content


def test_manual_login_service_contains_core_flow_markers():
    content = (ROOT / "src" / "web" / "services" / "manual_login_service.py").read_text(encoding="utf-8")
    assert 'RegistrationEngine' in content
    assert 'waiting_confirm_overwrite' in content
    assert 'waiting_push_auth' in content
    assert 'refresh_by_session_token' in content
    assert '_persist_login_bundle' in content
    assert '_sync_subscription_after_login' in content
    assert 'check_subscription_status_detail' in content
    assert 'PushAuthVerificationRequired' in content
