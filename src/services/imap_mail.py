"""
IMAP 邮箱服务
支持 Gmail / QQ / 163 / 126 / Yeah 等标准 IMAP 协议邮件服务商。

当前文件为兼容版实现：
- 保留旧版 imaplib 逻辑作为后备
- 对 Coremail 系（126/163/yeah）优先使用更兼容的原始 IMAP 会话流程
"""

from __future__ import annotations

import email as email_module
import logging
import re
import socket
import ssl
import time
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

from .imap_mail_legacy import ImapMailService as LegacyImapMailService

logger = logging.getLogger(__name__)


def _quote_imap(value: str) -> str:
    """按 IMAP quoted string 规则转义。"""
    escaped = str(value or "").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


@dataclass
class _RawImapCommandResult:
    status: str
    text: str
    lines: List[str]
    literals: List[bytes]


class _RawImapClient:
    """
    极简原始 IMAP 客户端。

    只实现当前项目所需的最小指令集：
    CAPABILITY / ID / LOGIN / LIST / LSUB / SELECT / SEARCH / FETCH / STORE / LOGOUT
    """

    ID_PAYLOAD = (
        '("name" "imapflow" "version" "1.2.18" '
        '"vendor" "Postal Systems" '
        '"support-url" "https://github.com/postalsys/imapflow/issues")'
    )

    def __init__(self, host: str, port: int, use_ssl: bool = True, timeout: int = 30):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.timeout = timeout
        self._socket: Optional[socket.socket] = None
        self._reader = None
        self._tag_index = 0
        self.capabilities: Set[str] = set()
        self._greeting = ""

    def __enter__(self) -> "_RawImapClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def connect(self) -> None:
        if self._socket:
            return

        sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        sock.settimeout(self.timeout)
        if self.use_ssl:
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=self.host)

        self._socket = sock
        self._reader = sock.makefile("rb")
        greeting = self._reader.readline()
        if not greeting:
            raise RuntimeError("IMAP 服务器未返回欢迎信息")
        self._greeting = greeting.decode("utf-8", errors="replace").rstrip("\r\n")
        logger.debug("IMAP greeting [%s]: %s", self.host, self._greeting)

    def close(self) -> None:
        if self._socket:
            try:
                self.logout()
            except Exception:
                pass
        if self._reader:
            try:
                self._reader.close()
            except Exception:
                pass
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
        self._reader = None
        self._socket = None

    def _next_tag(self) -> str:
        self._tag_index += 1
        return f"A{self._tag_index}"

    def execute(self, command: str, tolerate_fail: bool = False) -> _RawImapCommandResult:
        if not self._socket or not self._reader:
            raise RuntimeError("IMAP 连接尚未建立")

        tag = self._next_tag()
        wire = f"{tag} {command}\r\n".encode("utf-8")
        self._socket.sendall(wire)

        lines: List[str] = []
        literals: List[bytes] = []
        status = ""
        text = ""

        while True:
            line = self._reader.readline()
            if not line:
                raise RuntimeError(f"IMAP 命令执行中连接已关闭: {command}")

            decoded = line.decode("utf-8", errors="replace").rstrip("\r\n")
            lines.append(decoded)

            literal_match = re.search(r"\{(\d+)\}$", decoded)
            if literal_match:
                literal_size = int(literal_match.group(1))
                literal = self._reader.read(literal_size)
                if literal is None or len(literal) != literal_size:
                    raise RuntimeError(f"IMAP literal 读取不完整: {command}")
                literals.append(literal)
                crlf = self._reader.read(2)
                if crlf != b"\r\n":
                    raise RuntimeError(f"IMAP literal 结尾异常: {command}")

            if decoded.startswith(f"{tag} "):
                parts = decoded.split(" ", 2)
                status = parts[1].upper() if len(parts) > 1 else ""
                text = parts[2] if len(parts) > 2 else ""
                break

        result = _RawImapCommandResult(
            status=status,
            text=text,
            lines=lines,
            literals=literals,
        )

        if status != "OK" and not tolerate_fail:
            raise RuntimeError(f"{command.split(' ', 1)[0]} 失败: {text or status}")

        return result

    def capability(self) -> Set[str]:
        result = self.execute("CAPABILITY")
        caps: Set[str] = set()
        for line in result.lines:
            if line.startswith("* CAPABILITY "):
                caps = {item.strip().upper() for item in line[len("* CAPABILITY ") :].split() if item.strip()}
                break
        self.capabilities = caps
        return caps

    def send_id(self) -> None:
        if "ID" not in self.capabilities:
            return
        self.execute(f"ID {self.ID_PAYLOAD}", tolerate_fail=True)

    def login(self, username: str, password: str) -> None:
        self.execute(f"LOGIN {_quote_imap(username)} {_quote_imap(password)}")

    def bootstrap_session(self, username: str, password: str) -> None:
        self.capability()
        self.send_id()
        self.login(username, password)
        self.capability()
        self.execute('LIST "" ""', tolerate_fail=True)
        self.execute('LIST "" "INBOX"', tolerate_fail=True)
        self.execute('LSUB "" "INBOX"', tolerate_fail=True)

    def select(self, mailbox: str = "INBOX") -> int:
        result = self.execute(f"SELECT {mailbox}")
        exists = 0
        for line in result.lines:
            match = re.match(r"^\* (\d+) EXISTS$", line)
            if match:
                exists = int(match.group(1))
        return exists

    def search_unseen(self) -> List[int]:
        result = self.execute("SEARCH UNSEEN")
        for line in result.lines:
            if line.startswith("* SEARCH"):
                suffix = line[len("* SEARCH") :].strip()
                if not suffix:
                    return []
                return [int(part) for part in suffix.split() if part.isdigit()]
        return []

    def fetch_rfc822(self, sequence_id: int) -> Tuple[Optional[int], bytes]:
        result = self.execute(f"FETCH {sequence_id} (UID RFC822)")
        if not result.literals:
            raise RuntimeError(f"FETCH {sequence_id} 未返回邮件正文")

        uid = None
        for line in result.lines:
            uid_match = re.search(r"UID (\d+)", line)
            if uid_match:
                uid = int(uid_match.group(1))
                break

        return uid, result.literals[0]

    def mark_seen(self, sequence_id: int) -> None:
        self.execute(f"STORE {sequence_id} +FLAGS (\\Seen)", tolerate_fail=True)

    def logout(self) -> None:
        if self._socket and self._reader:
            try:
                self.execute("LOGOUT", tolerate_fail=True)
            except Exception:
                pass


class ImapMailService(LegacyImapMailService):
    """标准 IMAP 邮箱服务，Coremail 系优先使用兼容会话流程。"""

    COREMAIL_HOST_SUFFIXES = ("126.com", "163.com", "yeah.net")

    def _should_use_raw_compat(self) -> bool:
        host = (self.host or "").strip().lower()
        return bool(self.use_ssl and host.endswith(self.COREMAIL_HOST_SUFFIXES))

    def _create_raw_client(self) -> _RawImapClient:
        return _RawImapClient(
            host=self.host,
            port=self.port,
            use_ssl=self.use_ssl,
            timeout=self.timeout,
        )

    def _connect_with_raw_compat(self) -> _RawImapClient:
        client = self._create_raw_client()
        client.connect()
        client.bootstrap_session(self.email_addr, self.password)
        return client

    def get_verification_code(
        self,
        email: str,
        email_id: str = None,
        timeout: int = 60,
        pattern: str = None,
        otp_sent_at: Optional[float] = None,
    ) -> Optional[str]:
        if not self._should_use_raw_compat():
            return super().get_verification_code(
                email=email,
                email_id=email_id,
                timeout=timeout,
                pattern=pattern,
                otp_sent_at=otp_sent_at,
            )

        start_time = time.time()
        seen_ids: Set[int] = set()
        client: Optional[_RawImapClient] = None

        try:
            client = self._connect_with_raw_compat()
            client.select("INBOX")

            while time.time() - start_time < timeout:
                try:
                    message_ids = client.search_unseen()
                    if not message_ids:
                        time.sleep(3)
                        continue

                    for seq_id in reversed(message_ids):
                        if seq_id in seen_ids:
                            continue
                        seen_ids.add(seq_id)

                        _uid, raw = client.fetch_rfc822(seq_id)
                        msg = email_module.message_from_bytes(raw)

                        from_addr = self._decode_str(msg.get("From", ""))
                        if not self._is_openai_sender(from_addr):
                            continue

                        body = self._get_text_body(msg)
                        code = self._extract_otp(body)
                        if code:
                            client.mark_seen(seq_id)
                            self.update_status(True)
                            logger.info("IMAP(Coremail兼容) 获取验证码成功: %s", code)
                            return code

                except Exception as e:
                    logger.debug("IMAP(Coremail兼容) 搜索邮件失败: %s", e)
                    try:
                        if client:
                            client.select("INBOX")
                    except Exception:
                        pass

                time.sleep(3)

        except Exception as e:
            logger.warning("IMAP(Coremail兼容) 连接/轮询失败: %s", e)
            self.update_status(False, str(e))
        finally:
            if client:
                client.close()

        return None

    def check_health(self) -> bool:
        if not self._should_use_raw_compat():
            return super().check_health()

        client: Optional[_RawImapClient] = None
        try:
            client = self._connect_with_raw_compat()
            client.select("INBOX")
            self.update_status(True)
            return True
        except Exception as e:
            logger.warning("IMAP(Coremail兼容) 健康检查失败: %s", e)
            self.update_status(False, str(e))
            return False
        finally:
            if client:
                client.close()
