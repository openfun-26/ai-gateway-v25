# 更新日志 (Changelog)

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 风格记录版本变更。

## [v20] - 当前版本

### 修复 (Fixed)
- **管理台致命 Bug**：`_path_compat` 中间件此前对双端口同时生效，导致管理台 SPA 页面 `/models` 等路径在管理端口（9009）被错误重写为 API 路径 `/v1/models` 并落入 API 鉴权，页面显示 `Missing API key`。修复为仅在 API 端口执行路径兼容重写。
- **`X-Gateway-*` 响应头编码问题**：HTTP 响应头仅允许 latin-1 字符，中文关键词（如 auto 规则名"翻译"）会触发 `UnicodeEncodeError` 且被静默吞掉。全部 3 处自定义响应头（`X-Gateway-Auto-Rule`、2 处 `X-Gateway-Fallback`）统一改为 `urllib.parse.quote(..., safe='')` 百分号编码。
- **`start.sh` 嵌套后台启动 Bug**：`cd backend && nohup ... &` 中 `&` 作用于整条 `&&` 链，后台实际运行的是 bash 包装进程，导致 PID 文件记录错误、脚本卡死。修复为 `cd` 与 `nohup ... &` 分行执行，启动后回项目根目录。
- **日志缓冲**：启动命令加入 `PYTHONUNBUFFERED=1`，首次启动生成的默认密钥即时可见。

### 新增 (Added)
- **auto 规则路由**：新表 `auto_rules(id, keyword, model_name, priority, enabled)`。`auto` 虚拟模型路由时先按用户提问内容做关键词匹配（大小写不敏感子串），命中即定向到指定模型；未命中或调用失败再回退到健康度优先挑选。响应头 `X-Gateway-Auto-Rule` 可观察命中情况。管理台「模型监控」页提供规则 CRUD 与启停。
- **模型排序**：`models.sort_order` 列 + `POST /admin/api/models/reorder` 全量重排接口 + 管理台 ↑↓ 按钮。该顺序同时决定模型显示顺序、降级链顺序与 auto 健康度挑选顺序。
- **付费渠道标记**：`channels.paid` 列 + 管理台开关 + 新设置 `auto_exclude_paid`（默认开启）。auto 路由默认跳过付费渠道，避免日常闲聊消耗计费额度。
- **首次启动自动初始化**：检测到 `api_keys` 空表时自动生成 `sk-gw-` 前缀默认密钥并在控制台醒目打印，彻底告别"装完不知道密钥是什么"。
- **`start.sh` 重写为完整管理脚本**：`start | foreground | stop | restart | status | logs [N] | logs follow | help` 子命令，彩色输出，支持 env > 数据库 > 默认值 三级端口读取，依赖检查，端口占用检测（`fuser`），stop 兜底清理。
- **FRP 引导化**：脚本仅在 FRP 配置为空时打印引导说明，**绝不自动写入任何配置**；提供 `frpc.example.ini` 模板供用户自填。管理台 FRP 页面粘贴配置即可使用。

## [v19]

### 新增 (Added)
- **auto 虚拟模型**：将 `auto` 设为模型别名后，网关按渠道健康度自动挑选可用模型；调用失败自动换下一家，最多尝试 3 次。
- **备选降级链**：为指定模型配置备选模型（顺序 = 模型列表排序），失败时按链降级并在 `X-Gateway-Fallback` 响应头中标注 `原始模型 -> 实际模型`。
- **路由联动冷却**：健康检测失败后立即将该渠道进入冷却期，路由侧即时感知，无需等周期检测。
- 新设置项：`model_fallback`（降级链总开关）、`auto_enabled`（auto 总开关）。

## [v1 – v18] - 基础能力积累

### Added
- OpenAI 兼容聚合网关：`/v1/chat/completions`、`/v1/models`、`/v1/embeddings` 等多格式路径兼容
- Anthropic Messages 协议双向转换（Claude SDK / OpenAI SDK 互转）
- 渠道反代模式（直接透传指定上游）
- 8 页面 Vue3 管理台（仅管理端口开放，API 端口隔离 403）
- 客户端密钥管理、限流、每日额度、熔断、失败冷却
- 周期健康检测与手动触发
- 请求日志审计与黑名单
- SQLite WAL 模式存储，单文件数据库
- Termux（Android）一键部署脚本 `termux-setup.sh`
- 双端口隔离架构：API 端口（可 FRP 穿透公网）/ 管理端口（仅内网）
- 出站请求防重拼（原样透传 body）、模型级故障隔离
