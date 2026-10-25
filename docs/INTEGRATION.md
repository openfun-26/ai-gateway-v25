# 对接文档（客户端接入指南）

网关对外完全兼容 **OpenAI API**，任何支持「自定义 OpenAI Base URL」的客户端/SDK 都能直接使用。Claude 协议客户端走 `/anthropic/v1/messages`。

---

## 1. 拿到两样东西

| 需要 | 从哪来 |
|---|---|
| **Base URL** | `http://你的网关IP:9010/v1`（本机则 `http://127.0.0.1:9010/v1`；FRP 穿透后为 `http://你的服务器:远程端口/v1`） |
| **API Key** | 管理台「客户端密钥」生成的 `sk-gw-xxxx` |

## 2. OpenAI SDK

### Python

```python
from openai import OpenAI

client = OpenAI(
    api_key="sk-gw-xxxx",
    base_url="http://127.0.0.1:9010/v1",
)

# 普通对话（model 可用 auto / 别名 / 任意网关内模型）
resp = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "你好"}],
)
print(resp.choices[0].message.content)

# 流式
stream = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": "讲个故事"}],
    stream=True,
)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="", flush=True)
```

### Node.js / TypeScript

```ts
import OpenAI from "openai";

const client = new OpenAI({
  apiKey: "sk-gw-xxxx",
  baseURL: "http://127.0.0.1:9010/v1",
});

const stream = await client.chat.completions.create({
  model: "auto",
  messages: [{ role: "user", content: "你好" }],
  stream: true,
});
for await (const chunk of stream) {
  process.stdout.write(chunk.choices[0]?.delta?.content ?? "");
}
```

## 3. 第三方桌面/手机客户端

在客户端设置里选择「OpenAI / 自定义提供商」，填：

| 客户端 | API Host / Base URL | Key | 模型 |
|---|---|---|---|
| ChatBox | `http://IP:9010/v1` | sk-gw-xxxx | 填 `auto` 或具体模型名 |
| NextChat | 接口地址 `http://IP:9010`，无 `/v1`（它会自动拼） | sk-gw-xxxx | 同上 |
| LobeChat | `http://IP:9010/v1` | sk-gw-xxxx | 同上 |
| Open WebUI | OpenAI 兼容连接 `http://IP:9010/v1` | sk-gw-xxxx | 从 /v1/models 自动拉取 |

> 拼错路径没关系：网关会把 `/v4/v1/chat/completions`、`/chat/completions` 等自动修正为 `/v1/chat/completions`。

## 4. Claude 协议客户端

Base URL：`http://IP:9010`（Anthropic SDK 路径 `/anthropic/v1/messages` 由网关提供）：

```python
import anthropic

client = anthropic.Anthropic(
    api_key="sk-gw-xxxx",
    base_url="http://127.0.0.1:9010/anthropic",
)
msg = client.messages.create(
    model="auto",
    max_tokens=1024,
    messages=[{"role": "user", "content": "你好"}],
)
print(msg.content[0].text)
```

上游无论是 OpenAI 还是 Claude 协议渠道，网关自动完成双向转换。

## 5. curl 直接调用

```bash
# 非流式
curl http://127.0.0.1:9010/v1/chat/completions \
  -H "Authorization: Bearer sk-gw-xxxx" \
  -H "Content-Type: application/json" \
  -d '{"model":"auto","messages":[{"role":"user","content":"你好"}],"max_tokens":512}'

# 流式
curl -N http://127.0.0.1:9010/v1/chat/completions \
  -H "Authorization: Bearer sk-gw-xxxx" -H "Content-Type: application/json" \
  -d '{"model":"auto","stream":true,"messages":[{"role":"user","content":"你好"}]}'
```

## 6. 模型选择的建议

| 场景 | model 填法 |
|---|---|
| 不确定哪个模型可用 / 想自动容错 | `auto` |
| 有特定偏好且能接受降级 | 填首选模型名（失败会按你排好的顺序降级，响应头 `X-Gateway-Fallback` 会告知） |
| 必须锁定某个模型，失败就报错 | 管理台关闭「备选降级」（`model_fallback=0`）后填模型名 |
| 按问题类型走不同模型 | 在管理台配 auto 规则（如 `翻译→某模型`），然后统一用 `auto` |

## 7. 对接检查清单

- [ ] 网关已启动：`bash start.sh status`
- [ ] 密钥有效且未超额（管理台「客户端密钥」）
- [ ] 所用模型已添加且启用；用 `auto` 时确认模型监控页 auto 开关已开
- [ ] Base URL 末尾带 `/v1`（Anthropic 客户端除外）
- [ ] 防火墙/安全组放行 9010（或 FRP 远程端口）
- [ ] 外网访问只穿透 9010，**不要**穿透 9009 管理台

## 8. 常见错误

| 现象 | 处理 |
|---|---|
| 401 Missing API key | Key 填错或没加 `Authorization: Bearer` 前缀 |
| Model 'auto' not in key whitelist | 该密钥配了模型白名单，把 `auto` 加进白名单或清空白名单 |
| 502 全部 N 次调用失败 | 看管理台「错误日志」定位上游问题；网关会自动冷却故障渠道稍后重试 |
| 流式中断 | 检查反代/FRP 是否缓冲 SSE（Nginx 需 `proxy_buffering off`） |
