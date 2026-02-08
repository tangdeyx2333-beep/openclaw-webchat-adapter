"""为 OpenClaw Gateway 适配器提供配置加载能力。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from .env import load_dotenv
from .exceptions import ConfigurationError


def _require_non_empty(value: Optional[str], name: str) -> str:
    """校验配置项存在且非空，并返回清洗后的字符串。

    Args:
        value: 待校验的输入值。
        name: 配置项名称，用于错误消息。

    Returns:
        去除首尾空白后的字符串值。

    Raises:
        ConfigurationError: 当配置缺失或为空白时抛出。
    """

    if value is None or not str(value).strip():
        raise ConfigurationError(f"Missing required configuration: {name}")
    return str(value).strip()


def _resolve_dotenv_path(dotenv_path: str) -> str:
    """在不同工作目录运行时，尽可能稳健地解析 .env 的实际路径。

    Args:
        dotenv_path: 调用方传入的路径，可为绝对路径或相对路径。

    Returns:
        若在解析出的候选位置找到文件则返回其绝对路径；否则返回原始输入，
        以便 load_dotenv 在文件不存在时自然成为 no-op。
    """

    if not isinstance(dotenv_path, str) or not dotenv_path.strip():
        return dotenv_path

    candidate = dotenv_path
    if os.path.isabs(candidate) and os.path.exists(candidate):
        return candidate

    if not os.path.isabs(candidate):
        if os.path.exists(candidate):
            return os.path.abspath(candidate)
        package_root = os.path.dirname(os.path.abspath(__file__))
        src_root = os.path.dirname(package_root)
        src_candidate = os.path.abspath(os.path.join(src_root, candidate))
        if os.path.exists(src_candidate):
            return src_candidate
        project_root = os.path.dirname(src_root)
        project_candidate = os.path.abspath(os.path.join(project_root, candidate))
        if os.path.exists(project_candidate):
            return project_candidate

    return dotenv_path


@dataclass(frozen=True)
class AdapterSettings:
    """保存连接 OpenClaw Gateway 实例所需的配置项。

    Args:
        url: 网关 WebSocket URL。
        token: 基于 token 的鉴权凭据（可选）。
        password: 基于密码的鉴权凭据（可选）。
        session_key: chat 请求使用的 session key。
        client_id: connect 握手中的 client.id。
        client_mode: connect 握手中的 client.mode。
        client_display_name: connect 握手中的 client.displayName。
        client_version: connect 握手中的 client.version。
        platform: connect 握手中的 client.platform。
        instance_id: connect 握手中的 client.instanceId。
        protocol_version: connect 握手使用的协议版本。
        role: connect 请求中的 role 字段。
        scopes_csv: 逗号分隔的 scopes 列表字符串。
        connect_fallback_delay_s: 若未收到 challenge，则延迟后发送 connect 的兜底等待时间。
        handshake_poll_interval_s: 等待 hello-ok 时的轮询 sleep 间隔。
        chat_poll_interval_s: 等待 chat 事件时的队列轮询间隔。
    """

    url: str = "ws://127.0.0.1:18789"
    token: Optional[str] = None
    password: Optional[str] = None
    session_key: str = "agent:main:main"

    client_id: str = "webchat-ui"
    client_mode: str = "webchat"
    client_display_name: str = "py-adapter"
    client_version: str = "dev"
    platform: str = "browser"
    instance_id: Optional[str] = None

    protocol_version: int = 3
    role: str = "operator"
    scopes_csv: str = "operator.admin"
    connect_fallback_delay_s: float = 0.75
    handshake_poll_interval_s: float = 0.01
    chat_poll_interval_s: float = 0.2

    @classmethod
    def from_env(cls, dotenv_path: str = ".env", dotenv_override: bool = False) -> "AdapterSettings":
        """从环境变量与可选的 .env 文件加载配置并构造 AdapterSettings。

        Args:
            dotenv_path: .env 文件路径。若文件不存在，则仅读取 os.environ。
            dotenv_override: .env 中的值是否覆盖 os.environ 中已存在的同名变量。

        Returns:
            AdapterSettings 实例。

        Raises:
            ConfigurationError: 当必需配置项缺失或格式不合法时抛出。
        """

        resolved_dotenv_path = _resolve_dotenv_path(dotenv_path)
        load_dotenv(path=resolved_dotenv_path, override=dotenv_override)

        url = os.getenv("OPENCLAW_GATEWAY_URL") or cls.url
        token = os.getenv("OPENCLAW_GATEWAY_TOKEN") or None
        password = os.getenv("OPENCLAW_GATEWAY_PASSWORD") or None
        session_key = os.getenv("OPENCLAW_SESSION_KEY") or cls.session_key

        protocol_version_raw = os.getenv("OPENCLAW_PROTOCOL_VERSION")
        protocol_version = cls.protocol_version
        if protocol_version_raw and protocol_version_raw.strip():
            try:
                protocol_version = int(protocol_version_raw)
            except ValueError as e:
                raise ConfigurationError("OPENCLAW_PROTOCOL_VERSION must be an integer") from e

        client_id = os.getenv("OPENCLAW_CLIENT_ID") or cls.client_id
        client_mode = os.getenv("OPENCLAW_CLIENT_MODE") or cls.client_mode
        client_display_name = os.getenv("OPENCLAW_CLIENT_DISPLAY_NAME") or cls.client_display_name
        client_version = os.getenv("OPENCLAW_CLIENT_VERSION") or cls.client_version
        platform = os.getenv("OPENCLAW_CLIENT_PLATFORM") or cls.platform
        instance_id = os.getenv("OPENCLAW_CLIENT_INSTANCE_ID") or None

        role = os.getenv("OPENCLAW_CONNECT_ROLE") or cls.role
        scopes_csv = os.getenv("OPENCLAW_CONNECT_SCOPES") or cls.scopes_csv

        url = _require_non_empty(url, "OPENCLAW_GATEWAY_URL")
        session_key = _require_non_empty(session_key, "OPENCLAW_SESSION_KEY")

        return cls(
            url=url,
            token=token,
            password=password,
            session_key=session_key,
            client_id=client_id,
            client_mode=client_mode,
            client_display_name=client_display_name,
            client_version=client_version,
            platform=platform,
            instance_id=instance_id,
            protocol_version=protocol_version,
            role=role,
            scopes_csv=scopes_csv,
        )
