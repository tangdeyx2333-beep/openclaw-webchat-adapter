"""Test ws_adapter create_connected behavior with an injected fake WebSocket."""

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

from openclaw_webchat_adapter.config import AdapterSettings
from openclaw_webchat_adapter.ws_adapter import OpenClawGatewayWsAdapter


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
        self.sent_frames: "list[Dict[str, Any]]" = []

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
        self.sent_frames.append(frame)
        if frame.get("type") != "req":
            return
        req_id = frame.get("id")
        method = frame.get("method")
        if not isinstance(req_id, str):
            return
        if self._on_message is None:
            return
        if method == "sessions.patch":
            res = {"type": "res", "id": req_id, "ok": True, "payload": {}}
            self._on_message(self, json.dumps(res, ensure_ascii=False))
            return

        if method == "chat.send":
            res = {"type": "res", "id": req_id, "ok": True, "payload": {}}
            self._on_message(self, json.dumps(res, ensure_ascii=False))
            params = frame.get("params") or {}
            run_id = params.get("idempotencyKey") if isinstance(params, dict) else None
            if isinstance(run_id, str):
                evt = {
                    "type": "event",
                    "event": "chat",
                    "payload": {
                        "runId": run_id,
                        "state": "final",
                        "message": {"content": [{"type": "text", "text": "ok"}]},
                    },
                }
                self._on_message(self, json.dumps(evt, ensure_ascii=False))
            return

    def close(self) -> None:
        self._closed.set()
        if self._on_close is not None:
            self._on_close(self, None, None)


def _fake_ws_factory(url: str, **kwargs: Any) -> _FakeWebSocketApp:
    return _FakeWebSocketApp(url, **kwargs)


class TestCreateConnected(unittest.TestCase):
    def test_create_connected_performs_handshake_and_ensures_session(self) -> None:
        settings = AdapterSettings(url="ws://example", session_key="agent:main:main")
        adapter = OpenClawGatewayWsAdapter.create_connected(
            settings=settings,
            ensure_session_key="main",
            timeout_s=2.0,
            ws_factory=_fake_ws_factory,
        )
        try:
            self.assertIsInstance(adapter.hello_payload, dict)
            self.assertEqual(adapter.hello_payload.get("type"), "hello-ok")
        finally:
            adapter.stop()

    def test_create_connected_from_env_reads_dotenv_and_connects(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / ".env"
            dotenv_path.write_text(
                "\n".join(
                    [
                        "OPENCLAW_GATEWAY_URL=ws://from-dotenv",
                        "OPENCLAW_SESSION_KEY=agent:main:main",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                adapter = OpenClawGatewayWsAdapter.create_connected_from_env(
                    dotenv_path=str(dotenv_path),
                    dotenv_override=True,
                    timeout_s=2.0,
                    ws_factory=_fake_ws_factory,
                )
                try:
                    self.assertEqual(adapter._settings.url, "ws://from-dotenv")
                    self.assertIsNotNone(adapter._ws)
                    self.assertEqual(adapter._ws.url, "ws://from-dotenv")
                finally:
                    adapter.stop()

    def test_create_connected_from_env_allows_url_token_password_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            dotenv_path = Path(temp_dir) / ".env"
            dotenv_path.write_text(
                "\n".join(
                    [
                        "OPENCLAW_GATEWAY_URL=ws://ignored-dotenv",
                        "OPENCLAW_GATEWAY_TOKEN=dotenv-token",
                        "OPENCLAW_GATEWAY_PASSWORD=dotenv-pass",
                        "OPENCLAW_SESSION_KEY=agent:main:main",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True):
                adapter = OpenClawGatewayWsAdapter.create_connected_from_env(
                    url="ws://override",
                    token="override-token",
                    password="override-pass",
                    dotenv_path=str(dotenv_path),
                    dotenv_override=True,
                    timeout_s=2.0,
                    ws_factory=_fake_ws_factory,
                )
                try:
                    self.assertEqual(adapter._settings.url, "ws://override")
                    self.assertEqual(adapter._settings.token, "override-token")
                    self.assertEqual(adapter._settings.password, "override-pass")
                    self.assertIsNotNone(adapter._ws)
                    self.assertEqual(adapter._ws.url, "ws://override")
                finally:
                    adapter.stop()
