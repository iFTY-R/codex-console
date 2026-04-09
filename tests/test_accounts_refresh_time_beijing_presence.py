from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_accounts_last_refresh_uses_beijing_formatter():
    content = (ROOT / "static" / "js" / "accounts.js").read_text(encoding="utf-8")

    assert "format.beijingDate(account.last_refresh)" in content


def test_accounts_monitor_timestamps_use_beijing_formatter():
    content = (ROOT / "static" / "js" / "accounts.js").read_text(encoding="utf-8")

    assert "return format.beijingDate(value);" in content
    assert "const time = format.beijingDate(item?.time);" in content


def test_utils_exposes_beijing_date_formatter():
    content = (ROOT / "static" / "js" / "utils.js").read_text(encoding="utf-8")

    assert "beijingDate(dateStr)" in content
    assert "timeZone: 'Asia/Shanghai'" in content
