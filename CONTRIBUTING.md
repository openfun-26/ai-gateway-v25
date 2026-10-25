# 参与贡献 (Contributing)

感谢你对本项目的关注！欢迎通过 Issue 反馈问题、通过 Pull Request 提交代码。

## 开始之前

1. 阅读 [README.md](README.md) 了解项目定位
2. 阅读 [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) 了解架构与扩展指南
3. 阅读 [docs/HANDOFF.md](docs/HANDOFF.md) 了解管线细节与**真实踩坑记录**（强烈建议，能帮你避开大量深坑）

## 开发环境

```bash
# 后端（Python 3.10+）
cd backend
pip install -r requirements.txt
python run.py

# 前端（Node 18+，修改后必须重新构建 dist）
cd frontend
npm install
npm run build
```

## 提交规范

- 一个 PR 聚焦一件事，避免混杂无关改动
- Commit message 使用祈使句，如 `fix: 管理台 /models 页面被路径重写劫持`
- 涉及用户可见行为的改动，请同步更新 [CHANGELOG.md](CHANGELOG.md)

## 改完代码必跑的回归清单

```bash
bash start.sh restart
curl -o /dev/null -w "%{http_code}\n" http://127.0.0.1:9009/models   # 期望 200
curl -o /dev/null -w "%{http_code}\n" http://127.0.0.1:9010/models   # 期望 401（无密钥）
curl -o /dev/null -w "%{http_code}\n" http://127.0.0.1:9010/admin/   # 期望 403（端口隔离）
# 业务回归：auto 单选 / 规则命中（看 X-Gateway-Auto-Rule 头）/
# 指定模型降级（看 X-Gateway-Fallback 头）/ PUT 设置开关即时生效
```

## 架构红线（改代码前必读）

- **双端口隔离不可破坏**：管理路径绝不能在 API 端口响应
- **绝不硬编码任何人的真实 FRP 配置 / 上游密钥**，示例一律用占位符
- 动数据库前先备份；SQLite 打包前 `PRAGMA wal_checkpoint(TRUNCATE)`
- `cd backend && nohup ... &` 这类写法有坑，参考 `start.sh` 现有实现

## 报告 Bug

请附上：启动方式（PC / Termux）、`bash start.sh logs 100` 的输出片段、复现步骤、期望与实际行为。**注意隐去你的上游 API 密钥与 FRP token。**
