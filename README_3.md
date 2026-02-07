# 如何和 OpenClaw Gateway 建立 WebSocket 连接并聊天（融合版）

这份文档把“你的原始笔记 + 关键纠正点 + 格式化示例”融合成一份可以直接照着实现的版本。

## 0) 三个 ID 的区别（先搞清楚）

- `req.id`：每一条 RPC 请求的 id，用来把 `res.id` 对回对应的 `req`（pending map 的 key）。
- `runId`：一次 `chat.send` 对应的一次“回复流”（delta/final/error/aborted 都带同一个 runId）。
- `sessionKey`：会话标识（上下文/历史归属）。同一个 sessionKey 里会有很多 runId。

## 1) 建连与握手（按顺序）

1. 建立 WebSocket：`ws://127.0.0.1:18789`
2. 收到服务端 `event=connect.challenge`（拿到 nonce，未来做 device 签名要用）
3. 发送第一条请求 `req(method="connect")`（在 `params.auth` 里带 token/password）
4. 收到 `res.payload.type == "hello-ok"`：握手完成，从这一刻开始才能安全发送 `chat.send`

纠正点：
- `connect.challenge` 不是“无关紧要”。如果你第二阶段实现 `device`，就必须把 `nonce` 放进 `device.nonce` 并参与签名（远程连接更重要）。
- WebSocket URL 里带 `?token=...` 不是 Gateway WS 协议的一部分；WS 鉴权以 `connect.params.auth` 为准。
- `chat.send` 的 `req.id` 不需要等于 `runId`：  
  - `req.id` 用来匹配 ack（`res.id`）  
  - `runId` 用来匹配后续 `event=chat` 的一整段流式输出

## 2) 详细流程与帧格式（可直接对照实现）
1. 在 OpenClaw Gateway 中配置 token 或 password，用于通过鉴权
2. 客户端发起 WebSocket 连接
3. Gateway 推送 `connect.challenge`（event），示例：

```json
{
  "type": "event",
  "event": "connect.challenge",
  "payload": {
    "nonce": "572d805a-f72d-4d8a-bf60-81c402f38608",
    "ts": 1770441654773
  }
}
```

说明（更正）：
- 这条 event 对“token-only 连接是否能握手成功”通常不是决定性因素，但 **nonce 会在第二阶段 device 签名里用到**（远程连接尤其重要）。

4. 客户端发送第一条请求 `connect`（req），用于握手 + 权限验证：

```json
{
  "type": "req",
  "id": "REQ_ID_UUID",
  "method": "connect",
  "params": {
    "minProtocol": 3,
    "maxProtocol": 3,
    "client": {
      "id": "webchat-ui",
      "displayName": "my-web-adapter",
      "version": "dev",
      "platform": "browser",
      "mode": "webchat",
      "instanceId": "tab-1"
    },
    "auth": { "token": "YOUR_TOKEN" },
    "role": "operator",
    "scopes": ["operator.admin"]
  }
}
```
5. 如果之后 openclaw 会放回（connect 的响应）
```text
 {'type': 'res', 'id': 'b025db99-383a-4f61-80a5-4640b1eaa4f7', 'ok': True, 'payload': {'type': 'hello-ok', 'protocol': 3, 'server': {'version': 'dev', 'host': 'hadage', 'connId': '26bb8cd8-7aa9-4737-80ac-a6b7201120fa'}, 'features': {'methods': ['health', 'logs.tail', 'channels.status', 'channels.logout', 'status', 'usage.status', 'usage.cost', 'tts.status', 'tts.providers', 'tts.enable', 'tts.disable', 'tts.convert', 'tts.setProvider', 'config.get', 'config.set', 'config.apply', 'config.patch', 'config.schema', 'exec.approvals.get', 'exec.approvals.set', 'exec.approvals.node.get', 'exec.approvals.node.set', 'exec.approval.request', 'exec.approval.resolve', 'wizard.start', 'wizard.next', 'wizard.cancel', 'wizard.status', 'talk.mode', 'models.list', 'agents.list', 'skills.status', 'skills.bins', 'skills.install', 'skills.update', 'update.run', 'voicewake.get', 'voicewake.set', 'sessions.list', 'sessions.preview', 'sessions.patch', 'sessions.reset', 'sessions.delete', 'sessions.compact', 'last-heartbeat', 'set-heartbeats', 'wake', 'node.pair.request', 'node.pair.list', 'node.pair.approve', 'node.pair.reject', 'node.pair.verify', 'device.pair.list', 'device.pair.approve', 'device.pair.reject', 'device.token.rotate', 'device.token.revoke', 'node.rename', 'node.list', 'node.describe', 'node.invoke', 'node.invoke.result', 'node.event', 'cron.list', 'cron.status', 'cron.add', 'cron.update', 'cron.remove', 'cron.run', 'cron.runs', 'system-presence', 'system-event', 'send', 'agent', 'agent.identity.get', 'agent.wait', 'browser.request', 'chat.history', 'chat.abort', 'chat.send'], 'events': ['connect.challenge', 'agent', 'chat', 'presence', 'tick', 'talk.mode', 'shutdown', 'health', 'heartbeat', 'cron', 'node.pair.requested', 'node.pair.resolved', 'node.invoke.request', 'device.pair.requested', 'device.pair.resolved', 'voicewake.changed', 'exec.approval.requested', 'exec.approval.resolved']}, 'snapshot': {'presence': [{'host': 'hadage', 'ip': '26.26.26.1', 'version': 'unknown', 'platform': 'windows 10.0.22631', 'deviceFamily': 'Windows', 'modelIdentifier': 'x64', 'mode': 'gateway', 'reason': 'self', 'text': 'Gateway: hadage (26.26.26.1) · app unknown · mode gateway · reason self', 'ts': 1770468121551}, {'host': 'my-web-adapter', 'version': 'dev', 'platform': 'browser', 'mode': 'webchat', 'roles': ['operator'], 'scopes': ['operator.admin'], 'instanceId': 'tab-1', 'reason': 'connect', 'ts': 1770468121550, 'text': 'Node: my-web-adapter · mode webchat'}], 'health': {'ok': True, 'ts': 1770468083458, 'durationMs': 0, 'channels': {}, 'channelOrder': [], 'channelLabels': {}, 'heartbeatSeconds': 1800, 'defaultAgentId': 'main', 'agents': [{'agentId': 'main', 'isDefault': True, 'heartbeat': {'enabled': True, 'every': '30m', 'everyMs': 1800000, 'prompt': 'Read HEARTBEAT.md if it exists (workspace context). Follow it strictly. Do not infer or repeat old tasks from prior chats. If nothing needs attention, reply HEARTBEAT_OK.', 'target': 'last', 'ackMaxChars': 300}, 'sessions': {'path': 'C:\\Users\\15328\\.openclaw\\agents\\main\\sessions\\sessions.json', 'count': 1, 'recent': [{'key': 'agent:main:main', 'updatedAt': 1770467951855, 'age': 131603}]}}], 'sessions': {'path': 'C:\\Users\\15328\\.openclaw\\agents\\main\\sessions\\sessions.json', 'count': 1, 'recent': [{'key': 'agent:main:main', 'updatedAt': 1770467951855, 'age': 131603}]}}, 'stateVersion': {'presence': 65, 'health': 484}, 'uptimeMs': 26908756, 'configPath': 'C:\\Users\\15328\\.openclaw\\openclaw.json', 'stateDir': 'C:\\Users\\15328\\.openclaw', 'sessionDefaults': {'defaultAgentId': 'main', 'mainKey': 'main', 'mainSessionKey': 'agent:main:main', 'scope': 'per-sender'}}, 'canvasHostUrl': 'http://127.0.0.1:18789', 'policy': {'maxPayload': 524288, 'maxBufferedBytes': 1572864, 'tickIntervalMs': 30000}}}
```

只需要关注：`type="res"` 且 `payload.type == "hello-ok"`，表示握手成功，可以开始通过当前的 socket 连接聊天。

6. 客户端聊天请求 `chat.send`（req）格式：

```json
{
  "type": "req",
  "id": "REQ_ID_3_UUID",
  "method": "chat.send",
  "params": {
    "sessionKey": "agent:main:main",
    "message": "hello",
    "idempotencyKey": "RUN_ID_UUID"
  }
}
```

说明（更正）：
- `id`（REQ_ID_3_UUID）是“请求-响应配对”的 id
- `idempotencyKey`（RUN_ID_UUID）是“这次聊天运行”的幂等键，后续 event=chat 会用它当 `runId`

7. 客户端收到 openclaw 返回的消息格式

第一条通常是 ack（res）：

```json
{
  "type": "res",
  "id": "REQ_ID_3_UUID",
  "ok": true,
  "payload": { "runId": "RUN_ID_UUID", "status": "started" }
}
```

说明（更正）：
- `payload.runId` 应该等于你发 `chat.send` 时的 `idempotencyKey`
- 后续的 `event=chat.payload.runId` 也应该等于这个 runId（同一次请求的流式输出）

接下来就是 openclaw 的回复（event=chat），示例（delta）：

```json
{
  "type": "event",
  "event": "chat",
  "payload": {
    "runId": "RUN_ID_UUID",
    "sessionKey": "agent:main:main",
    "seq": 1,
    "state": "delta",
    "message": {
      "role": "assistant",
      "content": [{ "type": "text", "text": "你好！欢迎回来！" }],
      "timestamp": 1770471294110
    }
  }
}
```

拼接要点：
- `delta` 里的 `message.content[0].text` 通常是“截至目前完整文本”，建议做前缀差分，只输出新增部分
- `final` 表示结束；`error/aborted` 表示失败/中止


8) 通过这几步就完成了建立 websocket 连接并和 openclaw 交流



