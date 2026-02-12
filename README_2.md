# ws-openclaw-client

一个最小可运行的 WebSocket 客户端示例：连接 OpenClaw Gateway，完成握手（connect / hello-ok），然后调用 `health` 或进入 `chat.send` 的交互式聊天。

## chat.history（历史消息查询）

- 请求示例：

```json
{
  "type": "req",
  "id": "9562ea9d-fe01-4ef3-9432-d729c6cc1820",
  "method": "chat.history",
  "params": {
    "sessionKey": "agent:main:main",
    "limit": 200
  }
}
```

- 响应示例：

```json
{
  "sessionKey": "agent:main:main",
  "sessionId": "85647085-3d1c-42d9-8563-5185a2575c9a",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "nihao"
        }
      ],
      "timestamp": 1770794234304
    },
    {
      "role": "assistant",
      "content": [
        {
          "type": "text",
          "text": "Hey. I just came online. Who am I? Who are you? [[reply_to_current]]"
        }
      ],
      "api": "openai-completions",
      "provider": "qwen-portal",
      "model": "coder-model",
      "usage": {
        "input": 15004,
        "output": 20,
        "cacheRead": 512,
        "cacheWrite": 0,
        "totalTokens": 15536,
        "cost": {
          "input": 0,
          "output": 0,
          "cacheRead": 0,
          "cacheWrite": 0,
          "total": 0
        }
      },
      "stopReason": "stop",
      "timestamp": 1770794234312
    }
  ],
  "thinkingLevel": "off"
}
```

### 封装与方法完善
- 请求封装：仅使用 sessionKey 与 limit 两个参数。
- 响应封装：返回结构化对象，包含 sessionKey、sessionId、messages（role、content[type/text]、timestamp、可选 api/provider/model/usage/stopReason）与 thinkingLevel。
- 方法行为：get_chat_history 返回封装后的响应对象并执行严格参数校验，遵循字段白名单。

## 使用方式

1. 复制 `src/ws-openclaw-client/.env.example` 为 `src/ws-openclaw-client/.env`
2. 运行：

```bash
pnpm tsx src/ws-openclaw-client/run.ts
```

## 0) 快速索引（回答你提的 5 点）

1) 要实现和 gateway 建立 websocket 连接需要哪几步？  
- 看 [3) 连接步骤（必做清单）](#3-连接步骤必做清单)

2) 这些步骤分别在哪个小节实现？  
- 看 [3) 连接步骤（必做清单）](#3-连接步骤必做清单) 的“对应章节/对应 run.ts”

3) connect（握手第一条 req）到底要怎么发？token + device 必须吗？ConnectParams 详解  
- 看 [5) 握手 connect 与 ConnectParams 详解](#5-握手-connect-与-connectparams-详解)

4) 在哪里建立了最终可以聊天的 socket 连接？  
- 看 [6) 什么时候可以开始聊天？（可聊天连接的判定）](#6-什么时候可以开始聊天可聊天连接的判定)

5) device 字段怎么获取？必须需要吗？  
- 看第 5.4 小节：device（设备身份：publicKey/signature/signedAt/nonce）


## 1) 先明确：OpenClaw Gateway 的 WebSocket 不是“聊天/echo”而是“RPC + 事件推送”

你连上的 `ws://127.0.0.1:18789` 是一个“控制面 WebSocket”：

- **你发消息**：不是随便发 `"hello"` 字符串，而是发 **JSON 帧**（frame）
- **你调用方法**：用 `type="req"` 的请求帧（RPC request），比如 `health` / `sessions.patch` / `chat.send`
- **你收消息**：Gateway 会推送 `type="event"` 的事件帧，比如 `tick` / `chat` / `presence` 等

协议里把所有 WS 消息都定义为三种顶层帧（下面第 4 节会给出精确定义和示例）。

协议定义源码在：[frames.ts](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/protocol/schema/frames.ts#L20-L165)

## 3) 连接步骤（必做清单）

想要“连上 OpenClaw Gateway 并最终能聊天”，从协议角度你必须按顺序实现下面这些步骤（我用【必做】/【聊天必做】标出来）：

1) 【必做】建立 WebSocket 连接（ws:// 或 wss://）  
- 对应章节：3.1  
- 对应 run.ts：`client.start()`（run.ts 本身不直接 new WebSocket）  

2) 【必做】解析并分发三种帧：`req` / `res` / `event`  
- 对应章节：4  
- 对应 run.ts：只消费事件（`onEvent`）；真正的帧解析/校验/关联由 `GatewayClient` 实现  

3) 【必做】握手：接收 `event=connect.challenge` 拿 nonce  
- 对应章节：5.1  
- 对应 run.ts：由 `GatewayClient` 内部完成（你做 Web 适配器需要自己实现）  

4) 【必做】握手：发送第一条请求 `req(method="connect")`，params 为 `ConnectParams`（带上你的鉴权信息）  
- 对应章节：5.2（ConnectParams 详解也在这里）  
- 对应 run.ts：由 `GatewayClient.sendConnect()` 自动完成  

5) 【必做】握手：等待 `connect` 的响应 payload=`hello-ok`（握手成功标志）  
- 对应章节：5.5  
- 对应 run.ts：`await withTimeout(helloOk, ...)`（等待 `onHelloOk` 触发）  

6) 【聊天必做】确保会话存在且允许发送（例如 `sessions.patch` / sendPolicy）  
- 对应章节：6.2（发送/接收位置里会指出）  
- 对应 run.ts：`sessions.patch`  

7) 【聊天必做】发送 `chat.send`，并接收 `event=chat` 的 delta/final 进行流式展示  
- 对应章节：6.2（接收）、6.3（发送）  
- 对应 run.ts：`chat.send` + `onEvent` 处理 `event=chat`  

本小节在聊天中的作用：
- 这张清单就是你未来写 Web 客户端适配器时的“最小必做 checklist”：把 1~5 做完连接就“可用”，把 6~7 做完就“能聊天”。

### 3.1 run.ts 是怎么“建立 WS 连接”的？

run.ts 自己没有 `new WebSocket(...)`，它是通过 `GatewayClient.start()` 间接完成的。

在 [GatewayClient.start](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/client.ts#L101-L165) 里：

- `this.ws = new WebSocket(url, wsOptions);`（使用 Node 的 `ws` 库）
- 监听：
  - `open`：连接建立（TCP/TLS + WebSocket 握手完成）
  - `message`：收到服务端发来的任何帧（JSON string）
  - `close` / `error`：断开/错误处理

所以 **WS 的建立** 在 `GatewayClient.start()` 内部完成，而 run.ts 只负责调用：

- `client.start()`：[run.ts](file:///f:/aaa_desktop_file/openclaw/openclaw/src/ws-openclaw-client/run.ts#L185-L191)

---

## 4) WS 上“发送/接收消息”的完整格式（你做 Web 适配器必须实现）

协议定义（最权威）在：[frames.ts](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/protocol/schema/frames.ts#L126-L165)

### 4.1 请求帧（客户端 -> 服务端）：RequestFrame

```json
{
  "type": "req",
  "id": "uuid-string",
  "method": "health",
  "params": { }
}
```

- `id`：你生成的请求 ID，用来和响应匹配（关键：你要维护一个 pending map）
- `method`：调用的方法名（必须是 Gateway 支持的）
- `params`：该方法参数（不同 method 不同结构）

对应 schema：`RequestFrameSchema` [frames.ts](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/protocol/schema/frames.ts#L126-L135)

### 4.2 响应帧（服务端 -> 客户端）：ResponseFrame

```json
{
  "type": "res",
  "id": "same-as-req-id",
  "ok": true,
  "payload": { }
}
```

失败时：

```json
{
  "type": "res",
  "id": "same-as-req-id",
  "ok": false,
  "error": { "code": "INVALID_REQUEST", "message": "..." }
}
```

对应 schema：`ResponseFrameSchema` [frames.ts](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/protocol/schema/frames.ts#L136-L145)

### 4.3 事件帧（服务端 -> 客户端，推送）：EventFrame

```json
{
  "type": "event",
  "event": "tick",
  "payload": { "ts": 123 },
  "seq": 42,
  "stateVersion": { "health": 10, "presence": 3 }
}
```

- `event`：事件名
- `payload`：事件数据（不同 event 不同结构）
- `seq`：全局递增序号，用于检测丢帧（断网/阻塞时很关键）
- `stateVersion`：某些状态的版本号（做增量同步/缓存会用到）

对应 schema：`EventFrameSchema` [frames.ts](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/protocol/schema/frames.ts#L147-L156)

> 你在 Web 端要做“可靠 UI/同步”，一定要实现 `seq gap` 检测：GatewayClient 里就有 `lastSeq` + `onGap` 的逻辑（见 [client.ts](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/client.ts#L302-L308)）。

---

## 5) “身份认证 / 握手”完整流程（最重要）

这里是你以后写 Web 适配器最需要搞懂的部分。

### 5.1 服务端一连上就推 challenge

服务端在新连接建立后，立即推送：

- `event = "connect.challenge"`，payload 里有 `nonce`

源码位置：[ws-connection.ts](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/server/ws-connection.ts#L120-L125)

它长这样：

```json
{
  "type": "event",
  "event": "connect.challenge",
  "payload": { "nonce": "<randomUUID>", "ts": 1700000000000 }
}
```

作用：
- 对“非本地/不可信连接”强制加入 nonce，防止设备签名被重放
- 让客户端把这个 nonce 填进 `connect.params.device.nonce`

### 5.2 客户端发送 connect（这是“握手请求”，也是第一条 req）& ConnectParams 详解

客户端必须发：

- `type="req"`, `method="connect"`, `params` 为 `ConnectParams`

ConnectParams 的 schema 在：[frames.ts:ConnectParamsSchema](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/protocol/schema/frames.ts#L20-L68)

核心字段：

- `minProtocol` / `maxProtocol`：协议版本协商
- `client`：客户端信息（id/displayName/version/platform/mode/instanceId）
- `auth`（可选）：共享 `token` 或 `password`
- `device`（可选但通常建议有）：设备身份（公钥 + 签名 + signedAt + nonce）

#### 5.2.1 这条 connect “最小长什么样”（示例）

下面是一个“可对照理解字段”的最小 connect 请求帧示例（具体值你要按实际替换）：

```json
{
  "type": "req",
  "id": "b2d0e2d4-6d84-4c3f-8cb6-2f41f2fce7a3",
  "method": "connect",
  "params": {
    "minProtocol": 1,
    "maxProtocol": 1,
    "client": {
      "id": "webchat-ui",
      "displayName": "my-web-adapter",
      "version": "dev",
      "platform": "browser",
      "mode": "webchat",
      "instanceId": "tab-1"
    },
    "auth": { "token": "YOUR_GATEWAY_TOKEN" }
  }
}
```

注意：
- `client.id/mode` 不是随便写字符串，推荐用现有枚举（见 [client-info.ts](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/protocol/client-info.ts#L1-L33)）
- `minProtocol/maxProtocol` 必须覆盖服务端支持的版本，否则握手失败

#### 5.2.2 你配置了 token 鉴权：connect 时需要传 token + device 吗？（重点回答）

先说结论（按“普通 Web 客户端适配器”的现实情况）：

- 如果你的 Gateway 配置的是 **token 鉴权**，那么 connect 时 **必须提供 `auth.token`**（否则服务端会在握手阶段拒绝）。  
- `device` **不是“必然必须”**：如果你只想“先连上并能聊天”，在某些客户端/策略分支里可以只带 token，不带 device。  
- 但如果你要走“设备配对（pairing）/下发 deviceToken/更强的设备身份”，那你最终还是应该实现 `device`。

为什么会这样（对应服务端实现逻辑）：
- 服务端会先校验你带没带 `device`，以及有没有 token/password：[message-handler.ts](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/server/ws-connection/message-handler.ts#L368-L420)
- 然后会跑统一的鉴权（token/password/其它）：[message-handler.ts](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/server/ws-connection/message-handler.ts#L570-L625)
- 如果你带了 device，还会进入“是否需要配对/是否已配对”的流程（可能会返回 NOT_PAIRED）：[message-handler.ts](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/server/ws-connection/message-handler.ts#L627-L720)

你当前的 Node 示例为什么“没感觉到你手动传 device”也能连上：
- 因为 `GatewayClient` 默认会 `loadOrCreateDeviceIdentity()`，基本等于“总是带 device”：[GatewayClient.constructor](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/client.ts#L94-L99)

#### 5.2.3 ConnectParams 每个字段在“聊天”里的作用

- `minProtocol/maxProtocol`：保证客户端和 Gateway 说的是同一套协议（否则连 hello-ok 都拿不到）
- `client`：影响服务端安全策略分支、日志、能力识别（例如 webchat/ui/cli 的差异）
- `auth`：决定你是否“有资格连上”以及能否执行 `chat.send` 等方法
- `device`：决定你能否进入“配对体系”、能否拿到/复用 `deviceToken`、以及是否需要处理 pairing required

**在 GatewayClient 里，这一步由 `sendConnect()` 自动完成**  
见：[GatewayClient.sendConnect](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/client.ts#L178-L286)

其中它会做：

1) 选用认证信息（优先级）：
- 先尝试加载本机缓存的 **deviceToken**（之前配对/授权过）  
  读取：[loadDeviceAuthToken](file:///f:/aaa_desktop_file/openclaw/openclaw/src/infra/device-auth-store.ts#L71-L90)
- 没有的话才用 `.env` 里的共享 `token/password`

2) 生成 device 签名：
- payload 规则：[buildDeviceAuthPayload](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/device-auth.ts#L13-L31)
- 签名算法：Ed25519  
  见：[signDevicePayload](file:///f:/aaa_desktop_file/openclaw/openclaw/src/infra/device-identity.ts#L122-L126)

> 结论：**你以后做 Web 客户端，如果不想折腾设备密钥/签名，最简单是让 Gateway 允许 token/password 模式**（但安全性取决于你的部署环境）。

### 5.3 服务端验证 connect（协议版本/角色/设备身份/token/password）

服务端握手处理在：[message-handler.ts](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/server/ws-connection/message-handler.ts#L262-L492)

它会检查：

- 第一条请求必须是 `method="connect"`，且 `ConnectParams` 合法，否则直接关连接
- 协议版本是否匹配
- role 是否允许（operator/node）
- 设备身份：
  - deviceId 是否和 publicKey 派生值一致
  - signedAt 是否在可接受时间窗口内
  - nonce 在非本地连接时必须存在且匹配 challenge 的 nonce
  - signature 验证通过（Ed25519）

共享 auth（token/password）模式也在握手阶段判定（依赖你的 Gateway 配置）。

### 5.4 device（设备身份：publicKey/signature/signedAt/nonce）

`device` 这一坨字段经常让人困惑，但你可以把它理解成：**“这个客户端实例的长期身份”**（更像“设备证书”），而不是一次性的 token。

它解决的问题：
- 让服务端能识别“是不是同一个设备/客户端”
- 支持“配对（pairing）”：首次连接可能会要求批准，批准后下次就不需要
- 支持下发 `deviceToken`：相当于“和设备身份绑定的 token”，后续可复用
- 远程连接时配合 `connect.challenge.nonce` 防重放（nonce 会参与签名）

**device 字段怎么来的（Node 版，也就是本仓库 GatewayClient 的做法）**
- 第一次运行时，本机会生成并保存一对 Ed25519 密钥（公钥/私钥），并派生出 `deviceId`  
  - 生成/加载逻辑：[device-identity.ts](file:///f:/aaa_desktop_file/openclaw/openclaw/src/infra/device-identity.ts#L64-L120)
  - `deviceId` 本质上是公钥的 sha256 指纹（用于稳定标识）
- 每次 connect 时：
  - 把若干字段拼成一个 payload 字符串：[device-auth.ts](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/device-auth.ts#L13-L31)
  - 用私钥对 payload 做签名（得到 `signature`）：[signDevicePayload](file:///f:/aaa_desktop_file/openclaw/openclaw/src/infra/device-identity.ts#L122-L126)
  - 把 `publicKey/signature/signedAt/nonce` 放进 ConnectParams.device

**Web 适配器怎么做（浏览器思路）**
- 你需要一个“可持久化的 keypair”（例如存 IndexedDB），并能做 Ed25519 签名
- 你需要在收到 `connect.challenge` 后，把 `nonce` 放进 payload 再签名

**必须需要吗？（再强调一次）**
- 不一定“协议上永远必须”，但如果你要做“完整且可长期使用”的 Web 客户端，最终建议实现它。  
- 如果你只想先跑通“能连上并能聊天”，并且你的 Gateway 允许共享 token 鉴权，那么你可以先只实现 `auth.token`，把 device 放到第二阶段。

补充：`OPENCLAW_GATEWAY_TLS_FINGERPRINT`（TLS 证书指纹）不是 device  
- 这是 wss:// 下的证书 pinning（防止连错服务器），与 ConnectParams.device 无关
- Node 版校验逻辑在：[GatewayClient.start](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/client.ts#L105-L137) 和 [GatewayClient.validateTlsFingerprint](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/client.ts#L388-L413)

本小节在聊天中的作用：
- device 决定了你会不会遇到 “pairing required”，以及能不能拿到/复用 `deviceToken`，从而影响你未来 Web 端的登录/授权体验设计。

### 5.5 服务端返回 hello-ok（握手成功标志）

握手成功后，服务端对 `connect` 这条 req 回一个 res，payload 结构是 `HelloOk`：

schema：[HelloOkSchema](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/protocol/schema/frames.ts#L70-L113)

典型 payload（简化）：

```json
{
  "type": "hello-ok",
  "protocol": 1,
  "server": { "version": "x.y.z", "connId": "..." },
  "features": {
    "methods": ["health", "chat.send", "sessions.patch", "..."],
    "events": ["tick", "chat", "presence", "..."]
  },
  "auth": {
    "deviceToken": "....",
    "role": "operator",
    "scopes": ["operator.admin"]
  },
  "policy": { "maxPayload": 123, "tickIntervalMs": 30000, "maxBufferedBytes": 123 }
}
```

关键点：
- `features.methods/events`：这是“动态能力表”，Web 客户端可以用它来做“是否支持某功能”的判断
- `auth.deviceToken`：服务端可能下发 deviceToken，客户端可以缓存，下次连接用它当 `auth.token`（更像“设备会话 token”）

**GatewayClient 收到 hello-ok 后，会触发 onHelloOk**：  
见：[client.ts](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/client.ts#L250-L269)

并会把 `auth.deviceToken` 保存到本机：  
见：[storeDeviceAuthToken](file:///f:/aaa_desktop_file/openclaw/openclaw/src/infra/device-auth-store.ts#L92-L119)

---

## 6) 什么时候可以开始聊天？（可聊天连接的判定）

你问“在哪里建立了最终可以聊天的 socket 连接？”——关键点是：

- OpenClaw Gateway 不会再给你建第二条“聊天专用 socket”。  
- **就是同一条 WebSocket**：从 `ws.open` -> 收到 `connect.challenge` -> 发 `connect` -> 收到 `hello-ok`。  
- 当你收到 `hello-ok`（也就是 `onHelloOk` 被触发）时，这条连接就进入“已握手、可调用方法”的状态；从这一刻开始你才能安全调用 `chat.send` 并接收 `event=chat`。

run.ts 里对应的“可聊天判定点”是：
- 等待握手完成：`await withTimeout(helloOk, ...)`（本质是等 `onHelloOk`）：[run.ts](file:///f:/aaa_desktop_file/openclaw/openclaw/src/ws-openclaw-client/run.ts#L185-L191)
- 握手完成后立刻进入聊天相关调用：`sessions.patch` / `chat.send`（见下方 6.3）

本小节在聊天中的作用：
- 你把“可聊天连接”的状态机做对了，才能避免 `gateway not connected` / “握手没完就发 chat.send” 这类问题。

### 6.2 接收：onEvent(evt)

run.ts 通过 `GatewayClient` 的 `onEvent` 回调接收所有 `type="event"` 帧：

- [run.ts: onEvent](file:///f:/aaa_desktop_file/openclaw/openclaw/src/ws-openclaw-client/run.ts#L99-L172)

里面做了两类处理：

1) `tick` 忽略（太频繁）
2) `chat` 事件：解析 `delta/final/error`，把 assistant 输出流式打印到 stdout

如果你不用 `GatewayClient`，而是用原生 WS（浏览器）自己收消息，那么你需要按下面这种“事件帧格式”来解析：

**chat 事件帧（服务端 -> 客户端）**
- 顶层是 `EventFrame`：`{ type:"event", event:"chat", payload: ChatEvent }`
- 其中 `payload` 的 schema： [logs-chat.ts:ChatEventSchema](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/protocol/schema/logs-chat.ts#L64-L81)

典型示例（delta）：
```json
{
  "type": "event",
  "event": "chat",
  "payload": {
    "runId": "7a7b1f85-49b5-4d7c-8c9b-5e4c6c2e1ad2",
    "sessionKey": "agent:main:main",
    "seq": 1,
    "state": "delta",
    "message": {
      "role": "assistant",
      "content": [{ "type": "text", "text": "Hello" }],
      "timestamp": 1700000000000
    }
  }
}
```

典型示例（final）：
```json
{
  "type": "event",
  "event": "chat",
  "payload": {
    "runId": "7a7b1f85-49b5-4d7c-8c9b-5e4c6c2e1ad2",
    "sessionKey": "agent:main:main",
    "seq": 2,
    "state": "final",
    "message": {
      "role": "assistant",
      "content": [{ "type": "text", "text": "Hello, how can I help you?" }],
      "timestamp": 1700000000100
    }
  }
}
```

要点（你写 Web 适配器时必须处理）：
- `payload.runId`：把一次 `chat.send` 对应的一整次流式输出串起来（delta/final 共享同一个 runId）
- `payload.seq`：同一个 runId 的递增序号（可以用于调试/排序）
- `payload.state`：`delta | final | aborted | error`（你至少要处理 delta/final/error）
- `payload.message`：结构上是一个对象（内容块数组），`text` 一般在 `message.content[0].text`

### 6.3 发送：client.request(method, params)

run.ts 里所有“发消息”都通过 `client.request(...)`：

- `health`：[run.ts](file:///f:/aaa_desktop_file/openclaw/openclaw/src/ws-openclaw-client/run.ts#L243-L245)
- 确保会话存在：`sessions.patch`：[run.ts](file:///f:/aaa_desktop_file/openclaw/openclaw/src/ws-openclaw-client/run.ts#L192-L205)
- 发送聊天：`chat.send`：[run.ts](file:///f:/aaa_desktop_file/openclaw/openclaw/src/ws-openclaw-client/run.ts#L207-L219)

如果你不用 `GatewayClient`，而是用原生 WS（浏览器）自己发消息，那么你需要按下面这种“请求帧 + 响应帧格式”来构造与匹配：

**1) 发送 chat.send（客户端 -> 服务端）**
- 顶层是 `RequestFrame`：`{ type:"req", id, method:"chat.send", params }`
- params 的 schema： [logs-chat.ts:ChatSendParamsSchema](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/protocol/schema/logs-chat.ts#L34-L45)

示例（请求帧）：
```json
{
  "type": "req",
  "id": "5c2a5b11-2b86-48fe-98a5-78dbef73c9d1",
  "method": "chat.send",
  "params": {
    "sessionKey": "agent:main:main",
    "message": "hello",
    "idempotencyKey": "7a7b1f85-49b5-4d7c-8c9b-5e4c6c2e1ad2"
  }
}
```

你会收到一个响应帧（ack），payload 通常长这样（服务端实现见 [server-methods/chat.ts](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/server-methods/chat.ts#L302-L445)）：
```json
{
  "type": "res",
  "id": "5c2a5b11-2b86-48fe-98a5-78dbef73c9d1",
  "ok": true,
  "payload": { "runId": "7a7b1f85-49b5-4d7c-8c9b-5e4c6c2e1ad2", "status": "started" }
}
```

关键点（你写 Web 适配器时必须实现）：
- `id`：用于把 `res` 和对应的 `req` 关联起来（pending map）
- `idempotencyKey`：用于把 ack（runId）和后续 `event=chat` 的流式推送关联起来  
  这里服务端直接把 `idempotencyKey` 当作 `runId` 来用（所以你自己生成的 idempotencyKey 会出现在事件里）

**2) 为什么还要 sessions.patch（聊天前的可选步骤）**

run.ts 里为了保证“这次发 chat 一定能发出去”，会在聊天前调用一次 `sessions.patch`（把 sendPolicy 设为 allow）：
```json
{
  "type": "req",
  "id": "19bc4ad1-8e8d-4e4c-a635-0f1f7f8e7e4b",
  "method": "sessions.patch",
  "params": { "key": "main", "sendPolicy": "allow" }
}
```

如果你做 Web 端适配器，建议也保留这一步（至少在调试阶段），避免碰到 “send blocked by session policy”。

---

## 7) 你要做 Web 客户端适配器：最小必做清单（协议层）

如果你在浏览器里用原生 `WebSocket` 写一个适配器，建议你把它拆成 3 层：

### 7.1 Transport 层（纯 WS）
- `ws = new WebSocket(url)`
- `ws.onmessage = (ev) => parse JSON`
- `ws.send(JSON.stringify(frame))`

### 7.2 Protocol 层（GatewayFrame）
你必须实现这几个点：

- **解析三种帧**：req/res/event（见第 4 节）
- **pending map**：`Map<id, {resolve,reject}>`，收到 res 用 id resolve/reject
- **握手流程**：
  - 收 `connect.challenge`（event）拿 nonce
  - 发 `connect`（req）带上 device/auth 信息
  - 收 `hello-ok`（res payload）标记“已连接”
- **事件分发**：按 `event` 名称分发到不同 handler
- **seq gap 检测**（可选但强烈建议）：发现丢帧后做全量拉取/刷新 UI

### 7.3 App 层（methods/events）
- `health`、`sessions.patch`、`chat.send` 等方法的参数结构
- `chat` 事件的 delta/final 处理

方法列表可参考：
- hello-ok 里的 `features.methods`
- 仓库静态列表：[server-methods-list.ts](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/server-methods-list.ts#L3-L85)
- chat 参数 schema：[logs-chat.ts:ChatSendParamsSchema](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/protocol/schema/logs-chat.ts#L34-L45)
- chat 事件 schema：[logs-chat.ts:ChatEventSchema](file:///f:/aaa_desktop_file/openclaw/openclaw/src/gateway/protocol/schema/logs-chat.ts#L64-L81)

---
