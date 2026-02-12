# OpenClaw WebChat 适配器 API 文档

## 概述
本文档提供了 OpenClaw WebChat 适配器的 API 说明，该适配器通过 WebSocket 连接与 OpenClaw 网关进行通信。

## 核心 API (推荐使用)

### 类: OpenClawWebChatAPI
`OpenClawWebChatAPI` 位于 `openclaw_webchat_adapter.api` 包中，是对底层适配器的更高层封装，提供了更简洁的初始化和调用方式。

#### 方法: create_connected_from_env
从环境变量或 `.env` 文件加载配置并自动建立连接。

##### 方法签名
```python
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
```

##### 参数
- **token** (`Optional[str]`, 可选): 显式传入的网关鉴权 token。若为 None 则从环境变量加载。
- **password** (`Optional[str]`, 可选): 显式传入的网关鉴权密码。若为 None 则从环境变量加载。
- **url** (`Optional[str]`, 可选): 显式传入的网关 WebSocket URL。若为 None 则从环境变量加载。
- **dotenv_path** (`str`, 可选): `.env` 文件路径。默认值为 ".env"。
- **dotenv_override** (`bool`, 可选): 是否用 `.env` 中的值覆盖系统环境变量。默认值为 False。
- **ensure_session_key** (`str`, 可选): 启动后自动确保并激活的会话 Key。默认值为 "main"。
- **timeout_s** (`float`, 可选): 连接和握手的超时时间（秒）。默认值为 12.0。
- **device** (`Optional[DeviceIdentityPlaceholder]`, 可选): 可选的设备身份信息。

##### 返回值
- **OpenClawWebChatAPI**: 已连接并就绪的 API 实例。

##### 使用示例
```python
from openclaw_webchat_adapter.api import OpenClawWebChatAPI

# 自动从 .env 加载配置并连接
api = OpenClawWebChatAPI.create_connected_from_env()

# 使用 API
for chunk in api.stream_chat("你好"):
    print(chunk, end="")

# 关闭连接
api.close()
```

#### 方法: get_chat_history
获取指定会话的历史聊天数据。

##### 使用示例
```python
history = api.get_chat_history(session_key="my-session", limit=50)
```

#### 方法: stream_chat
为给定的用户请求逐步流式传输助手响应。

##### 使用示例
```python
for fragment in api.stream_chat("你好"):
    print(fragment, end="")
```

#### 方法: get_chat_history_simple
获取指定会话的历史聊天数据，返回仅包含角色和内容的简化消息对象。

##### 使用示例
```python
simple_history = api.get_chat_history_simple(session_key="my-session")
```

#### 方法: stop
停止并关闭底层的 WebSocket 连接。

##### 使用示例
```python
api.stop()
```

---

## 底层适配器 (高级用法)

### 类: OpenClawChatWsAdapter
位于 `openclaw_webchat_adapter.ws_adapter` 中，提供对 WebSocket 协议的直接控制。

### 方法: get_chat_history

#### 描述
获取指定会话的历史聊天数据。返回具有严格字段验证的结构化响应对象。

#### 方法签名
```python
def get_chat_history(
    self,
    session_key: str = None, 
    limit: int = 200,
    timeout_s: float = 15.0,
) -> ChatHistory:
```

#### 参数
- **session_key** (`Optional[str]`, 必须): 会话标识符。如果未提供，则使用配置的会话密钥。必须是非空字符串或 None。
- **limit** (`int`, 可选): 要检索的消息最大数量。必须是正整数。默认值为 200。
- **timeout_s** (`float`, 可选): 请求超时时间（秒）。默认值为 15.0。

#### 返回值
- **ChatHistory**: 包含以下内容的结构化对象：
  - `session_key` (`str`): 会话标识符
  - `session_id` (`str`): 会话 ID
  - `messages` (`List[ChatMessage]`): 聊天消息列表，包含：
    - `role` (`str`): 消息角色 ('user', 'assistant' 等)
    - `content` (`List[ChatContentItem]`): 内容项目列表，包含：
      - `type` (`str`): 内容类型 (如 'text')
      - `text` (`str`): 内容文本
    - `timestamp` (`int`): Unix 时间戳
    - `api` (`Optional[str]`): 使用的 API (可选)
    - `provider` (`Optional[str]`): 使用的提供商 (可选)
    - `model` (`Optional[str]`): 使用的模型 (可选)
    - `usage` (`Optional[ChatUsage]`): 使用统计 (可选)
    - `stop_reason` (`Optional[str]`): 停止原因 (可选)
  - `thinking_level` (`Optional[str]`): 思考级别设置 (可选)

#### 异常
- **ValueError**: 如果提供了无效参数（例如，无效的 session_key 或非正数 limit）
- **RequestTimeoutError**: 如果请求超时
- **RequestFailedError**: 如果网关返回错误响应
- **RuntimeError**: 如果连接未建立

#### 使用示例
```python
from openclaw_webchat_adapter.ws_adapter import OpenClawChatWsAdapter

# 假设适配器已连接
history = adapter.get_chat_history(session_key="my-session", limit=50)
for message in history.messages:
    print(f"{message.role}: {message.content[0].text}")
```

---

### 方法: stream_chat

#### 描述
为给定的用户请求逐步流式传输助手响应。在可用时产生文本片段。

#### 方法签名
```python
def stream_chat(self, user_request: str, timeout_s: float = 120.0) -> Iterator[str]:
```

#### 参数
- **user_request** (`str`): 作为聊天消息发送的用户输入文本。必须是非空字符串。
- **timeout_s** (`float`, 可选): 等待聊天完成的最大时间（秒）。默认值为 120.0。

#### 产出
- **str**: 来自助手响应的增量文本片段。

#### 异常
- **GatewayClosedError**: 流式传输期间网关连接关闭时
- **ChatTimeoutError**: 聊天在超时时间内未完成时
- **ChatFailedError**: 聊天以错误或中止状态结束时

#### 使用示例
```python
from openclaw_webchat_adapter.ws_adapter import OpenClawChatWsAdapter

# 假设适配器已连接
response_parts = []
for fragment in adapter.stream_chat("你好，你好吗？", timeout_s=60.0):
    response_parts.append(fragment)
    print(fragment, end='', flush=True)  # 在片段到达时打印

full_response = ''.join(response_parts)
print(f"\n完整响应: {full_response}")
```

#### 注意事项
- 该方法处理增量文本传递，允许实时显示响应
- 片段一旦从网关接收就会产生
- 该方法自动管理内部队列和超时
- 如果 user_request 为空或不是字符串，该方法返回空迭代器

---

## 其他方法

### 方法: get_chat_history_simple

#### 描述
获取指定会话的历史聊天数据，返回仅包含角色和内容的简化消息对象。

#### 方法签名
```python
def get_chat_history_simple(
    self,
    session_key: Optional[str] = None,
) -> List[ChatMessage_Simple]:
```

#### 参数
- **session_key** (`Optional[str]`, 可选): 会话标识符。如果未提供，则使用配置的会话密钥。

#### 返回值
- **List[ChatMessage_Simple]**: 简化聊天消息对象列表，包含：
  - `role` (`str`): 消息角色 ('user', 'assistant' 等)
  - `content` (`List[ChatContentItem]`): 内容项目列表，包含：
    - `type` (`str`): 内容类型 (如 'text')
    - `text` (`str`): 内容文本

#### 使用示例
```python
from openclaw_webchat_adapter.ws_adapter import OpenClawChatWsAdapter

# 假设适配器已连接
simple_messages = adapter.get_chat_history_simple(session_key="my-session")
for msg in simple_messages:
    print(f"{msg.role}: {msg.content[0].text}")
```

## 错误处理

适配器包含各种场景的全面错误处理：

- **连接问题**: `GatewayClosedError` - 连接丢失时
- **超时**: `RequestTimeoutError` 和 `ChatTimeoutError` - 超时场景
- **请求失败**: `RequestFailedError` - 网关错误
- **验证错误**: `ValueError` - 无效输入
- **一般错误**: `RuntimeError` 和 `ChatFailedError` - 其他故障情况