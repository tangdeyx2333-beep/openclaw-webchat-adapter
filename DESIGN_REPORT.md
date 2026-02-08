# OpenClaw Gateway Adapter 设计文档（本次变更）

## 修改摘要
- 修复 `OpenClawGatewayWsAdapter.create_connected()` 的类方法绑定，并新增 `create_connected_from_env()`：支持无参从 `.env`/环境变量读取并连接，也支持显式覆盖 `OPENCLAW_GATEWAY_URL/token/password`。
- 将 `openclaw_webchat_adapter` 包内的模块/类/函数 Docstring 统一翻译为中文，提升可读性与团队协作效率（不改变任何运行逻辑）。
- 新增 `env.py` 的解析与加载单元测试，覆盖引号处理、注释/空行跳过、override 行为等核心路径。
- 将 CLI 的“连接/握手/会话准备”逻辑迁移到 `ws_adapter.create_connected()`，CLI 仅负责读取输入并调用聊天接口。
- 适配器在“连接就绪/会话就绪”时输出 INFO 日志，便于启动排障与联调。
- 新增 `TEST_REPORT.md` 作为本次交付的测试报告。

## 架构设计思路
该适配器以“配置加载 + 协议适配 + 异常分层”的方式拆分职责，降低耦合并便于测试：
- `openclaw_webchat_adapter/env.py`
  - 负责 `.env` 文本解析与写入 `os.environ`，不引入第三方依赖。
- `openclaw_webchat_adapter/config.py`
  - 负责从环境变量/`.env` 读取配置并做基本合法性校验，最终构造 `AdapterSettings`。
- `openclaw_webchat_adapter/ws_adapter.py`
  - 负责 WebSocket 连接、握手、RPC request/response 的 pending 映射、chat 事件路由与增量输出；并提供 `create_connected()` 封装一键启动流程。
- `openclaw_webchat_adapter/exceptions.py`
  - 对外暴露类型化异常，便于上层做精确捕获与处理分支。
- `openclaw_webchat_adapter/__main__.py`
  - 提供最小 CLI 入口，方便验证连通性与进行一次性请求；连接与会话准备由 `ws_adapter.create_connected()` 承担。

## 环境变量详细配置指南
建议复制 `.env.example` 为 `.env`，并按注释块填写。代码侧读取入口为 `AdapterSettings.from_env()`，主要变量如下：

### 必填（代码会校验非空）
- `OPENCLAW_GATEWAY_URL`
  - 网关 WebSocket 地址，例如：`ws://127.0.0.1:18789`
- `OPENCLAW_SESSION_KEY`
  - chat 请求使用的会话 key，例如：`agent:main:main`

### 选填（是否必需由网关端策略决定）
- `OPENCLAW_GATEWAY_TOKEN`
  - token 鉴权凭据（若提供则在 connect 时携带）。
- `OPENCLAW_GATEWAY_PASSWORD`
  - password 鉴权凭据（若提供则在 connect 时携带）。

### 选填（握手与客户端信息）
- `OPENCLAW_PROTOCOL_VERSION`
- `OPENCLAW_CLIENT_ID`
- `OPENCLAW_CLIENT_MODE`
- `OPENCLAW_CLIENT_DISPLAY_NAME`
- `OPENCLAW_CLIENT_VERSION`
- `OPENCLAW_CLIENT_PLATFORM`
- `OPENCLAW_CLIENT_INSTANCE_ID`
- `OPENCLAW_CONNECT_ROLE`
- `OPENCLAW_CONNECT_SCOPES`

说明：
- 变量的 `[必须/可选]`、`[配置效果]`、`[格式/默认值]` 以 `.env.example` 为准；该文件是配置说明的单一可信来源。
- `.env` 加载策略：默认不覆盖已存在的 `os.environ` 同名值；如需覆盖可在代码调用 `dotenv_override=True`。

## 安全性说明
- 适配器不输出 `token/password` 等敏感字段；上层若需要日志，请自行脱敏后再记录。
- `.env` 解析逻辑仅处理 `KEY=VALUE` 形式，并会忽略注释/空行/非法行，降低误解析风险。
