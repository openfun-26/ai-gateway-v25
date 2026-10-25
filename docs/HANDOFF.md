# 项目交接文档（HANDOFF · 基于 v20）

> **用途**：将本项目完整移交给下一位维护者（人或 AI），继续开发后续版本。
> 阅读本文档 + 浏览代码即可接手。所有路径相对项目根；配合 [DEVELOPMENT.md](DEVELOPMENT.md) 与 [API.md](API.md) 食用。

---

## 1. 项目一句话

单进程、零外部依赖的多协议 AI 聚合网关：FastAPI 后端 + Vue3 管理台（预编译 dist 托管），OpenAI/Claude 双协议转发 + OpenAI 透传反代，auto 智能路由 + 备选降级链 + 双端口安全隔离，SQLite 存储，PC 与 Termux(Android) 通用。当前版本 `v20`（`backend/app/core/config.py` 的 `GATEWAY_VERSION`）。

## 2. 运行形态（不可破坏的架构约定）

- **单进程双端口**：`backend/run.py` asyncio 同进程跑两个 uvicorn.Server（9010 API 对外可穿透 / 9009 管理台仅内网），DB 与后台任务只跑一份，任一退出带停另一个
- **零外部依赖**：禁止引入 Docker/Redis/MySQL/消息队列；后台任务全部 `asyncio.create_task`
- **Termux 兼容**：新依赖必须纯 Python 或有 aarch64 wheel；pydantic-core 走 `termux-setup.sh`（TUR 预编译）
- **降级安全承诺**（作者核心诉求）：用户指定模型失败后**不得随机换模型**（防误触付费模型产生费用）；备选只按用户制定的顺序（模型监控列表）取前 3 个；auto 兜底仅 `auto_enabled=1` 时生效；auto 默认排除付费渠道

## 3. 请求处理管线

### 3.1 中间件（`app/main.py`，执行顺序 CORS → `_port_guard` → `_path_compat`）

- `_port_guard`：请求端口 == `app.state.admin_port` 全放行；否则 `/`、`/admin/*`、`/assets/*` 等一律 403（HTML 请求返回中文提示页）。**这是安全隔离核心**
- `_path_compat`：**仅 API 端口生效**（v20 修复：9009 上重写会劫持管理台 SPA 页面路径如 `/models`）；非 `/v1` 前缀路径从后往前匹配 `_KNOWN_EPS`（14 个端点）重写为 `/v1/<ep>`；反代前缀优先不重写

### 3.2 转发管线（`gateway/auth.py` → `services/forward.py`）

Bearer 鉴权 → IP 白名单 → 额度（周期重置）→ key RPS → 全局 RPS → `resolve_model`（`auto` → `__auto__` 哨兵行；别名；**key 模型白名单**）→ `handle_chat`：

1. **auto 分支**：`_match_auto_rule`（最后一条 user 消息匹配 `auto_rules` 关键词，命中→`_resolve(规则模型)`→`_run_channels`）→ 失败/未命中进入 `_pick_auto` 循环（按渠道 `_success_rate` 降序，排除熔断/冷却/并发满/付费(`auto_exclude_paid`)/模型级冷却/黑名单，最多 3 次，`exclude_up` 累积）
2. **原始模型**：`_run_channels`（`pick_channels` 渠道级选择：专属路由组→routing_rules→全局策略排序；过滤模型白黑名单/模型级冷却/熔断/冷却/并发；发上游用**真实 upstream_model**）
3. **降级链**（`model_fallback=1`）：`_fallback_models` 按 `models.sort_order, id` 顺序取前 3 备选 → auto 兜底（`auto_enabled`）
4. 成功响应带 `X-Gateway-Fallback` / `X-Gateway-Auto-Rule`（**值必须 percent-encode**，见 §8 坑）

### 3.3 故障隔离三层

| 层 | 触发 | 效果 | 位置 |
|---|---|---|---|
| 渠道级冷却 | 网络错/非模型级 4xx5xx | 冷却渠道 `cooldown_sec`（默认 60s） | forward `_mark_failure` |
| 模型级冷却 | 400/404/422 且文本命中 `_MODEL_ERR_PAT`（"service info not found"/"model_not_found"/"当前模型不可用" 等） | 只冷却 `(channel_id, upstream_model)` 60s | forward `_is_model_level_error` + state `mark_model_fail`；upstream `pick_channels` 与 `_pick_auto` 跳过 |
| 检测联动 | 健康检测确认不可用（404→600s；400/422/2xx+错误特征→300s） | 同上 | health `_mark_model_cool` |

### 3.4 上游 URL 智能拼接（`upstream.upstream_url` + `_VER_SEG = r"/v\d+(?:/|$)"`）

openai 协议 base_url 不含版本段才补 `/v1`；`base.endswith("/v1") and path.startswith("/v1/")` 防双拼。前端保存渠道也有同款正则补 `/v1`（`Channels.vue saveForm`）。

## 4. 数据库（data/gateway.db，10 张表）

`settings`、`channels`、`models`、`api_keys`、`logs`、`routing_rules`、`proxy_rules`、`model_blacklist`、`auto_rules`（v20：keyword/model_name/priority/enabled）、`sqlite_sequence`。

- `models.sort_order`（v20）：0=未排序（按 id）；reorder API 会全列表重编号 1..n；`get_models_snapshot` `ORDER BY sort_order, id`——**该顺序同时是模型监控页显示顺序、备选降级顺序、auto 健康度挑选顺序**
- `channels.paid`（v20）：付费标记，`_pick_auto` 按 `auto_exclude_paid` 排除
- 关键设置键（`DEFAULT_SETTINGS` 权威清单在 `core/config.py`）：`port/admin_port/routing_strategy/model_fallback/auto_enabled/auto_exclude_paid/health_interval_sec/frp_config/frp_autostart...`
- **开源版不带 db**：首次启动 `init_db()` 自动建表；`main.py _startup` 检测 `api_keys` 为空自动生成默认密钥并打印（开源开箱体验，勿删）

## 5. start.sh（管理脚本）

子命令 `start|foreground|stop|restart|status|logs [N]|logs follow|help`。要点：

- 端口检测用 `fuser`；PID 文件 `data/gateway.pid`（**启动块必须 `cd backend` 与 `nohup ... &` 分行写**——写成 `cd backend && nohup ... &` 会让 `&` 作用于整条 `&&` 链，后台跑的是 bash 包装进程：PID 文件记错、脚本不退出，踩过）
- `PYTHONUNBUFFERED=1` 保证日志即时落盘（默认密钥打印在日志开头，首次用户靠它拿密钥）
- FRP 永不自动写入用户配置：仅检测 `settings.frp_config` 为空时打印引导（模板 `frpc.example.ini`）
- `cmd_stop` 末尾 `fuser -k` 兜底清理残留端口占用（frpc 子进程/半退出），否则 restart 立刻 start 会误报端口占用

## 6. 管理台前端

`frontend/src/views/` 8 页面；改源码必须 `cd frontend && npm install && npm run build`（outDir `../dist`）。v20 相关：

- `ModelMonitor.vue`：auto 卡片（总开关 + 排除付费开关 + 规则路由表格/弹窗）、模型行 ↑↓ 按钮
- `Channels.vue`：表单 `paid` 开关
- `Dashboard.vue`：版本徽标（发版记得改）

## 7. 版本历史摘要

- **v1–v18**：聚合转发、双协议转换、反代、8 页管理台、限流/额度/熔断/冷却、健康检测、日志、Termux 支持、双端口隔离、多格式路径兼容、出站防双拼、模型级故障隔离
- **v19**：auto 虚拟模型（健康度优先，失败换下家最多 3 次）、备选降级链（顺序=模型列表 + auto 兜底 + Fallback 头）、`model_fallback`/`auto_enabled`、健康检测→路由联动冷却
- **v20**：auto 规则路由（`auto_rules` 表 + `_match_auto_rule`，按问题内容选模型）、模型排序 `sort_order`（↑↓ 按钮 + `/models/reorder`）、渠道 `paid` 标记 + `auto_exclude_paid`、**修复 9009 管理台页面被 `_path_compat` 劫持**、`X-Gateway-*` 响应头 percent-encode、start.sh 重写为管理脚本 + FRP 引导化（不自动写配置）+ 首次启动自动建库/密钥

## 8. 已知的坑（每条都真实踩过）

1. **改设置是 `PUT /admin/api/settings`**，不是 POST
2. **HTTP 响应头值只允许 latin-1**：中文关键词放进 `X-Gateway-Auto-Rule` 会抛 `UnicodeEncodeError`（当时被 `contextlib.suppress` 静默吞掉，表象是"头没出现"）→ 统一 `urllib.parse.quote`
3. **AppState 方法必须是类方法**：写成模块级函数导致 `AttributeError` 500
4. **SQLite 打包前** `PRAGMA wal_checkpoint(TRUNCATE)` 再删 `-wal/-shm`；**进程未停时操作 db 会 `database table is locked`**——先停进程（必要时 `fuser -k`）再动库；**`cp` 覆盖 db 主文件前必须确认同目录无残留 `-wal`**——强杀（SIGKILL/fuser -k）网关会留下 `-wal`，只换主文件后下次打开时 WAL 回放会把旧数据盖回来（真实事故：用户库被回放成空库）
5. **`pkill -f` 会匹配自身命令行自杀**：同一命令里含明文模式文本时，`[s]leep` 方括号技巧也救不了（命令行其他部分仍含明文）——用 `fuser -k <port>/tcp` 或分开执行
6. **`cd backend && nohup ... &`**：`&` 作用于整条 `&&` 链 → 后台是 bash 包装进程（PID 错、脚本挂）→ `cd` 与 `&` 必须分行
7. Termux pydantic-core 必须 `termux-setup.sh`（TUR wheel），直接 pip 报 Rust 错
8. 改前端必须重新 build dist；9010 上 `/v1/models` 无密钥返回 401 是正常现象
9. zip 打包先 `cd 项目根`；移库/删库类操作前**先备份**（db 是用户命根子）
10. `resolve_model` 的 auto 哨兵：`{"alias":"auto","upstream_model":"__auto__","channel_id":0,...}`；forward 用 `upstream_model == "__auto__"` 特判

## 9. v21+ 建议方向

1. **auto 语义路由升级**：当前规则是关键词匹配；可加 LLM 意图分类（轻量模型）或向量相似度路由
2. **模型级付费标记**：paid 目前是渠道粒度，可细化到模型粒度
3. **降级链拖拽排序 UI**（现为 ↑↓ 按钮，拖拽体验更好）
4. 渠道自动禁用、告警 webhook 推送、用量报表
5. 密钥白名单与 auto/降级的联动策略可配置化（当前：白名单内才可用 auto/备选）

## 10. 快速回归清单（改完代码必跑）

```bash
bash start.sh restart
curl -o /dev/null -w "%{http_code}\n" http://127.0.0.1:9009/models   # 200（v20 修复项）
curl -o /dev/null -w "%{http_code}\n" http://127.0.0.1:9010/models   # 401
curl -o /dev/null -w "%{http_code}\n" http://127.0.0.1:9010/admin/   # 403
# 业务回归（需配置渠道+密钥）：auto 单选 / 规则命中(看 X-Gateway-Auto-Rule) /
# 指定模型降级(看 X-Gateway-Fallback) / PUT 设置开关即时生效
```
