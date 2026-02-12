# OpenClaw Gateway Python 适配器（WebChat 协议）

让你的项目更加简单的嵌入openclaw

这是一个可复用的 Python 包：基于 OpenClaw Gateway 的 WebSocket 协议完成握手与 RPC 调用，并提供开箱即用的流式聊天接口（chat.send + event=chat）。

## 0.0.4 更新
1. 新增了获取历史聊天记录接口，get_chat_history,get_chat_history_simple 
2. 将接口封装到了api.cilent.OpenClawWebChatAPI中 

## 如何工作（简版）

```text
调用接口（你的 Python 代码 / CLI）
    │
    ▼
伪造的 WebChat 终端（本适配器模拟的 Web 客户端）
    │  ws://127.0.0.1:18789（WebChat 协议：connect / sessions.patch / chat.send）
    ▼
OpenClaw Gateway
```

## 特性
- 一键连接：`OpenClawGatewayWsAdapter.create_connected()` 自动握手并准备会话
- 配置统一：`AdapterSettings.from_env()` 从 `.env` / 环境变量读取参数
- 流式输出：`stream_chat()` 增量产出 assistant 文本片段
- CLI 入口：支持一次性请求与交互式 REPL，并输出连接就绪日志
- 可测试：可注入 `ws_factory`，便于在单元测试中模拟网关收发

## 快速开始

### 1) 安装依赖
```bash
pip install openclaw-webchat-adapter 
```

### 2) 配置环境变量
复制 `.env.example` 为 `.env` 并按注释块填写（每个变量的含义与影响以 `.env.example` 为准）。

最少需要：
- `OPENCLAW_GATEWAY_URL`
- `OPENCLAW_SESSION_KEY`

鉴权（按你的网关策略选择其一或同时提供）：
- `OPENCLAW_GATEWAY_TOKEN`
- `OPENCLAW_GATEWAY_PASSWORD`

### 3) 使用示例（推荐：代码调用）

```python
"""为 OpenClaw Gateway 适配器提供一个最小可用的命令行入口。"""

from openclaw_webchat_adapter.ws_adapter import OpenClawChatWsAdapter as adapter

def main() -> int:
    """基于 .env 配置启动交互式 REPL 或执行一次性请求。"""
    connect = adapter.create_connected_from_env()
    # 进入交互式 REPL
    try:
        while True:
            line = input("> ").strip()
            if not line:
                continue
            if line.lower() in ("/exit", "/quit"):
                break
            for chunk in connect.stream_chat(line):
                print(chunk, end="", flush=True)
            print("")
    finally:
        connect.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


```

退出交互式聊天：
- 输入 `/exit` 或 `/quit`

## 安全建议
- 不要在日志中输出 `token/password` 等敏感信息（本适配器不会主动打印这些字段）。
- 如需远程访问网关，建议通过安全通道（例如内网/VPN/反向代理）并启用鉴权。

## 文档
- 结构化设计文档：[ADAPTER_DESIGN_REPORT.md](file:///f:/aaa_desktop_file/python-study/openclaw_webchat_adapter/ADAPTER_DESIGN_REPORT.md)
- 本仓库设计变更说明：[DESIGN_REPORT.md](file:///f:/aaa_desktop_file/python-study/openclaw_webchat_adapter/DESIGN_REPORT.md)
- 本仓库测试报告：[TEST_REPORT.md](file:///f:/aaa_desktop_file/python-study/openclaw_webchat_adapter/TEST_REPORT.md)
- 协议与握手细节参考：[README_3.md](file:///f:/aaa_desktop_file/python-study/openclaw_webchat_adapter/README_3.md)
