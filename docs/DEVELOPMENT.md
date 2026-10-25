# 开发文档（DEVELOPMENT）

面向想参与开发或自部署改造的开发者。读完即可上手改代码；更完整的技术细节（管线顺序、数据库、坑）见 [HANDOFF.md](HANDOFF.md)。

---

## 1. 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python ≥3.10 · FastAPI · uvicorn · httpx · aiosqlite（`backend/requirements.txt` 全锁定版本） |
| 前端 | Vue3 · Vite · 原生轻组件（`frontend/`，构建产物输出到项目根 `dist/`） |
| 存储 | SQLite（WAL 模式，写串行），单文件 `data/gateway.db`，无其他外部依赖 |
| 运行形态 | **单进程双端口**：`backend/run.py` 用 asyncio 同时跑两个 uvicorn Server（9010 API / 9009 管理台），DB 与后台任务只跑一份 |

## 2. 本地开发环境

```bash
# 后端（热重启可选 uvicorn --reload，但 run.py 是双端口启动器，建议直接跑）
pip install -r backend/requirements.txt
python backend/run.py                # 或 bash start.sh foreground

# 前端（改管理台界面时）
cd frontend && npm install
npm run dev                          # 开发服务器（API 代理见 vite.config）
npm run build                        # 产物输出到 ../dist，改完必须 build 才能在正式端口看到
```

> 运行期只读 `dist/`，改前端源码后必须重新 build。

## 3. 目录结构

```
backend/app/
├── main.py               # FastAPI 实例、中间件(_port_guard/_path_compat)、路由挂载、startup
├── core/
│   ├── config.py         # GATEWAY_VERSION、路径常量、DEFAULT_SETTINGS(所有设置键)
│   ├── database.py       # aiosqlite 封装(WAL、写串行)
│   ├── state.py          # AppState：冷却/熔断/并发/成功率/模型级冷却(内存态)
│   ├── limiter.py        # key 级与全局 RPS
│   └── cache.py          # TTL 缓存
├── db/
│   ├── schema.py         # 建表 SCHEMA + COLS 轻量迁移(缺列自动 ALTER)
│   └── repo.py           # CRUD + settings 读写(s_int/s_float)
├── gateway/
│   ├── auth.py           # 鉴权管线、resolve_model(auto 哨兵)、get_models_snapshot
│   ├── routes.py         # 对外端点(chat/models/embeddings/anthropic messages)
│   └── converters.py     # OpenAI↔Claude 双向协议转换
├── services/
│   ├── forward.py        # ★ 核心转发：auto 规则/健康度挑选、降级链、模型级隔离、SSE
│   ├── upstream.py       # pick_channels(渠道选择)、upstream_url(防双拼)、调用与重试
│   ├── health.py         # 健康检测 + 检测→路由联动冷却
│   ├── proxy.py          # OpenAI 透传反代
│   ├── stats.py / frp.py # 统计 / FRP 进程管理
└── routers/              # /admin/api/* 管理接口(dashboard/models/channels/keys/routing/logs/settings)
frontend/src/views/       # 8 个管理页面(Dashboard/ModelMonitor/Channels/ApiKeys/Routing/Logs/ErrorLogs/Settings)
```

## 4. 请求处理管线（改代码前必读）

```
CORS → _port_guard(端口隔离) → _path_compat(多格式路径修正, 仅API口) → 路由
网关请求: authenticate(Bearer/IP/额度/RPS/模型白名单) → resolve_model(别名/auto哨兵)
  → forward.handle_chat:
      auto 哨兵 → _match_auto_rule(关键词规则) → _pick_auto(健康度, 排除付费/冷却/熔断/并发) ×3次
      普通模型 → _run_channels(pick_channels 选渠道 → 调上游 → 重试/冷却/模型级隔离)
      全失败 → _fallback_models(模型监控顺序, 排除付费不影响这里) → auto 兜底
  → 协议转换(converters) → 上游调用(真实 upstream_model) → SSE/JSON → 计费 → 写 logs
```

## 5. 常见扩展怎么做

### 5.1 新增一个设置项（三步）

1. `core/config.py` 的 `DEFAULT_SETTINGS` 加键值（唯一权威来源）
2. 后端需要处用 `repo.s_int(await repo.get_settings(), "键名", 默认值)` 读取
3. 前端在对应页面加控件，`PUT /admin/api/settings` 提交

### 5.2 给表加列

`db/schema.py`：SCHEMA 里加列定义（新库）+ `COLS` 加迁移条目（旧库自动 `ALTER TABLE`）。改完删旧库或重启即生效。

### 5.3 新增管理 API

在 `routers/` 对应文件加 `@router.get/post/...`；涉及缓存的写操作记得 `cache.invalidate()`。

### 5.4 新增管理页面

`frontend/src/views/` 新建 `.vue` → 注册路由（`frontend/src/main.js`）→ `npm run build`。

## 6. 测试要点（改完必跑）

```bash
bash start.sh restart
# 1) 双端口基本功能
curl -o /dev/null -w "%{http_code}\n" http://127.0.0.1:9009/models      # 200 管理台页面
curl -o /dev/null -w "%{http_code}\n" http://127.0.0.1:9010/models      # 401 API(需密钥) = 多格式兼容仍生效
curl -o /dev/null -w "%{http_code}\n" http://127.0.0.1:9010/admin/      # 403 端口隔离
# 2) 业务回归（需已配置渠道与密钥）
curl http://127.0.0.1:9010/v1/chat/completions -H "Authorization: Bearer sk-gw-x" \
  -H "Content-Type: application/json" -d '{"model":"auto","messages":[{"role":"user","content":"hi"}]}'
```

- 改 auto/降级相关逻辑：验证规则命中（`X-Gateway-Auto-Rule` 头）、降级链（`X-Gateway-Fallback` 头）、模型级冷却跳过
- 改健康检测：触发 `POST /admin/api/models/health-check-channel/1` 后确认 offline 模型被路由绕开

## 7. 代码约定

- 全部异步（`async/await`），阻塞操作禁止入主循环；后台任务一律 `asyncio.create_task`
- 新增依赖必须锁定版本写入 `backend/requirements.txt`，且**纯 Python 或有 aarch64 wheel**（Termux 兼容红线）
- 端口隔离与双端口语义不可破坏；用户数据表结构变更必须走 `COLS` 迁移，禁止要求用户删库
- 响应头值只允许 latin-1：含中文的内容必须 `urllib.parse.quote`（踩过的坑，见 HANDOFF.md §坑）
