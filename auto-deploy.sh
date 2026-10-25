#!/bin/bash
# AI Gateway v25 - 自动化部署脚本

echo "🚀 AI Gateway v25 自动化部署脚本"
echo "=================================="

# 检查wrangler是否安装
if ! command -v wrangler &> /dev/null; then
    echo "📦 安装 wrangler..."
    npm install -g wrangler
fi

# 检查是否已登录Cloudflare
if ! wrangler whoami &> /dev/null; then
    echo "🔐 登录Cloudflare..."
    wrangler login
fi

# 检查Cloudflare API Token
if [ -z "${CLOUDFLARE_API_TOKEN:-}" ]; then
    echo "⚠️  CLOUDFLARE_API_TOKEN 环境变量未设置"
    echo "请在GitHub仓库设置Secrets，然后重新运行此脚本"
    exit 1
fi

# 部署Worker
echo "🌐 部署到Cloudflare Workers..."
cd cloudflare-worker

# 构建Worker
echo "📦 构建Worker..."
wrangler deploy --env production

if [ $? -eq 0 ]; then
    echo "✅ 部署成功！"
    echo "🌐 访问地址：https://ai-gateway-v25.workers.dev"
else
    echo "❌ 部署失败，请检查配置"
    exit 1
fi
