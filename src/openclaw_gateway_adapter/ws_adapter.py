"""实现 OpenClaw Gateway 协议的 WebSocket 适配器。"""

from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from dataclasses import dataclass
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


WsFactory = Callable[..., Any]


class OpenClawGatewayWsAdapter:
    """通过 WebSocket 连接 OpenClaw Gateway，并提供流式聊天 API。"""

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
            print("Hello Developer!")
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

