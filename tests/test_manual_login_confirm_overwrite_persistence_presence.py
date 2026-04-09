from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_manual_login_confirm_overwrite_reads_pending_result_from_task_manager():
    content = (ROOT / "src" / "web" / "services" / "manual_login_service.py").read_text(encoding="utf-8")
    assert 'task_manager.get_domain_task_raw(MANUAL_LOGIN_DOMAIN, task_id)' in content
    assert 'raw_task.get("_pending_result")' in content
    assert '_pending_result=dict(bundle)' in content
    assert '_existing_account_id=int(existing_account.id)' in content
    assert '开始覆盖写回账号：' in content
    assert '覆盖写回完成：' in content


def test_task_manager_exposes_raw_domain_task_helper():
    content = (ROOT / "src" / "web" / "task_manager.py").read_text(encoding="utf-8")
    assert 'def get_domain_task_raw(self, domain: str, task_id: str)' in content


def test_crud_update_account_uses_non_conflicting_record_id_parameter():
    content = (ROOT / "src" / "database" / "crud.py").read_text(encoding="utf-8")
    assert "def update_account(" in content
    assert "record_id: int" in content


def test_confirm_overwrite_wraps_failures_into_runtime_errors():
    content = (ROOT / "src" / "web" / "services" / "manual_login_service.py").read_text(encoding="utf-8")
    assert "覆盖写回失败：" in content
    assert 'raise RuntimeError(f"覆盖写回失败: {exc}") from exc' in content


def test_confirm_overwrite_route_has_generic_exception_guard():
    content = (ROOT / "src" / "web" / "routes" / "accounts.py").read_text(encoding="utf-8")
    assert 'logger.exception("处理手动登录覆盖确认失败: task_id=%s", task_id)' in content
    assert 'raise HTTPException(status_code=500, detail=f"覆盖确认接口异常: {exc}")' in content
