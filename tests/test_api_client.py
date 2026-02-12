"""测试 api 包中的 OpenClawWebChatAPI 功能。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any, Callable, Dict, Optional
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from openclaw_webchat_adapter.api import OpenClawWebChatAPI
from openclaw_webchat_adapter.ws_adapter import OpenClawChatWsAdapter

class _FakeWebSocketApp:
    def __init__(
        self,
        url: str,
        on_open: Optional[Callable[..., Any]] = None,
        on_message: Optional[Callable[..., Any]] = None,
        on_error: Optional[Callable[..., Any]] = None,
        on_close: Optional[Callable[..., Any]] = None,
    ):
        self.url = url
        self._on_open = on_open
        self._on_message = on_message
        self._on_error = on_error
        self._on_close = on_close
        self._closed = threading.Event()

    def run_forever(self) -> None:
        if self._on_open is not None:
            self._on_open(self)
        if self._on_message is not None:
            hello = {
                "type": "res",
                "id": "hello-req-id",
                "ok": True,
                "payload": {"type": "hello-ok", "protocol": 3, "server": {"connId": "fake-conn"}},
            }
            self._on_message(self, json.dumps(hello, ensure_ascii=False))
        while not self._closed.is_set():
            time.sleep(0.01)

    def send(self, message: str) -> None:
        frame = json.loads(message)
        req_id = frame.get("id")
        method = frame.get("method")
        if not isinstance(req_id, str) or self._on_message is None:
            return

        if method == "sessions.patch":
            res = {"type": "res", "id": req_id, "ok": True, "payload": {}}
            self._on_message(self, json.dumps(res, ensure_ascii=False))
        elif method == "chat.send":
            res = {"type": "res", "id": req_id, "ok": True, "payload": {}}
            self._on_message(self, json.dumps(res, ensure_ascii=False))
            params = frame.get("params") or {}
            run_id = params.get("idempotencyKey")
            if isinstance(run_id, str):
                evt = {
                    "type": "event",
                    "event": "chat",
                    "payload": {
                        "runId": run_id,
                        "state": "final",
                        "message": {"content": [{"type": "text", "text": "test response"}]},
                    },
                }
                self._on_message(self, json.dumps(evt, ensure_ascii=False))
        elif method == "chat.history":
            res = {
                "type": "res",
                "id": req_id,
                "ok": True,
                "payload": {
                    "sessionKey": "test",
                    "sessionId": "test-id",
                    "messages": [
                        {
                            "role": "user",
                            "timestamp": int(time.time()),
                            "content": [{"type": "text", "text": "hello"}]
                        }
                    ]
                }
            }
            self._on_message(self, json.dumps(res, ensure_ascii=False))

    def close(self) -> None:
        self._closed.set()
        if self._on_close is not None:
            self._on_close(self, None, None)

def _fake_ws_factory(url: str, **kwargs: Any) -> _FakeWebSocketApp:
    return _FakeWebSocketApp(url, **kwargs)

class TestWebChatAPI(unittest.TestCase):
    def test_api_create_from_env(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / ".env"
            dotenv_path.write_text(
                "OPENCLAW_GATEWAY_URL=ws://test\nOPENCLAW_SESSION_KEY=test\n",
                encoding="utf-8"
            )
            
            # 由于 OpenClawWebChatAPI.create_connected_from_env 内部调用了 OpenClawChatWsAdapter.create_connected_from_env
            # 我们需要 mock 掉底层适配器的工厂，以便使用 fake ws
            with patch("openclaw_webchat_adapter.ws_adapter.OpenClawChatWsAdapter.create_connected_from_env") as mock_create:
                # 模拟一个已经用 fake ws 初始化的适配器
                from openclaw_webchat_adapter.config import AdapterSettings
                settings = AdapterSettings(url="ws://test", session_key="test")
                adapter = OpenClawChatWsAdapter(settings=settings, ws_factory=_fake_ws_factory)
                adapter.start(timeout_s=1.0)
                mock_create.return_value = adapter
                
                api = OpenClawWebChatAPI.create_connected_from_env(dotenv_path=str(dotenv_path))
                try:
                    self.assertIs(api._adapter, adapter)
                    
                    # 测试 get_chat_history
                    history = api.get_chat_history(session_key="test")
                    self.assertEqual(len(history.messages), 1)
                    self.assertEqual(history.messages[0].role, "user")
                    
                    # 测试 stream_chat
                    chunks = list(api.stream_chat("hello"))
                    self.assertEqual("".join(chunks), "test response")

                    # 测试 get_chat_history_simple
                    simple_history = api.get_chat_history_simple(session_key="test")
                    self.assertEqual(len(simple_history), 1)
                    self.assertEqual(simple_history[0].role, "user")

                    # 测试 stop
                    api.stop()
                    self.assertIsNone(api._adapter._ws)
                finally:
                    api.close()

if __name__ == "__main__":
    unittest.main()
