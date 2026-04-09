"""
账号管理手动登录任务服务。

职责：
- 编排账号管理页“手动登录”弹窗的后台任务
- 复用现有登录/验证码/会话补全能力
- 统一处理新账号创建、已有账号覆盖确认、日志输出
"""

from __future__ import annotations

import base64
import json
import threading
import urllib.parse as urlparse
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ...config.constants import AccountStatus, EmailServiceType, OPENAI_PAGE_TYPES
from ...core.anyauto.utils import decode_jwt_payload
from ...core.openai.payment import check_subscription_status_detail
from ...core.openai.token_refresh import TokenRefreshManager
from ...core.register import RegistrationEngine, RegistrationResult
from ...core.timezone_utils import utcnow_naive
from ...database import crud
from ...database.models import Account, EmailService as EmailServiceModel
from ...database.session import get_db
from ...services import EmailServiceFactory
from ..task_manager import task_manager

MANUAL_LOGIN_DOMAIN = "accounts"
MANUAL_LOGIN_TASK_TYPE = "manual_login"
MANUAL_LOGIN_TASK_PREFIX = "manual-login-"

_context_lock = threading.Lock()
_task_context: Dict[str, Dict[str, Any]] = {}


@dataclass
class ManualLoginResolvedService:
    service: Any
    service_type: EmailServiceType
    service_id: Optional[int]
    service_name: Optional[str]


class PushAuthVerificationRequired(RuntimeError):
    """登录流程命中 push 验证，需要用户在官方页面继续。"""

    def __init__(self, page_type: str, stage: str):
        self.page_type = str(page_type or "").strip() or "push_auth_verification"
        self.stage = str(stage or "").strip() or "open_login_flow"
        super().__init__(f"当前账号需要额外的 Push 验证（{self.page_type}）")


def _now_iso() -> str:
    return utcnow_naive().isoformat()


def _task_id() -> str:
    return f"{MANUAL_LOGIN_TASK_PREFIX}{uuid.uuid4().hex[:12]}"


def _set_context(task_id: str, **fields: Any) -> None:
    with _context_lock:
        current = _task_context.setdefault(task_id, {})
        current.update(fields)


def _get_context(task_id: str) -> Dict[str, Any]:
    with _context_lock:
        return dict(_task_context.get(task_id, {}))


def _update_context_nested(task_id: str, key: str, value: Dict[str, Any]) -> None:
    with _context_lock:
        current = _task_context.setdefault(task_id, {})
        nested = dict(current.get(key) or {})
        nested.update(dict(value or {}))
        current[key] = nested


def _append_log(task_id: str, level: str, message: str, *, stage: Optional[str] = None) -> None:
    entry = {
        "time": _now_iso(),
        "level": str(level or "info").strip().lower() or "info",
        "message": str(message or "").strip() or "-",
    }
    task_manager.append_domain_task_detail(MANUAL_LOGIN_DOMAIN, task_id, entry, max_items=400)
    progress = {}
    if stage:
        progress["stage"] = stage
    if progress:
        task_manager.update_domain_task(
            MANUAL_LOGIN_DOMAIN,
            task_id,
            message=entry["message"],
            progress=progress,
        )
    else:
        task_manager.update_domain_task(MANUAL_LOGIN_DOMAIN, task_id, message=entry["message"])


def _mask_secret(value: Optional[str], *, head: int = 6, tail: int = 4) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= head + tail:
        return "*" * len(text)
    return f"{text[:head]}***{text[-tail:]}"


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _normalize_workspace_entry(item: Any, *, selected_workspace_id: str = "") -> Optional[Dict[str, Any]]:
    if not isinstance(item, dict):
        return None

    workspace_id = _first_text(
        item.get("id"),
        item.get("workspace_id"),
        item.get("organization_id"),
        item.get("account_id"),
    )
    if not workspace_id:
        return None

    return {
        "id": workspace_id,
        "name": _first_text(
            item.get("name"),
            item.get("workspace_name"),
            item.get("display_name"),
            item.get("title"),
        ),
        "role": _first_text(
            item.get("role"),
            item.get("membership_role"),
            item.get("account_role"),
            item.get("account_user_role"),
        ),
        "kind": _first_text(item.get("kind"), item.get("type")),
        "plan_type": _first_text(
            item.get("plan_type"),
            item.get("workspace_plan_type"),
            item.get("subscription_type"),
        ),
        "is_selected": bool(selected_workspace_id and workspace_id == selected_workspace_id),
    }


def _extract_workspace_entries_from_payload(
    payload: Any,
    *,
    selected_workspace_id: str = "",
) -> Tuple[List[Dict[str, Any]], str]:
    if not isinstance(payload, dict):
        return [], str(selected_workspace_id or "").strip()

    selected_id = _first_text(
        selected_workspace_id,
        payload.get("workspace_id"),
        payload.get("default_workspace_id"),
        ((payload.get("workspace") or {}).get("id") if isinstance(payload.get("workspace"), dict) else ""),
        ((payload.get("selected_workspace") or {}).get("id") if isinstance(payload.get("selected_workspace"), dict) else ""),
        payload.get("organization_id"),
    )

    raw_lists: List[Any] = [
        payload.get("workspaces"),
        payload.get("accounts"),
        payload.get("organizations"),
        ((payload.get("user") or {}).get("workspaces") if isinstance(payload.get("user"), dict) else None),
        ((payload.get("data") or {}).get("workspaces") if isinstance(payload.get("data"), dict) else None),
        ((payload.get("session") or {}).get("workspaces") if isinstance(payload.get("session"), dict) else None),
    ]
    if isinstance(payload.get("workspace"), dict):
        raw_lists.append([payload.get("workspace")])
    if isinstance(payload.get("selected_workspace"), dict):
        raw_lists.append([payload.get("selected_workspace")])

    items: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw_list in raw_lists:
        if not isinstance(raw_list, list):
            continue
        for raw_item in raw_list:
            normalized = _normalize_workspace_entry(raw_item, selected_workspace_id=selected_id)
            if not normalized:
                continue
            workspace_id = str(normalized.get("id") or "").strip()
            if not workspace_id or workspace_id in seen_ids:
                continue
            seen_ids.add(workspace_id)
            items.append(normalized)

    if selected_id and selected_id not in seen_ids:
        items.append(
            {
                "id": selected_id,
                "name": "",
                "role": "",
                "kind": "",
                "plan_type": "",
                "is_selected": True,
            }
        )

    return items, selected_id


def _decode_cookie_payload(value: Optional[str]) -> Optional[Dict[str, Any]]:
    raw_value = str(value or "").strip()
    if not raw_value:
        return None

    candidates: List[str] = []
    if "." in raw_value:
        segments = raw_value.split(".")
        if len(segments) >= 2 and segments[1]:
            candidates.append(segments[1])
        if segments and segments[0]:
            candidates.append(segments[0])
    candidates.append(raw_value)

    for candidate in candidates:
        current = str(candidate or "").strip()
        if not current:
            continue
        for _ in range(2):
            decoded = urlparse.unquote(current)
            if decoded == current:
                break
            current = decoded
        for decoder in (
            lambda text: json.loads(text),
            lambda text: json.loads(base64.urlsafe_b64decode((text + "=" * (-len(text) % 4)).encode("ascii")).decode("utf-8")),
            lambda text: json.loads(base64.b64decode((text + "=" * (-len(text) % 4)).encode("ascii")).decode("utf-8")),
        ):
            try:
                parsed = decoder(current)
            except Exception:
                continue
            if isinstance(parsed, dict):
                return parsed
    return None


def _fetch_chatgpt_session_payload(
    http_session: Any,
    *,
    access_token: Optional[str] = None,
    task_id: str = "",
) -> Dict[str, Any]:
    if http_session is None:
        return {}

    headers = {
        "accept": "application/json",
        "referer": "https://chatgpt.com/",
        "origin": "https://chatgpt.com",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "cache-control": "no-cache",
        "pragma": "no-cache",
    }
    token = str(access_token or "").strip()
    if token:
        headers["authorization"] = f"Bearer {token}"

    response = http_session.get(
        "https://chatgpt.com/api/auth/session",
        headers=headers,
        timeout=20,
    )
    if task_id:
        _append_log(task_id, "info", f"/api/auth/session（workspace探测）原始响应报文: {response.text}", stage="capture_session")
    if response.status_code != 200:
        return {}
    try:
        payload = response.json() or {}
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _extract_workspace_snapshot_from_cookies(
    cookies: Any,
    *,
    selected_workspace_id: str = "",
) -> Dict[str, Any]:
    cookie_get = getattr(cookies, "get", None)
    auth_session_raw = ""
    auth_info_raw = ""
    if callable(cookie_get):
        try:
            auth_session_raw = str(cookie_get("oai-client-auth-session") or "").strip()
        except Exception:
            auth_session_raw = ""
        try:
            auth_info_raw = str(cookie_get("oai-client-auth-info") or "").strip()
        except Exception:
            auth_info_raw = ""

    for raw_value in (auth_session_raw, auth_info_raw):
        payload = _decode_cookie_payload(raw_value)
        items, selected_id = _extract_workspace_entries_from_payload(
            payload,
            selected_workspace_id=selected_workspace_id,
        )
        if items:
            selected_name = ""
            for item in items:
                if item.get("is_selected"):
                    selected_name = str(item.get("name") or "").strip()
                    break
            return {
                "workspaces": items,
                "selected_workspace_id": selected_id,
                "selected_workspace_name": selected_name,
            }

    return {
        "workspaces": [],
        "selected_workspace_id": str(selected_workspace_id or "").strip(),
        "selected_workspace_name": "",
    }


def _collect_workspace_snapshot(
    task_id: str,
    *,
    selected_workspace_id: str = "",
    access_token: Optional[str] = None,
    http_session: Any = None,
    session_token: Optional[str] = None,
    proxy: Optional[str] = None,
) -> Dict[str, Any]:
    selected_id = str(selected_workspace_id or "").strip()
    payload: Dict[str, Any] = {}

    if http_session is not None:
        try:
            payload = _fetch_chatgpt_session_payload(http_session, access_token=access_token, task_id=task_id)
        except Exception as exc:
            _append_log(task_id, "warning", f"获取 workspace session 数据失败：{exc}", stage="capture_session")
            payload = {}
    elif str(session_token or "").strip():
        try:
            manager = TokenRefreshManager(proxy_url=proxy)
            probe_session = manager._create_session()
            token = str(session_token or "").strip()
            for domain in (".chatgpt.com", "chatgpt.com"):
                probe_session.cookies.set("__Secure-next-auth.session-token", token, domain=domain, path="/")
            payload = _fetch_chatgpt_session_payload(probe_session, access_token=access_token, task_id=task_id)
            http_session = probe_session
        except Exception as exc:
            _append_log(task_id, "warning", f"通过 session_token 拉取 workspace 列表失败：{exc}", stage="capture_session")
            payload = {}

    items, selected_from_payload = _extract_workspace_entries_from_payload(
        payload,
        selected_workspace_id=selected_id,
    )
    selected_id = selected_from_payload or selected_id

    if (not items) and http_session is not None:
        cookie_snapshot = _extract_workspace_snapshot_from_cookies(
            getattr(http_session, "cookies", None),
            selected_workspace_id=selected_id,
        )
        items = list(cookie_snapshot.get("workspaces") or [])
        selected_id = str(cookie_snapshot.get("selected_workspace_id") or selected_id or "").strip()
        selected_name = str(cookie_snapshot.get("selected_workspace_name") or "").strip()
    else:
        selected_name = ""

    if not items and selected_id:
        items = [
            {
                "id": selected_id,
                "name": "",
                "role": "",
                "kind": "",
                "plan_type": "",
                "is_selected": True,
            }
        ]

    if not selected_name:
        for item in items:
            if bool(item.get("is_selected")):
                selected_name = str(item.get("name") or "").strip()
                break

    if items:
        selected_label = selected_name or selected_id or "-"
        _append_log(
            task_id,
            "info",
            f"检测到 {len(items)} 个 workspace，当前选中：{selected_label}",
            stage="capture_session",
        )

    return {
        "workspaces": items,
        "selected_workspace_id": selected_id,
        "selected_workspace_name": selected_name,
    }


def _extract_ids_from_access_token(access_token: Optional[str]) -> Tuple[str, str]:
    claims = decode_jwt_payload(str(access_token or "").strip())
    auth_claims = claims.get("https://api.openai.com/auth") or {}
    account_id = str(
        auth_claims.get("chatgpt_account_id")
        or auth_claims.get("account_id")
        or claims.get("chatgpt_account_id")
        or claims.get("account_id")
        or claims.get("workspace_id")
        or ""
    ).strip()
    workspace_id = str(
        auth_claims.get("workspace_id")
        or auth_claims.get("organization_id")
        or claims.get("workspace_id")
        or account_id
        or ""
    ).strip()
    return account_id, workspace_id


def _build_workspace_result_payload(source: Dict[str, Any]) -> Dict[str, Any]:
    selected_id = _first_text(
        source.get("selected_workspace_id"),
        source.get("workspace_id"),
    )
    items, selected_id = _extract_workspace_entries_from_payload(
        {"workspaces": source.get("workspaces") or []},
        selected_workspace_id=selected_id,
    )

    if not items and selected_id:
        items = [
            {
                "id": selected_id,
                "name": "",
                "role": "",
                "kind": "",
                "plan_type": "",
                "is_selected": True,
            }
        ]

    selected_name = _first_text(source.get("selected_workspace_name"))
    if not selected_name:
        for item in items:
            if bool(item.get("is_selected")):
                selected_name = str(item.get("name") or "").strip()
                break

    return {
        "workspace_id": selected_id,
        "selected_workspace_id": selected_id,
        "selected_workspace_name": selected_name,
        "workspaces": items,
    }


def _merge_extra_data(account: Optional[Account], payload: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(getattr(account, "extra_data", None) or {})
    merged.update(payload or {})
    return merged


def _sanitize_payload_for_task(request: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "email": str(request.get("email") or "").strip().lower(),
        "mode": str(request.get("mode") or "auto").strip().lower() or "auto",
        "email_service_id": request.get("email_service_id"),
        "has_password": bool(str(request.get("password") or "").strip()),
        "has_session_token": bool(str(request.get("session_token") or "").strip()),
        "has_cookies": bool(str(request.get("cookies") or "").strip()),
    }


def _upsert_cookie(cookies_text: Optional[str], cookie_name: str, cookie_value: str) -> str:
    target_name = str(cookie_name or "").strip()
    target_value = str(cookie_value or "").strip()
    if not target_name:
        return str(cookies_text or "").strip()

    pairs = []
    seen = False
    for item in str(cookies_text or "").split(";"):
        raw = str(item or "").strip()
        if not raw or "=" not in raw:
            continue
        name, value = raw.split("=", 1)
        name = name.strip()
        value = value.strip()
        if not name:
            continue
        if name == target_name:
            if target_value:
                pairs.append((name, target_value))
            seen = True
        else:
            pairs.append((name, value))

    if (not seen) and target_value:
        pairs.append((target_name, target_value))

    return "; ".join(f"{name}={value}" for name, value in pairs)


def _normalize_email_service_config(service_type: EmailServiceType, config: Optional[dict], proxy_url: Optional[str] = None) -> dict:
    from ..routes import payment as payment_routes

    return payment_routes._normalize_email_service_config_for_session_bootstrap(service_type, config, proxy_url)


def _resolve_manual_login_service(
    db,
    *,
    email: str,
    proxy: Optional[str],
    existing_account: Optional[Account] = None,
    email_service_id: Optional[int] = None,
) -> ManualLoginResolvedService:
    email_lower = str(email or "").strip().lower()
    if not email_lower:
        raise RuntimeError("邮箱不能为空")

    selected: Optional[EmailServiceModel] = None
    service_type: Optional[EmailServiceType] = None

    if email_service_id:
        selected = (
            db.query(EmailServiceModel)
            .filter(EmailServiceModel.id == int(email_service_id), EmailServiceModel.enabled == True)
            .first()
        )
        if not selected:
            raise RuntimeError("指定的邮箱服务不存在或已禁用")
        try:
            service_type = EmailServiceType(str(selected.service_type or "").strip().lower())
        except Exception as exc:
            raise RuntimeError("指定邮箱服务类型不受支持") from exc
    elif existing_account and str(existing_account.email_service or "").strip():
        raw_type = str(existing_account.email_service or "").strip().lower()
        try:
            service_type = EmailServiceType(raw_type)
        except Exception:
            service_type = None
        if service_type is not None:
            services = (
                db.query(EmailServiceModel)
                .filter(EmailServiceModel.service_type == service_type.value, EmailServiceModel.enabled == True)
                .order_by(EmailServiceModel.priority.asc(), EmailServiceModel.id.asc())
                .all()
            )
            if service_type in (EmailServiceType.OUTLOOK, EmailServiceType.IMAP_MAIL):
                for svc in services:
                    cfg_email = str((svc.config or {}).get("email") or "").strip().lower()
                    if cfg_email and cfg_email == email_lower:
                        selected = svc
                        break
            if not selected and services:
                selected = services[0]

    if not selected:
        all_services = (
            db.query(EmailServiceModel)
            .filter(EmailServiceModel.enabled == True)
            .order_by(EmailServiceModel.priority.asc(), EmailServiceModel.id.asc())
            .all()
        )
        for svc in all_services:
            cfg_email = str((svc.config or {}).get("email") or "").strip().lower()
            if cfg_email and cfg_email == email_lower:
                selected = svc
                try:
                    service_type = EmailServiceType(str(svc.service_type or "").strip().lower())
                except Exception as exc:
                    raise RuntimeError("自动匹配到的邮箱服务类型不受支持") from exc
                break

    if not selected or service_type is None:
        raise RuntimeError("未找到与该邮箱匹配的可用邮箱服务，请手动指定")

    config = _normalize_email_service_config(service_type, selected.config, proxy)
    service = EmailServiceFactory.create(service_type, config, name=f"manual_login_{service_type.value}")
    return ManualLoginResolvedService(
        service=service,
        service_type=service_type,
        service_id=int(selected.id),
        service_name=str(selected.name or "").strip() or None,
    )


def _build_result_preview(bundle: Dict[str, Any], *, existing_account: Optional[Account]) -> Dict[str, Any]:
    return {
        "email": bundle.get("email"),
        "mode": bundle.get("mode"),
        "existing_account_id": int(existing_account.id) if existing_account else None,
        "account_id": bundle.get("account_id") or "",
        "has_access_token": bool(str(bundle.get("access_token") or "").strip()),
        "has_refresh_token": bool(str(bundle.get("refresh_token") or "").strip()),
        "has_session_token": bool(str(bundle.get("session_token") or "").strip()),
        "has_cookies": bool(str(bundle.get("cookies") or "").strip()),
        "session_token_preview": _mask_secret(bundle.get("session_token")),
        "service_type": bundle.get("email_service"),
        "service_name": bundle.get("service_name"),
        **_build_workspace_result_payload(bundle),
    }


def _persist_login_bundle(
    db,
    *,
    bundle: Dict[str, Any],
    existing_account: Optional[Account],
    overwrite: bool,
) -> Account:
    email = str(bundle.get("email") or "").strip().lower()
    password = str(bundle.get("password") or "").strip()
    now = utcnow_naive()
    service_type_value = str(bundle.get("email_service") or "").strip().lower()
    service_db_id = bundle.get("service_db_id")
    extra_data = {
        "manual_login": {
            "mode": bundle.get("mode"),
            "service_name": bundle.get("service_name"),
            "service_type": service_type_value,
            "service_db_id": service_db_id,
            "updated_at": now.isoformat(),
        }
    }
    merged_extra = _merge_extra_data(existing_account, extra_data)

    if existing_account:
        if not overwrite:
            raise RuntimeError("覆盖确认未通过")
        update_payload = {
            "password": password or existing_account.password,
            "email_service": service_type_value or existing_account.email_service,
            "account_id": str(bundle.get("account_id") or "").strip() or existing_account.account_id,
            "workspace_id": str(bundle.get("workspace_id") or "").strip() or existing_account.workspace_id,
            "access_token": str(bundle.get("access_token") or "").strip() or existing_account.access_token,
            "refresh_token": str(bundle.get("refresh_token") or "").strip() or existing_account.refresh_token,
            "id_token": str(bundle.get("id_token") or "").strip() or existing_account.id_token,
            "session_token": str(bundle.get("session_token") or "").strip() or existing_account.session_token,
            "cookies": str(bundle.get("cookies") or "").strip() or existing_account.cookies,
            "proxy_used": str(bundle.get("proxy_used") or "").strip() or existing_account.proxy_used,
            "status": AccountStatus.ACTIVE.value,
            "source": "login",
            "last_refresh": now,
            "extra_data": merged_extra,
        }
        account = crud.update_account(db, existing_account.id, **update_payload)
        if account is None:
            raise RuntimeError("更新账号失败")
        return account

    account = crud.create_account(
        db,
        email=email,
        password=password,
        client_id=str(bundle.get("client_id") or "").strip() or None,
        session_token=str(bundle.get("session_token") or "").strip() or None,
        email_service=service_type_value,
        account_id=str(bundle.get("account_id") or "").strip() or None,
        workspace_id=str(bundle.get("workspace_id") or "").strip() or None,
        access_token=str(bundle.get("access_token") or "").strip() or None,
        refresh_token=str(bundle.get("refresh_token") or "").strip() or None,
        id_token=str(bundle.get("id_token") or "").strip() or None,
        cookies=str(bundle.get("cookies") or "").strip() or None,
        proxy_used=str(bundle.get("proxy_used") or "").strip() or None,
        extra_data=merged_extra,
        status=AccountStatus.ACTIVE.value,
        source="login",
    )
    account.last_refresh = now
    db.commit()
    db.refresh(account)
    return account


def _build_completion_result(bundle: Dict[str, Any], account: Optional[Account], *, action: str) -> Dict[str, Any]:
    workspace_payload = _build_workspace_result_payload(bundle)
    if account and (not workspace_payload.get("selected_workspace_id")):
        workspace_payload = _build_workspace_result_payload(
            {
                **bundle,
                "selected_workspace_id": getattr(account, "workspace_id", "") or "",
                "workspace_id": getattr(account, "workspace_id", "") or "",
            }
        )

    return {
        "email": bundle.get("email"),
        "mode": bundle.get("mode"),
        "account_action": action,
        "final_account_id": int(account.id) if account else None,
        "account_id": str(bundle.get("account_id") or getattr(account, "account_id", "") or "").strip(),
        "subscription_type": str(getattr(account, "subscription_type", "") or "free"),
        "session_token_saved": bool(str(bundle.get("session_token") or getattr(account, "session_token", "") or "").strip()),
        "access_token_saved": bool(str(bundle.get("access_token") or getattr(account, "access_token", "") or "").strip()),
        "refresh_token_saved": bool(str(bundle.get("refresh_token") or getattr(account, "refresh_token", "") or "").strip()),
        "cookies_saved": bool(str(bundle.get("cookies") or getattr(account, "cookies", "") or "").strip()),
        "service_type": bundle.get("email_service"),
        "service_name": bundle.get("service_name"),
        **workspace_payload,
    }


def _sync_subscription_after_login(task_id: str, account: Account, proxy: Optional[str]) -> None:
    """手动登录成功后同步订阅状态。失败不阻断登录主流程。"""
    if not str(getattr(account, "access_token", "") or "").strip():
        _append_log(task_id, "warning", "跳过订阅同步：账号缺少 access_token", stage="persist_account")
        return

    now = utcnow_naive()
    try:
        detail = check_subscription_status_detail(account, proxy=proxy)
        status = str((detail or {}).get("status") or "free").strip().lower() or "free"
        confidence = str((detail or {}).get("confidence") or "low").strip().lower() or "low"
        source = str((detail or {}).get("source") or "unknown").strip() or "unknown"

        if status in ("plus", "team"):
            account.subscription_type = status
            account.subscription_at = now
        elif status == "free" and confidence == "high":
            account.subscription_type = None
            account.subscription_at = None

        account.last_refresh = now
        _append_log(
            task_id,
            "info",
            f"订阅同步完成：status={status} source={source} confidence={confidence}",
            stage="persist_account",
        )
    except Exception as exc:
        _append_log(task_id, "warning", f"订阅同步失败，保留现有订阅状态：{exc}", stage="persist_account")


def _run_auto_login_flow(
    task_id: str,
    *,
    email: str,
    password: str,
    proxy: Optional[str],
    resolved_service: ManualLoginResolvedService,
    existing_account: Optional[Account] = None,
) -> Dict[str, Any]:
    _append_log(task_id, "info", f"已解析邮箱服务：{resolved_service.service_name or resolved_service.service_type.value}", stage="resolve_email_service")
    engine = RegistrationEngine(
        email_service=resolved_service.service,
        proxy_url=proxy,
        callback_logger=lambda msg: _append_log(task_id, "info", msg),
        task_uuid=None,
        check_cancelled=lambda: task_manager.is_domain_task_cancel_requested(MANUAL_LOGIN_DOMAIN, task_id),
    )
    engine.email = email
    engine.inbox_email = email
    engine.password = password
    existing_cookies = str(getattr(existing_account, "cookies", "") or "").strip()
    existing_session_token = str(getattr(existing_account, "session_token", "") or "").strip()
    if existing_cookies or existing_session_token:
        engine.bootstrap_login_context(
            cookies_text=existing_cookies,
            session_token=existing_session_token,
            access_token=str(getattr(existing_account, "access_token", "") or "").strip(),
        )
    if resolved_service.service_id:
        engine.email_info = {"service_id": str(resolved_service.service_id)}

    result = RegistrationResult(
        success=False,
        email=email,
        password=password,
        source="login",
    )

    _append_log(task_id, "info", "准备登录链路...", stage="open_login_flow")
    did, sen_token = engine._prepare_authorize_flow("手动登录")
    if not did:
        raise RuntimeError("登录入口准备失败")

    login_start = engine._submit_login_start(did, sen_token)
    if not login_start.success:
        raise RuntimeError(login_start.error_message or "登录入口失败")

    page_type = str(login_start.page_type or "").strip()
    if page_type == OPENAI_PAGE_TYPES["LOGIN_PASSWORD"]:
        _append_log(task_id, "info", "已进入密码页，准备提交密码", stage="submit_password")
        password_result = engine._submit_login_password()
        password_page_type = str(password_result.page_type or "").strip()
        if password_page_type == OPENAI_PAGE_TYPES.get("PUSH_AUTH_VERIFICATION"):
            raise PushAuthVerificationRequired(password_page_type, "submit_password")
        if (not password_result.success) or (not password_result.is_existing_account):
            raise RuntimeError(password_result.error_message or "密码登录失败")
    elif page_type == OPENAI_PAGE_TYPES["EMAIL_OTP_VERIFICATION"]:
        _append_log(task_id, "info", "登录入口已直达验证码页", stage="wait_email_code")
    elif page_type == OPENAI_PAGE_TYPES.get("PUSH_AUTH_VERIFICATION"):
        raise PushAuthVerificationRequired(page_type, "open_login_flow")
    else:
        raise RuntimeError(f"登录入口返回未知页面：{page_type or 'unknown'}")

    _append_log(task_id, "info", "开始抓取登录会话与 Token", stage="capture_session")
    if not engine._complete_token_exchange(result, require_login_otp=True):
        raise RuntimeError(result.error_message or "登录结果抓取失败")

    cookies = engine._dump_session_cookies()
    session_token = str(result.session_token or "").strip()
    if not session_token:
        session_token = str(TokenRefreshManager._extract_session_token_from_cookies(cookies) or "").strip()

    account_id = str(result.account_id or "").strip()
    workspace_id = str(result.workspace_id or "").strip()
    if not account_id and result.access_token:
        account_id, inferred_workspace = _extract_ids_from_access_token(result.access_token)
        if not workspace_id:
            workspace_id = inferred_workspace
    if not workspace_id:
        workspace_id = account_id
    workspace_snapshot = _collect_workspace_snapshot(
        task_id,
        selected_workspace_id=workspace_id,
        access_token=result.access_token,
        http_session=engine.session,
    )

    return {
        "email": email,
        "password": password,
        "mode": "auto",
        "email_service": resolved_service.service_type.value,
        "service_name": resolved_service.service_name,
        "service_db_id": resolved_service.service_id,
        "access_token": str(result.access_token or "").strip(),
        "refresh_token": str(result.refresh_token or "").strip(),
        "id_token": str(result.id_token or "").strip(),
        "session_token": session_token,
        "cookies": cookies,
        "account_id": account_id,
        "workspace_id": workspace_id,
        "selected_workspace_id": str(workspace_snapshot.get("selected_workspace_id") or workspace_id or "").strip(),
        "selected_workspace_name": str(workspace_snapshot.get("selected_workspace_name") or "").strip(),
        "workspaces": list(workspace_snapshot.get("workspaces") or []),
        "client_id": "",
        "proxy_used": proxy,
    }


def _run_semi_auto_materialize(
    task_id: str,
    *,
    email: str,
    password: str,
    proxy: Optional[str],
    session_token: Optional[str],
    cookies: Optional[str],
    resolved_service: Optional[ManualLoginResolvedService],
    existing_account: Optional[Account],
) -> Dict[str, Any]:
    _append_log(task_id, "info", "开始处理半自动登录结果", stage="capture_session")
    raw_session_token = str(session_token or "").strip()
    raw_cookies = str(cookies or "").strip()
    if not raw_session_token and raw_cookies:
        raw_session_token = str(TokenRefreshManager._extract_session_token_from_cookies(raw_cookies) or "").strip()
    if not raw_session_token:
        raise RuntimeError("半自动模式需要粘贴 session_token 或包含该字段的 cookies")

    manager = TokenRefreshManager(proxy_url=proxy)
    refresh_result = manager.refresh_by_session_token(raw_session_token)
    if not refresh_result.success:
        raise RuntimeError(refresh_result.error_message or "session_token 校验失败")

    merged_cookies = _upsert_cookie(raw_cookies, "__Secure-next-auth.session-token", raw_session_token)
    account_id, workspace_id = _extract_ids_from_access_token(refresh_result.access_token)
    if not workspace_id:
        workspace_id = account_id
    workspace_snapshot = _collect_workspace_snapshot(
        task_id,
        selected_workspace_id=workspace_id,
        access_token=refresh_result.access_token,
        session_token=raw_session_token,
        proxy=proxy,
    )
    email_service_value = (
        resolved_service.service_type.value
        if resolved_service
        else str(getattr(existing_account, "email_service", "") or "").strip().lower()
    )
    if not email_service_value:
        raise RuntimeError("半自动模式未找到可回写的邮箱服务，请先手动指定")

    return {
        "email": email,
        "password": password,
        "mode": "semi_auto",
        "email_service": email_service_value,
        "service_name": resolved_service.service_name if resolved_service else None,
        "service_db_id": resolved_service.service_id if resolved_service else None,
        "access_token": str(refresh_result.access_token or "").strip(),
        "refresh_token": str(refresh_result.refresh_token or "").strip(),
        "id_token": "",
        "session_token": raw_session_token,
        "cookies": merged_cookies,
        "account_id": account_id,
        "workspace_id": workspace_id,
        "selected_workspace_id": str(workspace_snapshot.get("selected_workspace_id") or workspace_id or "").strip(),
        "selected_workspace_name": str(workspace_snapshot.get("selected_workspace_name") or "").strip(),
        "workspaces": list(workspace_snapshot.get("workspaces") or []),
        "client_id": "",
        "proxy_used": proxy,
    }


def _execute_manual_login(task_id: str) -> None:
    context = _get_context(task_id)
    request = dict(context.get("request") or {})
    proxy = context.get("proxy")
    email = str(request.get("email") or "").strip().lower()
    password = str(request.get("password") or "").strip()
    mode = str(request.get("mode") or "auto").strip().lower() or "auto"
    email_service_id = request.get("email_service_id")
    session_token = request.get("session_token")
    cookies = request.get("cookies")

    acquired, running, quota = task_manager.try_acquire_domain_slot(MANUAL_LOGIN_DOMAIN, task_id)
    if not acquired:
        reason = f"并发配额已满（running={running}, quota={quota}）"
        task_manager.update_domain_task(
            MANUAL_LOGIN_DOMAIN,
            task_id,
            status="failed",
            finished_at=_now_iso(),
            message=reason,
            error=reason,
        )
        return

    try:
        task_manager.update_domain_task(
            MANUAL_LOGIN_DOMAIN,
            task_id,
            status="running",
            started_at=_now_iso(),
            message="手动登录任务执行中",
            progress={"stage": "init"},
        )
        _append_log(task_id, "info", "手动登录任务已启动", stage="init")
        if task_manager.is_domain_task_cancel_requested(MANUAL_LOGIN_DOMAIN, task_id):
            raise RuntimeError("任务已取消")

        with get_db() as db:
            existing_account = crud.get_account_by_email(db, email)
            if existing_account:
                _append_log(task_id, "info", f"检测到已有账号：ID={existing_account.id}", stage="detect_account")
            else:
                _append_log(task_id, "info", "账号库中未找到同邮箱记录，将按新账号处理", stage="detect_account")

            effective_proxy = str(getattr(existing_account, "proxy_used", "") or "").strip() or str(proxy or "").strip() or None
            if effective_proxy and effective_proxy != proxy:
                _append_log(task_id, "info", "检测到已有账号代理，优先复用历史代理登录上下文", stage="detect_account")

            resolved_service: Optional[ManualLoginResolvedService] = None
            if mode == "auto" or email_service_id:
                resolved_service = _resolve_manual_login_service(
                    db,
                    email=email,
                    proxy=effective_proxy,
                    existing_account=existing_account,
                    email_service_id=email_service_id,
                )
            elif existing_account and str(existing_account.email_service or "").strip():
                try:
                    resolved_service = _resolve_manual_login_service(
                        db,
                        email=email,
                        proxy=effective_proxy,
                        existing_account=existing_account,
                        email_service_id=email_service_id,
                    )
                except Exception:
                    resolved_service = None

            if mode == "auto":
                if not password:
                    raise RuntimeError("全自动模式必须填写密码")
                bundle = _run_auto_login_flow(
                    task_id,
                    email=email,
                    password=password,
                    proxy=effective_proxy,
                    resolved_service=resolved_service,
                    existing_account=existing_account,
                )
            elif mode == "semi_auto":
                if not password:
                    raise RuntimeError("半自动模式仍需填写密码以便回写账号信息")
                bundle = _run_semi_auto_materialize(
                    task_id,
                    email=email,
                    password=password,
                    proxy=effective_proxy,
                    session_token=session_token,
                    cookies=cookies,
                    resolved_service=resolved_service,
                    existing_account=existing_account,
                )
            else:
                raise RuntimeError("不支持的登录模式")

            if existing_account:
                preview = _build_result_preview(bundle, existing_account=existing_account)
                _set_context(
                    task_id,
                    pending_result=bundle,
                    existing_account_id=int(existing_account.id),
                )
                task_manager.update_domain_task(
                    MANUAL_LOGIN_DOMAIN,
                    task_id,
                    status="waiting_confirm_overwrite",
                    message=f"邮箱 {email} 已存在，等待确认是否覆盖",
                    result={
                        "email": email,
                        "mode": mode,
                        "existing_account_id": int(existing_account.id),
                        "preview": preview,
                    },
                    _pending_result=dict(bundle),
                    _existing_account_id=int(existing_account.id),
                    progress={"stage": "persist_account"},
                )
                _append_log(task_id, "warning", "登录成功，但检测到同邮箱账号，等待是否覆盖", stage="persist_account")
                return

            account = _persist_login_bundle(db, bundle=bundle, existing_account=None, overwrite=False)
            _sync_subscription_after_login(task_id, account, proxy)
            db.commit()
            db.refresh(account)
            result_payload = _build_completion_result(bundle, account, action="created")
            task_manager.update_domain_task(
                MANUAL_LOGIN_DOMAIN,
                task_id,
                status="completed",
                finished_at=_now_iso(),
                message="手动登录成功，已创建账号",
                result=result_payload,
                progress={"stage": "done"},
            )
            _append_log(task_id, "success", f"登录成功，已创建账号 #{account.id}", stage="done")
    except PushAuthVerificationRequired as exc:
        task_manager.update_domain_task(
            MANUAL_LOGIN_DOMAIN,
            task_id,
            status="waiting_push_auth",
            finished_at=_now_iso(),
            message="检测到账号需要额外的 Push 验证，请切换半自动或在官方页面完成后继续",
            result={
                "email": email,
                "mode": mode,
                "page_type": exc.page_type,
                "stage": exc.stage,
                "next_action": "open_official_login_and_complete_push_auth",
            },
            progress={"stage": exc.stage},
        )
        _append_log(
            task_id,
            "warning",
            f"检测到 {exc.page_type}，请在 GPT 官方页面完成额外验证后，再改用半自动模式保存结果",
            stage=exc.stage,
        )
    except Exception as exc:
        message = str(exc or "手动登录失败").strip() or "手动登录失败"
        final_status = "cancelled" if task_manager.is_domain_task_cancel_requested(MANUAL_LOGIN_DOMAIN, task_id) else "failed"
        task_manager.update_domain_task(
            MANUAL_LOGIN_DOMAIN,
            task_id,
            status=final_status,
            finished_at=_now_iso(),
            message=message,
            error=message,
            progress={"stage": "done"},
        )
        _append_log(task_id, "error", message, stage="done")
    finally:
        task_manager.release_domain_slot(MANUAL_LOGIN_DOMAIN, task_id)


def start_manual_login_task(request_data: Dict[str, Any], *, proxy: Optional[str]) -> Dict[str, Any]:
    task_id = _task_id()
    sanitized_payload = _sanitize_payload_for_task(request_data)
    snapshot = task_manager.register_domain_task(
        domain=MANUAL_LOGIN_DOMAIN,
        task_id=task_id,
        task_type=MANUAL_LOGIN_TASK_TYPE,
        payload=sanitized_payload,
        progress={"stage": "init"},
        max_retries=0,
    )
    _set_context(
        task_id,
        request=dict(request_data or {}),
        proxy=proxy,
        created_at=_now_iso(),
    )
    task_manager.executor.submit(_execute_manual_login, task_id)
    return snapshot


def get_manual_login_task(task_id: str) -> Optional[Dict[str, Any]]:
    return task_manager.get_domain_task(MANUAL_LOGIN_DOMAIN, task_id)


def cancel_manual_login_task(task_id: str) -> Optional[Dict[str, Any]]:
    snapshot = task_manager.request_domain_task_cancel(MANUAL_LOGIN_DOMAIN, task_id)
    if snapshot:
        _append_log(task_id, "warning", "已提交取消请求", stage="done")
    return snapshot


def confirm_manual_login_task(task_id: str, *, overwrite: bool) -> Dict[str, Any]:
    snapshot = task_manager.get_domain_task(MANUAL_LOGIN_DOMAIN, task_id)
    if not snapshot:
        raise RuntimeError("任务不存在")
    if str(snapshot.get("status") or "").strip().lower() != "waiting_confirm_overwrite":
        raise RuntimeError("当前任务不处于等待覆盖确认状态")

    raw_task = task_manager.get_domain_task_raw(MANUAL_LOGIN_DOMAIN, task_id) or {}
    pending_result = dict(raw_task.get("_pending_result") or {})
    existing_account_id = int(raw_task.get("_existing_account_id") or 0)
    if not pending_result or existing_account_id <= 0:
        context = _get_context(task_id)
        pending_result = dict(context.get("pending_result") or {})
        existing_account_id = int(context.get("existing_account_id") or 0)
    if not pending_result or existing_account_id <= 0:
        raise RuntimeError("任务缺少待确认的登录结果")

    with get_db() as db:
        account = crud.get_account_by_id(db, existing_account_id)
        if not account:
            raise RuntimeError("待覆盖账号不存在")

        pending_account_id = str(pending_result.get("account_id") or "").strip() or "-"
        pending_workspace_id = str(pending_result.get("workspace_id") or "").strip() or "-"
        pending_workspace_name = str(pending_result.get("selected_workspace_name") or "").strip() or "-"
        current_account_id = str(getattr(account, "account_id", "") or "").strip() or "-"
        current_workspace_id = str(getattr(account, "workspace_id", "") or "").strip() or "-"

        if not overwrite:
            result_payload = _build_completion_result(pending_result, account, action="skipped")
            task_manager.update_domain_task(
                MANUAL_LOGIN_DOMAIN,
                task_id,
                status="completed",
                finished_at=_now_iso(),
                message="用户取消覆盖，登录结果未写回账号",
                result=result_payload,
                _pending_result=None,
                _existing_account_id=None,
                progress={"stage": "done"},
            )
            _append_log(
                task_id,
                "warning",
                "用户取消覆盖："
                f"账号ID保持 {current_account_id}，"
                f"workspace保持 {current_workspace_id}；"
                f"本次结果 account_id={pending_account_id} workspace_id={pending_workspace_id} workspace_name={pending_workspace_name}",
                stage="done",
            )
            _append_log(task_id, "warning", "用户取消覆盖，本次登录结果未写回", stage="done")
            _set_context(task_id, pending_result=None, existing_account_id=None)
            return task_manager.get_domain_task(MANUAL_LOGIN_DOMAIN, task_id) or {}

        _append_log(
            task_id,
            "info",
            "开始覆盖写回账号："
            f"账号ID {current_account_id} -> {pending_account_id}；"
            f"workspace {current_workspace_id} -> {pending_workspace_id}；"
            f"workspace_name={pending_workspace_name}",
            stage="persist_account",
        )
        try:
            updated = _persist_login_bundle(db, bundle=pending_result, existing_account=account, overwrite=True)
            _sync_subscription_after_login(task_id, updated, pending_result.get("proxy_used"))
            db.commit()
            db.refresh(updated)
            result_payload = _build_completion_result(pending_result, updated, action="updated")
            task_manager.update_domain_task(
                MANUAL_LOGIN_DOMAIN,
                task_id,
                status="completed",
                finished_at=_now_iso(),
                message="登录结果已覆盖更新到现有账号",
                result=result_payload,
                _pending_result=None,
                _existing_account_id=None,
                progress={"stage": "done"},
            )
            _append_log(
                task_id,
                "success",
                "覆盖写回完成："
                f"账号ID={str(getattr(updated, 'account_id', '') or '').strip() or '-'}，"
                f"workspace_id={str(getattr(updated, 'workspace_id', '') or '').strip() or '-'}",
                stage="done",
            )
            _append_log(task_id, "success", f"已覆盖更新账号 #{updated.id}", stage="done")
            _set_context(task_id, pending_result=None, existing_account_id=None)
            return task_manager.get_domain_task(MANUAL_LOGIN_DOMAIN, task_id) or {}
        except Exception as exc:
            try:
                db.rollback()
            except Exception:
                pass
            _append_log(
                task_id,
                "error",
                f"覆盖写回失败：{exc}",
                stage="persist_account",
            )
            raise RuntimeError(f"覆盖写回失败: {exc}") from exc


def query_inbox_code(
    *,
    email: str,
    proxy: Optional[str],
    email_service_id: Optional[int] = None,
) -> Dict[str, Any]:
    email_lower = str(email or "").strip().lower()
    if not email_lower:
        raise RuntimeError("邮箱不能为空")

    with get_db() as db:
        existing_account = crud.get_account_by_email(db, email_lower)
        resolved = _resolve_manual_login_service(
            db,
            email=email_lower,
            proxy=proxy,
            existing_account=existing_account,
            email_service_id=email_service_id,
        )
        code = resolved.service.get_verification_code(
            email=email_lower,
            email_id=None,
            timeout=60,
        )
        if not code:
            raise RuntimeError("未收到验证码邮件")
        return {
            "success": True,
            "email": email_lower,
            "code": code,
            "service_type": resolved.service_type.value,
            "service_name": resolved.service_name,
        }
