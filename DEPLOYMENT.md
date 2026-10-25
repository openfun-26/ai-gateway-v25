# AI Gateway v25 - 完整部署指南

## 🚀 快速开始

### 方法一：自动部署（推荐）
```bash
# 1. 运行获取Token脚本
./get-cloudflare-token.sh

# 2. 按照提示设置GitHub Secret
# 3. 运行自动部署脚本
./auto-deploy.sh
```

### 方法二：手动部署
```bash
# 1. 安装依赖
npm install -g wrangler

# 2. 登录Cloudflare
wrangler login

# 3. 设置环境变量
export CLOUDFLARE_API_TOKEN="your-token-here"

# 4. 部署
cd cloudflare-worker
wrangler deploy --env production
```

## 📋 详细步骤

### 步骤1：获取Cloudflare API Token

1. **访问Cloudflare Dashboard**
   - 登录：https://dash.cloudflare.com/profile/api-tokens

2. **创建Token**
   - 点击 "Create Token"
   - 选择 "Edit zone DNS" 模板
   - 配置权限：
     - Zone Resources: "Specific Zone" 或 "All Zones"
     - Permissions: "Zone:DNS:Edit"

3. **获取Zone ID**
   - 登录Cloudflare Dashboard
   - 选择你的域名
   - 右下角显示 "Zone ID"

4. **完成Token创建**
   - 点击 "Continue" → "Create Token"
   - 复制生成的Token

### 步骤2：设置GitHub Secret

1. **访问GitHub仓库设置**
   - https://github.com/openfun-26/ai-gateway-v25/settings/secrets/actions

2. **添加Secret**
   - 点击 "New repository secret"
   - Name: `CLOUDFLARE_API_TOKEN`
   - Value: [粘贴你的Token]
   - 点击 "Add secret"

### 步骤3：触发自动部署

1. **GitHub Actions会自动运行**
   - 每次push到main分支都会触发
   - 可以在Actions页面查看状态

2. **手动触发**
   - 访问：https://github.com/openfun-26/ai-gateway-v25/actions
   - 点击 "Run workflow"

## 🔗 访问地址

- **GitHub仓库**：https://github.com/openfun-26/ai-gateway-v25
- **Cloudflare Worker**：https://ai-gateway-v25.workers.dev
- **管理台**：https://ai-gateway-v25.workers.dev（静态演示）

## ⚠️ 注意事项

1. **Token安全**
   - 不要将Token提交到代码仓库
   - 使用GitHub Secrets管理
   - 定期轮换Token

2. **域名配置**
   - 如果使用自定义域名，需要在Cloudflare配置CNAME记录
   - Workers域名：`ai-gateway-v25.your-domain.com`

3. **免费额度**
   - Cloudflare Workers免费版：10万请求/天
   - 超出需要付费

## 🛠️ 故障排除

### 常见问题

1. **部署失败**
   ```bash
   # 检查Token是否正确
   wrangler whoami
   
   # 查看详细日志
   wrangler deploy --env production --verbose
   ```

2. **访问404**
   - 确保Worker配置正确
   - 检查路由配置

3. **权限错误**
   - 确保Token有Zone:DNS:Edit权限
   - 检查Zone ID是否正确

### 获取帮助

- **GitHub Issues**：https://github.com/openfun-26/ai-gateway-v25/issues
- **Cloudflare文档**：https://developers.cloudflare.com/workers/

---

✅ **恭喜！按照以上步骤完成部署后，你的AI Gateway v25将永久托管在Cloudflare Workers上！**
