from src.web.routes import email as email_routes


def test_serialize_inbox_message_keeps_summary_and_detail_fields():
    message = {
        "id": "msg-1",
        "subject": "欢迎加入",
        "from": "team@example.com",
        "received_at": "2026-04-10T12:00:00Z",
        "text": "第一行\n第二行",
        "html": "<div><p>Hello <strong>World</strong></p></div>",
        "seen": True,
        "x_extra": {"trace_id": "abc-123"},
    }

    result = email_routes._serialize_inbox_message(message)

    assert result["id"] == "msg-1"
    assert result["subject"] == "欢迎加入"
    assert result["from"] == "team@example.com"
    assert result["snippet"]
    assert result["is_seen"] is True
    assert result["text_body"] == "第一行\n第二行"
    assert result["html_body"] == "<div><p>Hello <strong>World</strong></p></div>"
    assert "第一行" in result["safe_preview"]
    assert result["raw_message"]["x_extra"]["trace_id"] == "abc-123"
    assert result["content_meta"]["has_text"] is True
    assert result["content_meta"]["has_html"] is True
    assert "x_extra" in result["content_meta"]["available_fields"]


def test_serialize_inbox_message_uses_html_as_text_fallback():
    message = {
        "id": "msg-2",
        "html": "<div><p>第一段</p><p>第二段</p></div>",
        "raw": {"headers": {"x-source": "mail-test"}},
    }

    result = email_routes._serialize_inbox_message(message)

    assert result["text_body"] == "第一段\n第二段"
    assert "第一段" in result["snippet"]
    assert result["content_meta"]["has_raw"] is True
