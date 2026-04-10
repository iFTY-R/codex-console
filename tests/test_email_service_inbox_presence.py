from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_email_services_page_contains_inbox_modal():
    content = (ROOT / "templates" / "email_services.html").read_text(encoding="utf-8")
    assert "service-inbox-modal" in content
    assert "refresh-service-inbox-btn" in content
    assert "service-inbox-list" in content


def test_email_services_js_contains_inbox_entrypoints():
    content = (ROOT / "static" / "js" / "email_services.js").read_text(encoding="utf-8")
    assert "openServiceInbox" in content
    assert "toggleInboxMessageDetails" in content
    assert "buildSafeInboxPreviewSrcdoc" in content
    assert "/email-services/${currentInboxServiceId}/inbox?limit=5" in content
    assert content.count("收件箱") >= 2


def test_email_services_page_contains_expandable_inbox_detail_ui():
    content = (ROOT / "templates" / "email_services.html").read_text(encoding="utf-8")
    assert "inbox-message-details" in content
    assert "inbox-html-preview-frame" in content
    assert "inbox-raw-json" in content


def test_email_route_and_imap_support_inbox():
    email_route = (ROOT / "src" / "web" / "routes" / "email.py").read_text(encoding="utf-8")
    imap_service = (ROOT / "src" / "services" / "imap_mail.py").read_text(encoding="utf-8")
    assert '/{service_id}/inbox' in email_route
    assert 'def get_email_messages' in imap_service
    assert 'search_all' in imap_service
