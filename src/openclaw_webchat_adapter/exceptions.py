"""为 OpenClaw Gateway 适配器定义类型化异常。"""

from __future__ import annotations


class OpenClawGatewayError(RuntimeError):
    """表示 OpenClaw Gateway 适配器抛出的基础异常类型。"""


class ConfigurationError(OpenClawGatewayError):
    """表示适配器配置缺失或不合法。"""


class GatewayClosedError(OpenClawGatewayError):
    """表示网关连接被意外关闭。"""


class ProtocolError(OpenClawGatewayError):
    """表示收到的协议帧不符合预期或不合法。"""


class RequestTimeoutError(OpenClawGatewayError):
    """表示 RPC 请求在超时时间内未收到响应。"""


class RequestFailedError(OpenClawGatewayError):
    """表示 RPC 请求失败，且网关返回了错误信息。"""


class ChatTimeoutError(OpenClawGatewayError):
    """表示对话流在超时时间内未完成。"""


class ChatFailedError(OpenClawGatewayError):
    """表示一次对话以 error/aborted 状态结束。"""

