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

