"""为 OpenClaw Gateway 适配器提供一个最小可用的命令行入口。"""

from __future__ import annotations

import argparse
import os
import sys

if __package__ in (None, ""):
    _pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _pkg_root not in sys.path:
        sys.path.insert(0, _pkg_root)
    from openclaw_gateway_adapter.config import AdapterSettings
    from openclaw_gateway_adapter.ws_adapter import OpenClawGatewayWsAdapter
else:
    from .config import AdapterSettings
    from .ws_adapter import OpenClawGatewayWsAdapter


def _parse_args() -> argparse.Namespace:
    """解析适配器 CLI 的命令行参数。"""

    p = argparse.ArgumentParser()
    p.add_argument("--dotenv", default=".env")
    p.add_argument("--once", default=None)
    p.add_argument("--session-key", default=None)
    return p.parse_args()


def main() -> int:
    """基于 .env 配置启动交互式 REPL 或执行一次性请求。"""

    args = _parse_args()
    settings = AdapterSettings.from_env(dotenv_path=args.dotenv)
    if args.session_key:
        settings = AdapterSettings(**{**settings.__dict__, "session_key": args.session_key})

    try:
        adapter = OpenClawGatewayWsAdapter(settings=settings)
        adapter.start()
        adapter.ensure_session("main")
    except RuntimeError as e:
        msg = str(e)
        if "websocket-client" in msg or "No module named 'websocket'" in msg:
            sys.stderr.write(
                "缺少依赖：websocket-client\n"
                "请执行：pip install -r requirements.txt\n"
            )
            return 2
        raise

    if args.once:
        sys.stdout.write(adapter.chat(args.once) + "\n")
        adapter.stop()
        return 0

    try:
        while True:
            line = input("> ").strip()
            if not line:
                continue
            if line.lower() in ("/exit", "/quit"):
                break
            for chunk in adapter.stream_chat(line):
                print(chunk, end="", flush=True)
            print("")
    finally:
        adapter.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

