"""实现 OpenClaw Gateway 协议的 WebSocket 适配器。"""

from __future__ import annotations

import json
import logging
import queue
import threading
import time
import uuid
from dataclasses import dataclass, replace
from typing import Any, Callable, Dict, Iterator, List, Optional

from .config import AdapterSettings

from .exceptions import (
    ChatFailedError,
    ChatTimeoutError,
    GatewayClosedError,
    ProtocolError,
    RequestFailedError,
    RequestTimeoutError,
)

_logger = logging.getLogger(__name__)

def _uuid() -> str:
    """生成一个 UUID4 字符串，用于 requestId 与 runId。

    Returns:
        UUID4 字符串。
    """

    return str(uuid.uuid4())


def _extract_chat_text(message_obj: Any) -> str:
    """从网关 chat payload 的 message 对象中提取 assistant 文本。

    Args:
        message_obj: chat event 中的 payload.message 对象。

    Returns:
        提取到的文本；若不可提取则返回空字符串。
    """

    if not isinstance(message_obj, dict):
        return ""
    content = message_obj.get("content")
    if not isinstance(content, list) or not content:
        return ""
    first = content[0]
    if not isinstance(first, dict):
        return ""
    text = first.get("text")
    return text if isinstance(text, str) else ""


@dataclass(frozen=True)
class DeviceIdentityPlaceholder:
    """表示用于未来“签名连接”的 device 身份字段占位结构。"""

    id: str
    public_key: str
    signature: str
    signed_at: int
    nonce: Optional[str] = None

@dataclass(frozen=True)
class ChatContentItem:
    type: str
    text: str

@dataclass(frozen=True)
class ChatUsageCost:
    input: int
    output: int
    cacheRead: int
    cacheWrite: int
    total: int

@dataclass(frozen=True)
class ChatUsage:
    input: int
    output: int
    cacheRead: int
    cacheWrite: int
    totalTokens: int
    cost: ChatUsageCost

@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: List[ChatContentItem]
    timestamp: int
    api: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    usage: Optional[ChatUsage] = None
    stop_reason: Optional[str] = None

@dataclass(frozen=True)
class ChatMessage_Simple:
    role: str
    content: List[ChatContentItem]
    timestamp: int


@dataclass(frozen=True)
class ChatHistory:
    session_key: str
    session_id: str
    messages: List[ChatMessage]
    thinking_level: Optional[str] = None




class OpenClawChatWsAdapter:
    """通过 WebSocket 连接 OpenClaw Gateway，并提供流式聊天 API。"""

    @classmethod
    def create_connected(
        cls,
        settings: AdapterSettings,
        ensure_session_key: str = "main",
        timeout_s: float = 12.0,
        device: Optional[DeviceIdentityPlaceholder] = None,
        ws_factory: Optional[WsFactory] = None,
    ) -> "OpenClawGatewayWsAdapter":
        """创建适配器实例并在返回前完成握手与会话准备。

        Args:
            settings: 连接与握手配置。
            ensure_session_key: 启动后用于 sessions.patch 的会话 key。
            timeout_s: 等待 hello-ok 的最大秒数。
            device: 可选的设备身份占位信息，用于未来签名式 connect。
            ws_factory: 可选的 WebSocketApp 工厂，用于测试/依赖注入。

        Returns:
            已完成握手并确保会话可发送的适配器实例。

        Raises:
            GatewayClosedError: 当握手完成前网关连接被关闭时抛出。
            RequestTimeoutError: 当超时仍未收到 hello-ok 时抛出。
            RuntimeError: 当底层 WS 出错或依赖缺失时抛出。
        """

        adapter = cls(settings=settings, device=device, ws_factory=ws_factory)
        hello = adapter.start(timeout_s=timeout_s)
        server = hello.get("server") if isinstance(hello, dict) else None
        conn_id = server.get("connId") if isinstance(server, dict) else None
        protocol = hello.get("protocol") if isinstance(hello, dict) else None
        _logger.warning("已连接 OpenClaw Gateway：url=%s protocol=%s connId=%s", settings.url, protocol, conn_id)
        adapter.ensure_session(ensure_session_key)
        _logger.warning("会话已就绪：session=%s sendPolicy=allow", ensure_session_key)
        return adapter

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
        ws_factory: Optional[WsFactory] = None,
    ) -> "OpenClawGatewayWsAdapter":
        """从 .env / 环境变量加载配置并建立连接，返回已就绪的适配器实例。

        Args:
            token: 显式传入的网关鉴权 token；若为 None 则使用环境变量/`.env` 的值。
            password: 显式传入的网关鉴权 password；若为 None 则使用环境变量/`.env` 的值。
            url: 显式传入的网关 WebSocket URL；若为 None 则使用环境变量/`.env` 的值。
            dotenv_path: `.env` 文件路径；文件不存在时仅读取 `os.environ`。
            dotenv_override: `.env` 中的值是否覆盖 `os.environ` 中已存在的同名变量。
            ensure_session_key: 启动后用于 sessions.patch 的会话 key。
            timeout_s: 等待 hello-ok 的最大秒数。
            device: 可选的设备身份占位信息，用于未来签名式 connect。
            ws_factory: 可选的 WebSocketApp 工厂，用于测试/依赖注入。

        Returns:
            已完成握手并确保会话可发送的适配器实例。
        """

        def _normalize_optional(value: Optional[str]) -> Optional[str]:
            if value is None:
                return None
            stripped = str(value).strip()
            return stripped or None

        settings = AdapterSettings.from_env(dotenv_path=dotenv_path, dotenv_override=dotenv_override)

        url = _normalize_optional(url)
        token = _normalize_optional(token)
        password = _normalize_optional(password)

        if url is not None or token is not None or password is not None:
            settings = replace(
                settings,
                url=url if url is not None else settings.url,
                token=token if token is not None else settings.token,
                password=password if password is not None else settings.password,
            )

        return cls.create_connected(
            settings=settings,
            ensure_session_key=ensure_session_key,
            timeout_s=timeout_s,
            device=device,
            ws_factory=ws_factory,
        )

    def __init__(
        self,
        settings: AdapterSettings,
        device: Optional[DeviceIdentityPlaceholder] = None,
        ws_factory: Optional[WsFactory] = None,
    ):
        """初始化适配器并准备握手相关状态。

        Args:
            settings: 连接与握手配置。
            device: 可选的设备身份占位信息，用于未来签名式 connect。
            ws_factory: 可选的 WebSocketApp 工厂，用于测试/依赖注入。
        """

        self._settings = settings
        self._device = device
        self._ws_factory = ws_factory or self._default_ws_factory

        self._ws: Optional[Any] = None
        self._thread: Optional[threading.Thread] = None
        self._closed = threading.Event()
        self._hello_ok = threading.Event()
        self._hello_payload: Optional[Dict[str, Any]] = None
        self._connect_nonce: Optional[str] = None
        self._connect_sent = False
        self._connect_req_id: Optional[str] = None
        self._last_error: Optional[BaseException] = None

        self._pending: Dict[str, "queue.Queue[Dict[str, Any]]"] = {}
        self._pending_lock = threading.Lock()

        self._chat_queues: Dict[str, "queue.Queue[Dict[str, Any]]"] = {}
        self._chat_lock = threading.Lock()

    @property
    def hello_payload(self) -> Optional[Dict[str, Any]]:
        """在 start() 成功后返回 hello-ok 的 payload。

        Returns:
            hello-ok 的 payload 字典；若不可用则为 None。
        """

        return self._hello_payload

    def start(self, timeout_s: float = 12.0) -> Dict[str, Any]:
        """启动 WebSocket 连接并等待握手完成。

        Args:
            timeout_s: 等待 hello-ok 的最大秒数。

        Returns:
            hello-ok 的 payload 字典。

        Raises:
            GatewayClosedError: 当握手完成前网关连接被关闭时抛出。
            RequestTimeoutError: 当超时仍未收到 hello-ok 时抛出。
            RuntimeError: 当 start() 被重复调用或底层 WS 出错时抛出。
        """

        if self._ws is not None:
            raise RuntimeError("Adapter already started")

        self._closed.clear()
        self._hello_ok.clear()
        self._hello_payload = None
        self._connect_nonce = None
        self._connect_sent = False
        self._connect_req_id = None
        self._last_error = None

        self._ws = self._ws_factory(
            self._settings.url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self._thread = threading.Thread(target=self._ws.run_forever, daemon=True)
        self._thread.start()

        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if self._hello_ok.is_set():
                return self._hello_payload or {}
            if self._closed.is_set():
                if self._last_error:
                    raise RuntimeError(str(self._last_error))
                raise GatewayClosedError("Gateway closed before hello-ok")
            time.sleep(self._settings.handshake_poll_interval_s)
        if self._last_error:
            raise RuntimeError(str(self._last_error))
        raise RequestTimeoutError("Handshake timeout: hello-ok not received")

    def stop(self) -> None:
        """关闭 WebSocket 连接（尽力而为）。"""

        if self._ws is None:
            return
        try:
            self._ws.close()
        finally:
            self._closed.set()
            self._ws = None

    def request(self, method: str, params: Optional[Dict[str, Any]] = None, timeout_s: float = 15.0) -> Dict[str, Any]:
        """发送一次 RPC 请求并等待响应。

        Args:
            method: RPC 方法名。
            params: RPC 参数字典。
            timeout_s: 等待响应的最大秒数。

        Returns:
            响应 payload 字典。

        Raises:
            RequestTimeoutError: 当超时仍未收到响应时抛出。
            RequestFailedError: 当网关返回 ok=false 时抛出。
            ValueError: 当 method/params 的输入类型不合法时抛出。
            RuntimeError: 当握手未完成即调用时抛出。
        """

        if not self._hello_ok.is_set():
            raise RuntimeError("Gateway not connected (hello-ok not received)")
        if not isinstance(method, str) or not method.strip():
            raise ValueError("method must be a non-empty string")
        if params is not None and not isinstance(params, dict):
            raise ValueError("params must be a dict or None")

        req_id = _uuid()
        q: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[req_id] = q

        frame = {"type": "req", "id": req_id, "method": method, "params": params or {}}
        self._send(frame)
        try:
            res = q.get(timeout=timeout_s)
        except queue.Empty as e:
            raise RequestTimeoutError(f"Request timeout: {method}") from e
        finally:
            with self._pending_lock:
                self._pending.pop(req_id, None)

        if res.get("ok") is True:
            payload = res.get("payload")
            return payload if isinstance(payload, dict) else {"payload": payload}
        err = res.get("error") or {}
        message = err.get("message") if isinstance(err, dict) else None
        raise RequestFailedError(message or "Request failed")

    def ensure_session(self, key: str = "main", timeout_s: float = 15.0) -> Dict[str, Any]:
        """确保指定 session 存在，并按会话策略允许发送聊天。

        Args:
            key: 需要 patch 的 session key 名称。
            timeout_s: 等待 RPC 响应的最大秒数。

        Returns:
            响应 payload 字典。
        """

        if not isinstance(key, str) or not key.strip():
            raise ValueError("key must be a non-empty string")
        return self.request("sessions.patch", {"key": key, "sendPolicy": "allow"}, timeout_s=timeout_s)

    def get_chat_history_simple(
            self,
            session_key: Optional[str] = None,
    ) -> List[ChatMessage_Simple]:
        """获取指定会话的历史聊天数据（返回简化的消息列表，只包含role和content）。
        
        Args:
            session_key: 会话标识符，默认使用配置中的session_key
            
        Returns:
            List[ChatMessage_Simple]: 包含简化消息对象的列表
        """
        full_history = self.get_chat_history(session_key)
        return [
            ChatMessage_Simple(
                role=msg.role,
                content=msg.content,
                timestamp=msg.timestamp
            )
            for msg in full_history.messages
        ]


    def get_chat_history(
        self,
        session_key: str,
        limit: int = 200,
        timeout_s: float = 15.0,
    ) -> ChatHistory:
        if session_key is not None and (not isinstance(session_key, str) or not session_key.strip()):
            raise ValueError("session_key must be a non-empty string or None")
        if not isinstance(limit, int) or limit <= 0:
            raise ValueError("limit must be a positive integer")
        params = {
            "sessionKey": session_key or self._settings.session_key,
            "limit": limit,
        }
        payload = self.request("chat.history", params, timeout_s=timeout_s)
        return self._map_chat_history_payload(payload)

    def _map_chat_history_payload(self, payload: Dict[str, Any]) -> ChatHistory:
        sk = payload.get("sessionKey")
        sid = payload.get("sessionId")
        tl = payload.get("thinkingLevel")
        msgs_raw = payload.get("messages") or []
        msgs: List[ChatMessage] = []
        if isinstance(msgs_raw, list):
            for m in msgs_raw:
                if not isinstance(m, dict):
                    continue
                role = m.get("role")
                ts = m.get("timestamp")
                contents: List[ChatContentItem] = []
                content_raw = m.get("content") or []
                if isinstance(content_raw, list):
                    for c in content_raw:
                        if isinstance(c, dict):
                            t = c.get("type")
                            tx = c.get("text")
                            if isinstance(t, str) and isinstance(tx, str):
                                contents.append(ChatContentItem(type=t, text=tx))
                api = m.get("api")
                provider = m.get("provider")
                model = m.get("model")
                usage_obj = None
                usage_raw = m.get("usage")
                if isinstance(usage_raw, dict):
                    cost_raw = usage_raw.get("cost")
                    if isinstance(cost_raw, dict):
                        cost = ChatUsageCost(
                            input=cost_raw.get("input", 0),
                            output=cost_raw.get("output", 0),
                            cacheRead=cost_raw.get("cacheRead", 0),
                            cacheWrite=cost_raw.get("cacheWrite", 0),
                            total=cost_raw.get("total", 0),
                        )
                        usage_obj = ChatUsage(
                            input=usage_raw.get("input", 0),
                            output=usage_raw.get("output", 0),
                            cacheRead=usage_raw.get("cacheRead", 0),
                            cacheWrite=usage_raw.get("cacheWrite", 0),
                            totalTokens=usage_raw.get("totalTokens", 0),
                            cost=cost,
                        )
                stop_reason = m.get("stopReason")
                if isinstance(role, str) and isinstance(ts, int):
                    msgs.append(
                        ChatMessage(
                            role=role,
                            content=contents,
                            timestamp=ts,
                            api=api if isinstance(api, str) else None,
                            provider=provider if isinstance(provider, str) else None,
                            model=model if isinstance(model, str) else None,
                            usage=usage_obj,
                            stop_reason=stop_reason if isinstance(stop_reason, str) else None,
                        )
                    )
        return ChatHistory(
            session_key=sk if isinstance(sk, str) else "",
            session_id=sid if isinstance(sid, str) else "",
            messages=msgs,
            thinking_level=tl if isinstance(tl, str) else None,
        )

    def stream_chat(self, user_request: str, timeout_s: float = 120.0) -> Iterator[str]:
        """针对用户输入流式产出 assistant 的增量文本片段。

        Args:
            user_request: 作为 chat message 发送的用户文本。
            timeout_s: 等待对话完成的最大秒数。

        Yields:
            assistant 的增量文本片段。

        Raises:
            GatewayClosedError: 当流式过程中网关连接关闭时抛出。
            ChatTimeoutError: 当对话在超时时间内未完成时抛出。
            ChatFailedError: 当对话以 error/aborted 状态结束时抛出。
        """

        if not isinstance(user_request, str) or not user_request.strip():
            return iter(())

        run_id = _uuid()
        q: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        with self._chat_lock:
            self._chat_queues[run_id] = q

        try:
            _ = self.request(
                "chat.send",
                {
                    "sessionKey": self._settings.session_key,
                    "message": user_request,
                    "idempotencyKey": run_id,
                },
                timeout_s=timeout_s,
            )

            last_text = ""
            deadline = time.time() + timeout_s
            while time.time() < deadline:
                try:
                    evt = q.get(timeout=self._settings.chat_poll_interval_s)
                except queue.Empty:
                    if self._closed.is_set():
                        raise GatewayClosedError("Gateway closed")
                    continue

                state = evt.get("state")
                if state not in ("delta", "final", "error", "aborted"):
                    continue
                if state in ("error", "aborted"):
                    msg = evt.get("errorMessage")
                    raise ChatFailedError(msg or f"Chat {state}")

                msg_obj = evt.get("message")
                cur = _extract_chat_text(msg_obj)
                if cur:
                    if cur.startswith(last_text):
                        chunk = cur[len(last_text) :]
                    else:
                        chunk = cur
                    if chunk:
                        yield chunk
                    last_text = cur
                if state == "final":
                    return

            raise ChatTimeoutError("Chat timeout")
        finally:
            with self._chat_lock:
                self._chat_queues.pop(run_id, None)

    def chat(self, user_request: str, timeout_s: float = 120.0) -> str:
        """通过拼接 stream_chat 的片段返回完整 assistant 响应。

        Args:
            user_request: 作为 chat message 发送的用户文本。
            timeout_s: 等待对话完成的最大秒数。

        Returns:
            完整的 assistant 响应文本。
        """

        parts: List[str] = []
        for chunk in self.stream_chat(user_request, timeout_s=timeout_s):
            parts.append(chunk)
        return "".join(parts)

    def _send(self, obj: Dict[str, Any]) -> None:
        """通过 WebSocket 发送一个 JSON 帧。"""

        if self._ws is None:
            raise RuntimeError("WebSocket not started")
        self._ws.send(json.dumps(obj, ensure_ascii=False))

    def _default_ws_factory(self, url: str, **kwargs: Any) -> Any:
        """创建一个 websocket-client 的 WebSocketApp 实例。"""

        try:
            import websocket  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError("Missing dependency: websocket-client") from e
        return websocket.WebSocketApp(url, **kwargs)

    def _on_open(self, _ws: Any) -> None:
        """处理 on_open 回调并调度一次兜底 connect 请求。"""

        threading.Timer(self._settings.connect_fallback_delay_s, self._send_connect).start()

    def _send_connect(self) -> None:
        """发送一次 connect 握手请求（只发送一次）。"""

        if self._connect_sent or self._ws is None:
            return
        self._connect_sent = True
        self._connect_req_id = _uuid()

        params: Dict[str, Any] = {
            "minProtocol": self._settings.protocol_version,
            "maxProtocol": self._settings.protocol_version,
            "client": {
                "id": self._settings.client_id,
                "displayName": self._settings.client_display_name,
                "version": self._settings.client_version,
                "platform": self._settings.platform,
                "mode": self._settings.client_mode,
                "instanceId": self._settings.instance_id or f"py-{_uuid()}",
            },
            "role": self._settings.role,
            "scopes": [s.strip() for s in self._settings.scopes_csv.split(",") if s.strip()],
        }

        auth: Dict[str, Any] = {}
        if self._settings.token:
            auth["token"] = self._settings.token
        if self._settings.password:
            auth["password"] = self._settings.password
        if auth:
            params["auth"] = auth

        if self._device is not None:
            device_obj: Dict[str, Any] = {
                "id": self._device.id,
                "publicKey": self._device.public_key,
                "signature": self._device.signature,
                "signedAt": self._device.signed_at,
            }
            nonce = self._device.nonce or self._connect_nonce
            if nonce:
                device_obj["nonce"] = nonce
            params["device"] = device_obj

        frame = {"type": "req", "id": self._connect_req_id, "method": "connect", "params": params}
        self._send(frame)

    def _on_message(self, _ws: Any, message: str) -> None:
        """将入站帧分发到握手、等待中的 RPC 或 chat 流队列。"""

        try:
            frame = json.loads(message)
        except Exception:
            return
        if not isinstance(frame, dict):
            return

        t = frame.get("type")
        if t == "event":
            self._handle_event_frame(frame)
            return
        if t == "res":
            self._handle_res_frame(frame)
            return

    def _handle_event_frame(self, frame: Dict[str, Any]) -> None:
        """处理来自网关的 event 帧。"""

        event = frame.get("event")
        if event == "connect.challenge":
            payload = frame.get("payload") or {}
            nonce = payload.get("nonce") if isinstance(payload, dict) else None
            self._connect_nonce = nonce if isinstance(nonce, str) else None
            self._send_connect()
            return

        if event == "chat":
            payload = frame.get("payload")
            if not isinstance(payload, dict):
                return
            run_id = payload.get("runId")
            if not isinstance(run_id, str):
                return
            with self._chat_lock:
                q = self._chat_queues.get(run_id)
            if q is not None:
                q.put(payload)
            return

    def _handle_res_frame(self, frame: Dict[str, Any]) -> None:
        """处理 response 帧并唤醒对应的等待者。"""

        req_id = frame.get("id")
        if isinstance(req_id, str):
            with self._pending_lock:
                q = self._pending.get(req_id)
            if q is not None:
                q.put(frame)

        payload = frame.get("payload")
        if isinstance(payload, dict) and payload.get("type") == "hello-ok":
            _logger.debug("收到 hello-ok，握手完成。")
            self._hello_payload = payload
            self._hello_ok.set()
            return

        if req_id and req_id == self._connect_req_id and frame.get("ok") is False:
            err = frame.get("error") or {}
            msg = err.get("message") if isinstance(err, dict) else None
            self._last_error = ProtocolError(msg or "Connect failed")
            return

    def _on_error(self, _ws: Any, error: Any) -> None:
        """记录 WebSocket 错误，供 start() 与 request() 的等待逻辑使用。"""

        self._last_error = error if isinstance(error, BaseException) else RuntimeError(str(error))

    def _on_close(self, _ws: Any, close_status_code: Any, close_msg: Any) -> None:
        """在 WebSocket 关闭时标记适配器已关闭。"""

        self._closed.set()
