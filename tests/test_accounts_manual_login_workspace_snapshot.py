import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.web.services.manual_login_service import (  # noqa: E402
    _build_workspace_result_payload,
    _extract_workspace_entries_from_payload,
)


def test_extract_workspace_entries_marks_selected_workspace():
    items, selected_id = _extract_workspace_entries_from_payload(
        {
            "workspace_id": "ws-beta",
            "workspaces": [
                {"id": "ws-alpha", "name": "Alpha", "kind": "personal"},
                {"id": "ws-beta", "name": "Beta", "role": "owner"},
            ],
        }
    )

    assert selected_id == "ws-beta"
    assert [item["id"] for item in items] == ["ws-alpha", "ws-beta"]
    assert items[1]["name"] == "Beta"
    assert items[1]["is_selected"] is True


def test_build_workspace_result_payload_falls_back_to_selected_workspace():
    payload = _build_workspace_result_payload(
        {
            "workspace_id": "ws-only",
            "selected_workspace_name": "Only Workspace",
            "workspaces": [],
        }
    )

    assert payload["selected_workspace_id"] == "ws-only"
    assert payload["selected_workspace_name"] == "Only Workspace"
    assert payload["workspaces"] == [
        {
            "id": "ws-only",
            "name": "",
            "role": "",
            "kind": "",
            "plan_type": "",
            "is_selected": True,
        }
    ]
