"""测试 chat.history 接口的单元测试。"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from openclaw_webchat_adapter.ws_adapter import OpenClawChatWsAdapter
from openclaw_webchat_adapter.config import AdapterSettings


class TestChatHistory(unittest.TestCase):
    """测试 get_chat_history 方法的各类场景。"""

    def setUp(self):
        """设置测试环境。"""
        self.settings = AdapterSettings(
            url="ws://127.0.0.1:18789",
            session_key="agent:main:main",
            client_id="test-client",
            client_mode="test",
            client_display_name="Test Client",
        )
        self.adapter = OpenClawChatWsAdapter(settings=self.settings)
        self.adapter._hello_ok.set()

    def test_get_chat_history_success(self):
        """测试成功获取历史聊天记录。"""
        mock_response = {
            "sessionKey": "agent:main:main",
            "sessionId": "sess-1",
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "nihao"}],
                    "timestamp": 1770794234304,
                },
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "hello"}],
                    "api": "openai-completions",
                    "provider": "qwen-portal",
                    "model": "coder-model",
                    "usage": {
                        "input": 1,
                        "output": 2,
                        "cacheRead": 3,
                        "cacheWrite": 4,
                        "totalTokens": 5,
                        "cost": {
                            "input": 1,
                            "output": 2,
                            "cacheRead": 3,
                            "cacheWrite": 4,
                            "total": 10,
                        },
                    },
                    "stopReason": "stop",
                    "timestamp": 1770794234312,
                },
            ],
            "thinkingLevel": "off",
        }

        with patch.object(self.adapter, "request", return_value=mock_response):
            result = self.adapter.get_chat_history()

        self.assertEqual(result.session_key, "agent:main:main")
        self.assertEqual(result.session_id, "sess-1")
        self.assertEqual(len(result.messages), 2)
        self.assertEqual(result.messages[0].content[0].text, "nihao")

    def test_get_chat_history_with_custom_params(self):
        """测试使用自定义参数获取历史记录。"""
        mock_response = {
            "sessionKey": "custom:session:test",
            "sessionId": "sess-2",
            "messages": [],
            "thinkingLevel": "off",
        }

        with patch.object(self.adapter, "request", return_value=mock_response) as mock_request:
            self.adapter.get_chat_history(
                session_key="custom:session:test", limit=50
            )

        mock_request.assert_called_once_with(
            "chat.history",
            {"sessionKey": "custom:session:test", "limit": 50},
            timeout_s=15.0,
        )

    def test_get_chat_history_default_session_key(self):
        """测试使用默认 session_key。"""
        mock_response = {"sessionKey": "agent:main:main", "sessionId": "sess-3", "messages": [], "thinkingLevel": "off"}

        with patch.object(self.adapter, "request", return_value=mock_response) as mock_request:
            self.adapter.get_chat_history()

        mock_request.assert_called_once_with(
            "chat.history",
            {"sessionKey": "agent:main:main", "limit": 200},
            timeout_s=15.0,
        )

    def test_get_chat_history_none_session_key(self):
        """测试 session_key 参数为 None 时使用默认值。"""
        mock_response = {"sessionKey": "agent:main:main", "sessionId": "sess-4", "messages": [], "thinkingLevel": "off"}

        with patch.object(self.adapter, "request", return_value=mock_response) as mock_request:
            self.adapter.get_chat_history(session_key=None)

        mock_request.assert_called_once_with(
            "chat.history",
            {"sessionKey": "agent:main:main", "limit": 200},
            timeout_s=15.0,
        )

    def test_get_chat_history_invalid_session_key(self):
        """测试无效的 session_key 参数。"""
        with self.assertRaises(ValueError) as ctx:
            self.adapter.get_chat_history(session_key="")
        self.assertIn("session_key must be a non-empty string", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            self.adapter.get_chat_history(session_key="   ")
        self.assertIn("session_key must be a non-empty string", str(ctx.exception))

    def test_get_chat_history_invalid_limit(self):
        """测试无效的 limit 参数。"""
        with self.assertRaises(ValueError) as ctx:
            self.adapter.get_chat_history(limit=0)
        self.assertIn("limit must be a positive integer", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            self.adapter.get_chat_history(limit=-1)
        self.assertIn("limit must be a positive integer", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            self.adapter.get_chat_history(limit="100")
        self.assertIn("limit must be a positive integer", str(ctx.exception))

    def test_get_chat_history_empty_messages(self):
        """测试返回空消息列表的场景。"""
        mock_response = {"sessionKey": "agent:main:main", "sessionId": "sess-5", "messages": [], "thinkingLevel": "off"}

        with patch.object(self.adapter, "request", return_value=mock_response):
            result = self.adapter.get_chat_history()

        self.assertEqual(result.session_key, "agent:main:main")
        self.assertEqual(len(result.messages), 0)

    def test_get_chat_history_large_dataset(self):
        """测试大数据集的分页场景。"""
        messages = [
            {
                "role": "user" if i % 2 == 0 else "assistant",
                "content": [{"type": "text", "text": f"Message {i}"}],
                "timestamp": 1234567890 + i,
            }
            for i in range(100)
        ]
        mock_response = {"sessionKey": "agent:main:main", "sessionId": "sess-6", "messages": messages, "thinkingLevel": "off"}

        with patch.object(self.adapter, "request", return_value=mock_response):
            result = self.adapter.get_chat_history(limit=100)

        self.assertEqual(len(result.messages), 100)
        self.assertEqual(result.messages[0].content[0].text, "Message 0")
        self.assertEqual(result.messages[-1].content[0].text, "Message 99")

    def test_get_chat_history_request_timeout(self):
        """测试请求超时场景。"""
        from openclaw_webchat_adapter.exceptions import RequestTimeoutError

        with patch.object(
            self.adapter, "request", side_effect=RequestTimeoutError("Request timeout")
        ):
            with self.assertRaises(RequestTimeoutError):
                self.adapter.get_chat_history()

    def test_get_chat_history_request_failed(self):
        """测试网关返回错误场景。"""
        from openclaw_webchat_adapter.exceptions import RequestFailedError

        with patch.object(
            self.adapter, "request", side_effect=RequestFailedError("Gateway error")
        ):
            with self.assertRaises(RequestFailedError):
                self.adapter.get_chat_history()

    def test_get_chat_history_custom_timeout(self):
        """测试自定义超时时间。"""
        mock_response = {"sessionKey": "agent:main:main", "sessionId": "sess-7", "messages": [], "thinkingLevel": "off"}

        with patch.object(self.adapter, "request", return_value=mock_response) as mock_request:
            self.adapter.get_chat_history(timeout_s=30.0)

        mock_request.assert_called_once()
        call_args = mock_request.call_args
        self.assertEqual(call_args[1]["timeout_s"], 30.0)

    def test_get_chat_history_chinese_text_mapping(self):
        """测试中文文本映射。"""
        mock_response = {
            "sessionKey": "agent:main:main",
            "sessionId": "sess-8",
            "messages": [{"role": "user", "content": [{"type": "text", "text": "测试中文"}], "timestamp": 1234567890}],
            "thinkingLevel": "off",
        }
        with patch.object(self.adapter, "request", return_value=mock_response):
            result = self.adapter.get_chat_history()
        self.assertEqual(result.messages[0].content[0].text, "测试中文")


if __name__ == "__main__":
    unittest.main()
