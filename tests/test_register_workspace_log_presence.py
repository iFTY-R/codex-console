from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_register_contains_workspace_name_aware_logging_helpers():
    content = (ROOT / "src" / "core" / "register.py").read_text(encoding="utf-8")
    assert "_workspace_catalog" in content
    assert "_format_workspace_label" in content
    assert "提交 workspace/select：" in content
    assert "选择 Workspace，安排个靠谱座位：" in content
    assert "workspace/select 原始响应报文:" in content
    assert "/api/auth/session 原始响应报文:" in content
    assert "验证码校验原始响应报文:" in content
    assert "def _bootstrap_session_via_workspace_continue(" in content
    assert "尝试通过 workspace/select continue_url 建立 ChatGPT Web 会话：" in content
    assert "强制补会话成功：workspace continue 路线已拿到 session_token" in content
    assert "def bootstrap_login_context(" in content
    assert "已注入续登上下文 cookies：" in content
    assert "def _log_http_exchange(" in content
    assert 'self._log(f"{label} 请求URL: {url}")' in content
    assert '"提交登录密码"' in content
    assert 'self._log(f"{label} 响应报文: {response.text}")' in content
    assert "def _prewarm_seeded_login_context(" in content
    assert "续登预热 auth.openai" in content
    assert "续登预热 auth/session" in content
