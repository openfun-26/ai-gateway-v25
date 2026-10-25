# 接口文档（API Reference）

网关分两类接口：**对外网关 API**（端口 9010，供客户端调用，需 `sk-gw-` 密钥）与**管理台 API**（端口 9009，仅内网，无需登录，依赖端口隔离保护）。

---

## 1. 对外网关 API（默认 `http://127.0.0.1:9010`）

鉴权方式：`Authorization: Bearer sk-gw-xxxx`（管理台「客户端密钥」生成）。

### 1.1 对话补全（OpenAI 兼容）

```http
POST /v1/chat/completions
```

请求体（与 OpenAI 一致，常用字段全支持：`model/messages/stream/temperature/top_p/max_tokens/stop/tools` 等）：

```json
{
  "model": "auto",
  "messages": [{"role": "user", "content": "你好"}],
  "stream": false,
  "max_tokens": 1024
}
```

`model` 可填：

| 取值 | 行为 |
|---|---|
| 具体模型名 / 别名 | 按「渠道选择策略」调用该模型；失败按模型监控页顺序降级备选（可关） |
| `auto` | 规则路由（关键词命中→指定模型）→ 渠道健康度挑选 → 失败自动换下一个 |

响应（非流式）与 OpenAI 格式一致；**特殊响应头**：

| 响应头 | 含义 |
|---|---|
| `X-Gateway-Fallback: A -> B` | 主模型 A 失败，实际由备选 B（或 `auto(模型名)`）完成 |
| `X-Gateway-Auto-Rule: 关键词 -> 模型` | auto 命中了「关键词→模型」规则（关键词 URL 编码） |

流式：请求 `"stream": true` 时返回 `text/event-stream`（SSE，OpenAI chunk 格式或 Claude 事件格式，随入站协议）。

### 1.2 模型列表

```http
GET /v1/models
```

返回当前启用渠道的全部可用模型（OpenAI list 格式）。`auto` 是否可用取决于管理台 auto 开关。

### 1.3 向量

```http
POST /v1/embeddings
```

转发到支持 embeddings 的渠道（模型须存在于渠道模型表）。

### 1.4 Claude 协议

```http
POST /anthropic/v1/messages
```

Anthropic Messages 原生格式进出；网关按渠道协议自动转换（OpenAI 渠道 ↔ Claude 请求/响应双向映射，含 usage 换算）。

### 1.5 多格式路径兼容

以下拼法自动修正为 `/v1/chat/completions`（其余 14 个标准端点同理）：

```
/v4/v1/chat/completions   /api/paas/v4/chat/completions   /chat/completions
```

> 反代规则命中的路径优先走反代，不做修正。

### 1.6 错误格式

```json
{"error": {"message": "...", "type": "api_error|permission_error|invalid_request_error", "code": "..."}}
```

| 状态码 | 典型原因 |
|---|---|
| 401 | 缺少/错误密钥 |
| 403 | 模型不在密钥白名单 / 全局黑名单 / 管理路径访问 API 端口 |
| 404 | 模型不存在或未启用（含 auto 被关闭） |
| 429 | 触发 key 级或全局 RPS |
| 502 | 上游全部失败（含全部备选降级失败，message 含最后错误与尝试次数） |

---

## 2. 管理台 API（默认 `http://127.0.0.1:9009/admin/api`）

无登录鉴权（靠内网 + 端口隔离保护）。所有列表接口返回 `{"rows": [...]}`，写操作返回 `{"ok": true}`。

### 2.1 系统设置 `/settings`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/settings` | 全部设置 + 默认值 |
| PUT | `/settings` | 更新（body 传键值对，如 `{"auto_enabled":"1"}`） |
| POST | `/settings/vacuum` | SQLite VACUUM |
| GET | `/settings/export` | 导出全部配置（JSON） |
| POST | `/settings/import` | 导入配置 |

常用设置键：`port` / `admin_port` / `routing_strategy` / `global_max_retries` / `model_fallback` / `auto_enabled` / `auto_exclude_paid` / `health_interval_sec` / `log_retention_days` / `frp_config` / `frp_autostart`。

### 2.2 模型与 auto `/models`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/models?channel_id=&search=&status=` | 模型列表（顺序 = 降级顺序） |
| POST / PUT / DELETE | `/models`、`/models/{id}` | 增 / 改 / 删 |
| POST | `/models/reorder` | `{"id":9,"direction":"up"\|"down"}` 调整降级顺序 |
| GET / POST | `/models/auto-rules` | auto 规则列表 / 新增 `{"keyword","model_name","priority"}` |
| PUT / DELETE | `/models/auto-rules/{id}` | 改 / 删规则 |
| POST | `/models/health-check-all`、`/models/health-check-channel/{cid}` | 健康检测（异步） |
| POST | `/models/test` | 单模型测试 `{"channel_id","model","prompt"}` |
| POST | `/models/batch` | 批量启停/删除/改厂商/改备注 |
| POST | `/models/discover` | 从渠道拉取模型列表补录 |
| GET | `/models/export-csv` | CSV 导出 |

### 2.3 渠道 `/channels`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET / POST | `/channels` | 列表 / 新建 |
| PUT / DELETE | `/channels/{cid}` | 改 / 删（含 paid 付费标记字段） |
| POST | `/channels/{cid}/duplicate` | 复制（含模型） |
| POST | `/channels/{cid}/test` | 连通性测试 |
| POST | `/channels/{cid}/fetch-models` | 拉取上游模型列表 |
| POST | `/channels/{cid}/import-models` | 批量导入模型 |
| POST | `/channels/batch`、`/channels/import` | 批量操作 / 文本批量导入渠道 |
| GET | `/channels/groups` | 分组列表 |

### 2.4 密钥 `/keys`

`GET / POST /keys`、`PUT / DELETE /keys/{kid}`、`POST /keys/{kid}/reset-quota`、`POST /keys/{kid}/toggle`、`GET /keys/export-csv`。

### 2.5 路由策略 `/routing`

`GET /routing`、`PUT /routing/global`（全局策略/重试/熔断）、条件规则 `POST /routing/rules`、`PUT/DELETE /routing/rules/{rid}`、`POST /routing/rules/{rid}/move`。

### 2.6 日志 `/logs`

`GET /logs`（多维筛选分页）、`GET /logs/errors`（错误子集）、`GET /logs/{id}`、`GET /logs/export-csv`、`DELETE /logs/{id}`、`DELETE /logs`（清空）、`POST /logs/batch-delete`。

### 2.7 仪表盘 `/dashboard`

`GET /summary`、`/charts`、`/model-cards`、`/monitor`（实时监视）、`/alerts`；`POST /alerts/clear`、`/reset-stats`、`/clear-logs`、`/reset-circuits`、`/refresh-channels-daily`；`GET /export-today-csv`。

### 2.8 FRP `/frp`、反代与黑名单

| 方法 | 路径 | 说明 |
|---|---|---|
| GET / PUT | `/frp/config` | 读取 / 保存 frpc ini 配置（`{"config":"...","autostart":true}`） |
| GET | `/frp/status` | 进程状态 |
| POST | `/frp/start`、`/frp/stop` | 启停穿透 |
| GET | `/frp/logs`、POST `/frp/logs/clear` | 穿透日志 |
| GET / POST | `/proxy-rules`、`PUT/DELETE /proxy-rules/{rid}` | 透传反代规则 |
| GET / POST | `/blacklist`、`DELETE /blacklist/{bid}` | 全局模型黑名单 |
| GET | `/bootstrap` | 前端启动引导数据 |
