# 🛡️ SECURITY AUDIT REPORT (代码安全审计报告)

## 1. 审计概览 (Executive Summary)
* **审计对象**: `openclaw-webchat-adapter` Python Project
* **整体安全评分**: 45/100
* **威胁等级**: 🔴 极高
* **一句话结论**: 该项目存在多个严重漏洞，包括敏感数据明文传输、身份认证薄弱和拒绝服务风险，绝对不能用于生产环境。

## 2. 漏洞矩阵 (Vulnerability Matrix)
| ID | 漏洞类型 (CWE) | 严重程度 | 位置 (行号) | 简述 |
|----|---------------|---------|------------|------|
| V1 | CWE-319: Cleartext Transmission of Sensitive Information | 🔴 Critical | `config.py:100` | 默认使用未加密的 `ws://` 协议，导致凭证泄露。 |
| V2 | CWE-287: Improper Authentication | 🟠 High | `ws_adapter.py:441` | `ensure_session` 缺少会话授权，可被任意认证用户篡改。 |
| V3 | CWE-835: Loop with Unreachable Exit Condition ('Infinite Loop') | 🟠 High | `ws_adapter.py:303` | `_pending` 和 `_chat_queues` 字典无大小限制，可被恶意请求撑爆内存，导致拒绝服务。 |
| V4 | CWE-20: Improper Input Validation | 🟡 Medium | `ws_adapter.py:511` | `_map_chat_history_payload` 未充分验证载荷结构，可被恶意JSON攻击。 |
| V5 | CWE-259: Use of Hard-coded Password | 🟡 Medium | `config.py:103` | 默认 `session_key` (`agent:main:main`) 高度可预测，加剧了V2的风险。 |

## 3. 深度分析与漏洞复现 (Detailed Analysis)

### [V1] 🔴 Critical: Cleartext Transmission of Sensitive Information
* **原理分析**: `AdapterSettings` 类中的 `url` 字段默认值为 `"ws://127.0.0.1:18789"`。`ws://` 是一个未加密的协议。当适配器连接到任何非本地的网关时，所有流量，包括 `token` 或 `password`，都将以明文形式在网络上传输。
* **攻击向量**: 任何能够嗅探客户端与网关之间网络流量的攻击者，都可以直接捕获到鉴权凭证。
* **致命后果**: 攻击者可以窃取 `token` 或 `password`，完全冒充用户身份，访问和控制其所有数据与功能。
* **代码证据**:
    ```python
    # ❌ Vulnerable in config.py:100
    @dataclass(frozen=True)
    class AdapterSettings:
        url: str = "ws://127.0.0.1:18789"
        token: Optional[str] = None
        password: Optional[str] = None
        # ...
    ```

### [V2] 🟠 High: Improper Authentication
* **原理分析**: `ensure_session` 方法通过 `sessions.patch` RPC 调用来激活一个会话。此操作仅依赖于一个字符串 `key`。任何已经通过初始连接认证的客户端，都可以调用此方法并传入一个可预测的 `key`（如默认的 "main"），从而控制或干扰其他用户的会话。
* **攻击向量**: 攻击者使用自己的有效 `token` 连接网关，然后调用 `ensure_session(key="agent:main:main")`。如果其他用户也正在使用这个默认 `session_key`，攻击者可能会影响该会话的状态。
* **致命后果**: 破坏其他用户的会话状态，可能导致数据错乱或服务中断。
* **代码证据**:
    ```python
    # ❌ Vulnerable in ws_adapter.py:441
    def ensure_session(self, key: str = "main", timeout_s: float = 15.0) -> Dict[str, Any]:
        # ...
        return self.request("sessions.patch", {"key": key, "sendPolicy": "allow"}, timeout_s=timeout_s)
    ```

### [V3] 🟠 High: Loop with Unreachable Exit Condition ('Infinite Loop') / Resource Exhaustion
* **原理分析**: 在 `ws_adapter.py` 中，`_pending` 和 `_chat_queues` 两个字典用于跟踪活动的请求和聊天流。它们都没有任何形式的大小限制。
* **攻击向量**: 一个恶意的认证客户端可以发送大量 `request` 调用但从不读取响应，或者发送大量 `chat.send` 请求。这将导致 `_pending` 或 `_chat_queues` 字典无限增长，最终耗尽服务器的所有可用内存。
* **致命后果**: 导致服务端应用程序崩溃，造成拒绝服务 (DoS)，所有用户将无法使用。
* **代码证据**:
    ```python
    # ❌ Vulnerable in ws_adapter.py:303, 306
    self._pending: Dict[str, "queue.Queue[Dict[str, Any]]"] = {}
    # ...
    self._chat_queues: Dict[str, "queue.Queue[Dict[str, Any]]"] = {}
    ```

## 4. 修复方案 (Remediation)

### Fix for [V1]:
* **修复策略**: 强制使用加密的 `wss://` 协议，并验证 TLS 证书。
* **安全代码**:
    ```python
    # ✅ Secure in config.py:100
    @dataclass(frozen=True)
    class AdapterSettings:
        url: str = "wss://your-gateway-domain.com" # <-- MUST default to wss://
        # ...
    
    # Additionally, when creating the websocket, ensure TLS verification is enabled.
    # The 'websockets' library does this by default, but if using another library,
    # ensure 'sslopt={"cert_reqs": ssl.CERT_REQUIRED}' or equivalent is set.
    ```

### Fix for [V2] & [V5]:
* **修复策略**: 废除可预测的 `session_key`。应在成功连接后，由服务器生成一个唯一的、不可预测的会话ID并返回给客户端。客户端后续所有操作都必须使用此ID。
* **安全代码**:
    ```python
    # ✅ Secure (Conceptual change)
    # 1. Server-side: After a successful 'connect', the 'hello-ok' response MUST contain a unique `sessionId`.
    # { "type": "hello-ok", "payload": { ..., "sessionId": "unique-unguessable-session-id-123" } }
    
    # 2. Client-side: Store this sessionId and use it for all subsequent requests.
    class OpenClawChatWsAdapter:
        def __init__(...):
            self._session_id = None # Store the server-provided session ID
        
        def start(...):
            # ... after hello-ok
            self._session_id = self._hello_payload.get("sessionId")
            if not self._session_id:
                raise ProtocolError("Server did not provide a sessionId")

        def stream_chat(...):
            # Use the server-provided session ID, not a client-generated key
            self.request("chat.send", {"sessionId": self._session_id, ...})
    ```

### Fix for [V3]:
* **修复策略**: 为 `_pending` 和 `_chat_queues` 字典设置一个合理的大小上限，并在达到上限时拒绝新的请求。
* **安全代码**:
    ```python
    # ✅ Secure in ws_adapter.py
    class OpenClawChatWsAdapter:
        def __init__(...):
            # ...
            self._max_pending_requests = 100 # Set a reasonable limit
            self._max_chat_streams = 50

        def request(...):
            # ...
            with self._pending_lock:
                if len(self._pending) >= self._max_pending_requests:
                    raise RequestFailedError("Too many concurrent requests")
                self._pending[req_id] = q
            # ...

        def stream_chat(...):
            # ...
            with self._chat_lock:
                if len(self._chat_queues) >= self._max_chat_streams:
                    raise ChatFailedError("Too many concurrent chat streams")
                self._chat_queues[run_id] = q
            # ...
    ```

## 5. 潜在风险与架构建议 (Subtle Risks)
* **日志记录风险**: `_logger.warning` 记录了 `connId`。虽然 `connId` 本身可能不敏感，但必须确保日志中绝不会记录 `token`、`password` 或聊天内容。建议对所有日志输出进行审查。
* **依赖安全**: 项目依赖于 `websocket-client`。必须定期扫描此依赖及其子依赖是否存在已知的 CVE。
* **异常处理**: 当前的异常处理向客户端返回了较为详细的错误信息（例如 "Request timeout: {method}"）。在生产环境中，应使用通用的错误消息，并将详细信息记录在服务器端日志中，以避免泄露内部逻辑。
