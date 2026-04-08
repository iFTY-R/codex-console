from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_table_dropdown_card_style_exists():
    content = (ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")
    assert ".card.table-dropdown-card" in content
    assert ".table-dropdown-card .dropdown-menu" in content


def test_accounts_and_email_services_use_table_dropdown_card():
    accounts_html = (ROOT / "templates" / "accounts.html").read_text(encoding="utf-8")
    email_html = (ROOT / "templates" / "email_services.html").read_text(encoding="utf-8")
    assert "card table-dropdown-card" in accounts_html
    assert "table-dropdown-card" in email_html
