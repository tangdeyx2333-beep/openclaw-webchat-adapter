from __future__ import annotations

import queue
import time
from typing import Any, Dict, Iterator, List, Optional
from ..ws_adapter import (
    OpenClawChatWsAdapter,
    DeviceIdentityPlaceholder,
    ChatHistory,
    ChatContentItem,
    ChatMessage,
    ChatUsage,
    ChatUsageCost,
    _uuid,
    _extract_chat_text
)
from ..config import AdapterSettings
from ..exceptions import (
    GatewayClosedError,
    ChatTimeoutError,
    ChatFailedError
)

class OpenClawWebChatAPI:
    """OpenClaw WebChat API 封装类，提供更简洁的调用接口。"""

    def __init__(self, adapter: OpenClawChatWsAdapter):
        """初始化 API 实例。

        Args:
            adapter: 底层使用的 OpenClawChatWsAdapter 实例。
        """
        self._adapter = adapter

    @classmethod
    def create_connected_from_env(
        cls,
        token: Optional[str] = None,
        password: Optional[str] = None,
        url: Optional[str] = None,
        dotenv_path: str = ".env",
        dotenv_override: bool = False,
        ensure_session_key: str = "main",
        timeout_s: float = 12.0,
        device: Optional[DeviceIdentityPlaceholder] = None,
    ) -> OpenClawWebChatAPI:
        """从 .env / 环境变量加载配置并建立连接，返回已就绪的 API 实例。

        Args:
            token: 显式传入的网关鉴权 token。
            password: 显式传入的网关鉴权 password。
            url: 显式传入的网关 WebSocket URL。
            dotenv_path: `.env` 文件路径。
            dotenv_override: `.env` 中的值是否覆盖 `os.environ`。
            ensure_session_key: 启动后确保的会话 key。
            timeout_s: 连接超时秒数。
            device: 可选的设备身份信息。

        Returns:
            OpenClawWebChatAPI: 已连接并就绪的 API 实例。
        """
        adapter = OpenClawChatWsAdapter.create_connected_from_env(
            token=token,
            password=password,
            url=url,
            dotenv_path=dotenv_path,
            dotenv_override=dotenv_override,
            ensure_session_key=ensure_session_key,
            timeout_s=timeout_s,
            device=device
        )
        return cls(adapter)

    def get_chat_history(
        self,
        session_key: Optional[str] = None,
        limit: int = 200,
        timeout_s: float = 15.0,
    ) -> ChatHistory:
        """获取指定会话的历史聊天记录。

        Args:
            session_key: 会话标识符，若为 None 则使用配置中的默认值。
            limit: 返回的消息条数限制。
            timeout_s: 请求超时秒数。

        Returns:
            ChatHistory: 包含会话元数据和消息列表的历史记录对象。
        """
        return self._adapter.get_chat_history(
            session_key=session_key,
            limit=limit,
            timeout_s=timeout_s
        )

    def stream_chat(self, user_request: str, timeout_s: float = 120.0) -> Iterator[str]:
        """针对用户输入流式产出 assistant 的增量文本片段。

        Args:
            user_request: 用户发送的消息文本。
            timeout_s: 对话最大超时秒数。

        Yields:
            str: assistant 的增量文本片段。

        Raises:
            GatewayClosedError: 网关连接关闭。
            ChatTimeoutError: 对话超时。
            ChatFailedError: 对话失败。
        """
        yield from self._adapter.stream_chat(user_request, timeout_s=timeout_s)

    def get_chat_history_simple(
        self,
        session_key: Optional[str] = None,
    ) -> List[Any]:
        """获取指定会话的历史聊天数据（返回简化的消息列表）。

        Args:
            session_key: 会话标识符，默认使用配置中的 session_key。

        Returns:
            List: 包含简化消息对象的列表。
        """
        return self._adapter.get_chat_history_simple(session_key=session_key)

    def stop(self) -> None:
        """停止并关闭底层的 WebSocket 连接。"""
        self._adapter.stop()

    def close(self) -> None:
        """关闭底层的 WebSocket 连接。"""
        self.stop()
