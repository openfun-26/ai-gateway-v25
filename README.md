# AI 聚合网关（AI Aggregation Gateway）

<p align="center">
  <b>单进程 · 双端口隔离 · 多协议聚合 · auto 智能路由</b><br>
  FastAPI + Vue3 · 零外部依赖（无 Docker / Redis / MySQL）· PC 与 Android(Termux) 通用
</p>

---

一个把多家 AI 上游聚合为统一 OpenAI 兼容接口的自托管网关：**OpenAI / Claude 双协议互转**、**OpenAI 透传反代**、**auto 虚拟模型智能路由（按问题内容选模型 + 健康度兜底）**、**备选模型降级链（顺序由你制定）**、**渠道/模型级故障隔离**、**全链路日志与计费**，并内置 Vue3 可视化管理台。

## ✨ 特性

- **双端口安全隔离**：API（默认 9010）可穿透公网；管理台（默认 9009）仅内网访问，9010 上访问管理路径一律 403
- **auto 智能路由**：`model: "auto"` 即可使用——支持按问题内容配置「关键词 → 模型」规则，未命中按渠道健康度挑选；失败自动换下一个（防单点）
- **备选降级链**：指定模型失败后按你在模型监控页排好的顺序（↑↓ 可调）逐个降级，备选全挂 auto 兜底；响应头 `X-Gateway-Fallback` 透明告知
- **付费渠道保护**：渠道可标记「付费」，auto 挑选默认排除，防止误触付费模型产生费用
- **模型级故障隔离**：某 (渠道, 模型) 不可用只冷却该组合 60s，不拖累同渠道其他模型；健康检测结果自动联动路由
- **多格式路径兼容**：客户端拼错路径（如 `/v4/v1/chat/completions`）自动修正；上游 base_url 已含版本段不重复拼接
- **全链路可观测**：请求/错误日志、payload 留痕、渠道成功率/延迟 EMA、今日统计、模型健康检测（真实 chat 探测）
- **密钥与额度**：sk-gw- 客户端密钥、四项额度 + 日/月周期重置、key 级 RPS、模型/IP 白黑名单
- **FRP 内网穿透**：管理台内置 frpc 管理（配置/启停/日志），配置自己填，绝不替你做主
- **一键脚本**：`bash start.sh` 自动装依赖/建库/生成默认密钥，支持 `start|stop|restart|status|logs`

## 🏗 架构一览

```
客户端(ChatBox/SDK/curl)                     外网
        │  sk-gw-xxx                          │
        ▼                                     ▼
┌─────────────────────── FRP(可选) ───────────────────────┐
│  :9010  API 端口（对外）                                  │
│    /v1/chat/completions · /v1/models · /v1/embeddings    │
│    /anthropic/v1/messages · 反代规则                      │
│    ┌──────────── 管理路径 403 拒绝（安全隔离）────────┐    │
│    ▼                                                 │    │
│  FastAPI 单进程（asyncio 双 uvicorn Server）            │    │
│    鉴权→额度→限流→路径兼容→模型解析→auto/降级→协议转换     │    │
│    →渠道选择→熔断/冷却/并发→上游调用→SSE→计费→日志        │    │
│  :9009  管理台端口（仅内网）                              │    │
│    Vue3 管理界面 + /admin/api/*                         │    │
└──────────────────┬───────────────────────────────────┘    │
                   ▼                                        │
        SQLite(WAL) data/gateway.db                          │
        上游: OpenAI兼容渠道 / Claude渠道 / 透传反代            │
└──────────────────────────────────────────────────────────┘
```

## 🚀 快速开始

### PC（Linux / macOS / Windows-WSL）

```bash
pip install -r backend/requirements.txt
bash start.sh                # 首次启动自动建库并生成默认密钥
bash start.sh logs 30        # 查看默认密钥 sk-gw-xxxx
```

### Termux（Android）

```bash
pkg update && pkg install python
bash termux-setup.sh         # 一键修复 pydantic-core（免 Rust 编译）
bash start.sh foreground     # 前台运行防杀
```

### 第一次使用

1. 浏览器打开管理台 `http://127.0.0.1:9009`
2. 「上游渠道」添加你的 AI 渠道（OpenAI 兼容 base_url + key，或 Claude 协议）
3. 「模型监控」拉取/添加模型，点 ↑↓ 安排降级顺序，按需开启 auto 规则
4. 「客户端密钥」生成 `sk-gw-xxx`
5. 客户端即可调用：

```bash
curl http://127.0.0.1:9010/v1/chat/completions \
  -H "Authorization: Bearer sk-gw-你的密钥" \
  -H "Content-Type: application/json" \
  -d '{"model":"auto","messages":[{"role":"user","content":"你好"}]}'
```

> 需要 FRP 内网穿透？模板见 [`frpc.example.ini`](frpc.example.ini)，把内容粘贴到管理台「FRP 内网穿透」页修改保存即可。

## 📚 文档

| 文档 | 内容 |
|---|---|
| [docs/USER_GUIDE.md](docs/USER_GUIDE.md) | 使用文档：部署、8 个管理页面、auto/降级/付费保护实操、FAQ |
| [docs/API.md](docs/API.md) | 接口文档：网关 API 与管理 API 全量参考 |
| [docs/INTEGRATION.md](docs/INTEGRATION.md) | 对接文档：OpenAI SDK / ChatBox 等客户端接入指南 |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | 开发文档：架构、代码导读、扩展指南 |
| [docs/HANDOFF.md](docs/HANDOFF.md) | 项目交接文档：给下一位维护者/AI 的完整技术移交 |
| [CHANGELOG.md](CHANGELOG.md) | 版本历史 |

## 🔐 安全须知

- 管理台端口（9009）**仅供内网**，切勿穿透；对外只暴露 API 端口（9010）
- 上游 API Key 在管理台中脱敏展示（`sk-***abcd`），请勿把 `data/gateway.db` 提交到公开仓库（.gitignore 已排除）
- FRP token 属敏感信息，提交前请确认未写死在任何文件中

## 🤝 贡献

欢迎 Issue / PR，见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 📄 许可证

[MIT License](LICENSE)
