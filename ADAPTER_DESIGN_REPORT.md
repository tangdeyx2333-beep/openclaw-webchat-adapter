# OpenClaw Gateway Python 适配器（结构化版）设计文档

### 让你的项目更加简单的嵌入openclaw

## 修改摘要
- 将原先单文件的 WebSocket 适配器拆分为可复用的包：配置加载、.env 解析、协议适配、异常定义、CLI 入口分离。
- 新增统一配置入口 `AdapterSettings.from_env()`：从 `.env` 或系统环境变量读取 `token/password` 用于网关鉴权。
- 对外提供核心流式接口 `OpenClawGatewayWsAdapter.stream_chat(user_request)`：按 runId 订阅 chat 事件并增量输出。
- 增加可注入 `ws_factory` 以便单元测试模拟网关收发，降低耦合。

## 代码结构与职责划分
- `openclaw_gateway_adapter/env.py`
  - 负责解析/加载 `.env`，不引入第三方 dotenv 依赖。
- `openclaw_gateway_adapter/config.py`
  - 定义 `AdapterSettings`，统一读取并校验环境变量（含鉴权字段存在性校验）。
- `openclaw_gateway_adapter/exceptions.py`
  - 定义适配器对外抛出的异常类型，便于上层调用方精确捕获与处理。
- `openclaw_gateway_adapter/ws_adapter.py`
  - 协议适配核心：握手（connect.challenge -> connect -> hello-ok）、RPC request/response pending 映射、chat 事件路由与增量拼接输出。
- `openclaw_gateway_adapter/__main__.py`
  - 提供最小 CLI：用于快速验证连通性与流式输出效果。

## 关键设计点
### 1) 配置与鉴权
- 配置读取策略：
  - 优先从 `.env` 加载（若存在），再从 `os.environ` 获取最终值。
  - 默认不覆盖既有 `os.environ`（可通过 `dotenv_override=True` 允许覆盖）。
- 鉴权策略：
  - 强制要求至少配置 `OPENCLAW_GATEWAY_TOKEN` 或 `OPENCLAW_GATEWAY_PASSWORD` 其一。
  - 适配器在 `connect` 请求中仅在配置存在时才发送 `auth.token/auth.password` 字段，避免发送空字段。

### 2) 协议适配与流式输出
- 握手：
  - WebSocket 建连后可能先收到 `connect.challenge`，也可能不保证顺序；适配器同时提供事件触发和定时兜底，确保 connect 能发送。
  - 收到 `res.payload.type == "hello-ok"` 视为握手成功。
- RPC：
  - `req.id` 为一次请求的唯一标识；适配器用 `pending` 映射将 `res.id` 回投到对应等待队列。
- chat 流：
  - `chat.send` 使用 `idempotencyKey` 作为 `runId`（一次请求一次 run）。
  - 服务端 `event=chat` 按 `payload.runId` 路由到对应队列。
  - 对 `delta/final` 采用“前缀差分”输出新增文本，避免重复输出累计内容。

### 3) 可测试性与解耦
- `ws_factory` 注入点：
  - 默认使用 `websocket-client` 的 `WebSocketApp`。
  - 测试中用 FakeWebSocketApp 模拟握手、RPC、chat 事件，避免依赖真实网关。

## 环境变量配置指南
请复制 `.env.example` 为 `.env` 并填写。每个变量的含义与影响已在 `.env.example` 中以注释块完整说明：
- 网关连接：
  - `OPENCLAW_GATEWAY_URL`
- 鉴权（二选一或同时提供）：
  - `OPENCLAW_GATEWAY_TOKEN`
  - `OPENCLAW_GATEWAY_PASSWORD`
- 会话：
  - `OPENCLAW_SESSION_KEY`
- 可选握手参数：
  - `OPENCLAW_PROTOCOL_VERSION`
  - `OPENCLAW_CLIENT_ID`
  - `OPENCLAW_CLIENT_MODE`
  - `OPENCLAW_CLIENT_DISPLAY_NAME`
  - `OPENCLAW_CLIENT_VERSION`
  - `OPENCLAW_CLIENT_PLATFORM`
  - `OPENCLAW_CLIENT_INSTANCE_ID`
  - `OPENCLAW_CONNECT_ROLE`
  - `OPENCLAW_CONNECT_SCOPES`

## 使用方式
### 依赖安装（必须）
```bash
pip install -r requirements.txt
```

### 方式 A：代码调用（推荐集成）
```python
from openclaw_gateway_adapter import AdapterSettings, OpenClawGatewayWsAdapter

settings = AdapterSettings.from_env(dotenv_path=".env")
adapter = OpenClawGatewayWsAdapter(settings=settings)

adapter.start()
adapter.ensure_session("main")

for chunk in adapter.stream_chat("你好"):
    print(chunk, end="", flush=True)

adapter.stop()
```

### 方式 B：命令行快速验证
```bash
python -m openclaw_gateway_adapter --once "你好"
```

## 安全性说明
- 本实现不打印/不记录 token/password；上层如需日志，建议对敏感字段脱敏后再输出。
- `stream_chat` 对输入做类型与空字符串校验，避免异常协议请求。

