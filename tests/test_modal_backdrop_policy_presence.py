from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_utils_contains_global_modal_backdrop_policy():
    content = (ROOT / "static" / "js" / "utils.js").read_text(encoding="utf-8")
    assert "function canModalCloseOnBackdrop(modal)" in content
    assert "function canModalCloseOnEscape(modal)" in content
    assert "document.addEventListener('click', (e) => {" in content
    assert "if (!modal.classList.contains('modal')) return;" in content
    assert "if (!canModalCloseOnBackdrop(modal))" in content or "if (canModalCloseOnBackdrop(modal)) return;" in content


def test_view_only_modals_are_marked_as_backdrop_closable():
    accounts_html = (ROOT / "templates" / "accounts.html").read_text(encoding="utf-8")
    email_html = (ROOT / "templates" / "email_services.html").read_text(encoding="utf-8")
    assert 'id="detail-modal" data-backdrop-close="true" data-escape-close="true"' in accounts_html
    assert 'id="service-inbox-modal" data-backdrop-close="true" data-escape-close="true"' in email_html
