"""为 OpenClaw Gateway 适配器提供一个最小可用的命令行入口。"""

from openclaw_webchat_adapter.ws_adapter import OpenClawChatWsAdapter as adapter
from openclaw_webchat_adapter.api.client import OpenClawWebChatAPI as client
def main() -> int:
    """基于 .env 配置启动交互式 REPL 或执行一次性请求。"""
    connect1 = client.create_connected_from_env()
    connect = adapter.create_connected_from_env()
    try:
        # while True:
        #     line = input("> ").strip()
        #     if not line:
        #         continue
        #     if line.lower() in ("/exit", "/quit"):
        #         break
        #     for chunk in connect.stream_chat(line):
        #         print(chunk, end="", flush=True)
        #     print("")
        r1 = connect.get_chat_history("agent:main:main")
        print(r1)
        print("---"*10)
        r1 = connect.get_chat_history_simple("agent:main:main")
        print(r1)
    finally:
        connect.stop()
    # 进入交互式 REPL
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

