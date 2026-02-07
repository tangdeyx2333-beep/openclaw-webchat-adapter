# OpenClaw Gateway Python 适配器

让你的项目更加简单的嵌入openclaw

该适配器提供一个可复用的 Python 包，基于webchat协议，通过 WebSocket 连接 OpenClaw Gateway，完成握手、发送 RPC、并以流式方式接收 chat 事件输出。

## 特性
- 统一配置入口：从 `.env` / 环境变量加载配置（`AdapterSettings.from_env()`）
- 流式聊天：`stream_chat()` 按增量输出 assistant 文本
- 最小 CLI：支持一次性请求或交互式 REPL
- 可测试性：支持注入 `ws_factory`，便于模拟网关收发

## 快速开始

### 1) 安装依赖
```bash
pip install -r requirements.txt
```

### 2) 配置环境变量
复制 `.env.example` 为 `.env` 并填写必要配置（变量说明以 `.env.example` 的注释块为准）。

### 3) 使用示例（代码调用）
```python
from openclaw_gateway_adapter import AdapterSettings, OpenClawGatewayWsAdapter

settings = AdapterSettings.from_env(dotenv_path=".env")
adapter = OpenClawGatewayWsAdapter(settings=settings)

adapter.start()
adapter.ensure_session("main")

for chunk in adapter.stream_chat("你好"):
    print(chunk, end="", flush=True)
print("")

adapter.stop()
```

### 4) 使用示例（命令行）
一次性请求：
```bash
python -m openclaw_gateway_adapter --once "你好"
```

交互式聊天：
```bash
python -m openclaw_gateway_adapter
```

## 文档
- 结构化设计文档：[ADAPTER_DESIGN_REPORT.md](file:///f:/aaa_desktop_file/python-study/openclaw_webchat_adapter/ADAPTER_DESIGN_REPORT.md)
- 本次变更设计说明：[DESIGN_REPORT.md](file:///f:/aaa_desktop_file/python-study/openclaw_webchat_adapter/DESIGN_REPORT.md)
- 本次测试报告：[TEST_REPORT.md](file:///f:/aaa_desktop_file/python-study/openclaw_webchat_adapter/TEST_REPORT.md)
- 协议与握手细节参考：[README_3.md](file:///f:/aaa_desktop_file/python-study/openclaw_webchat_adapter/README_3.md)

