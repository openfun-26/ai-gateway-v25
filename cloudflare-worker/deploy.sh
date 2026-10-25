#!/bin/bash
# AI Gateway v25 - Cloudflare Worker部署脚本

echo "🚀 部署AI Gateway v25到Cloudflare Workers..."

# 检查wrangler是否安装
if ! command -v wrangler &> /dev/null; then
    echo "❌ wrangler未安装，正在安装..."
    npm install -g wrangler
fi

# 登录Cloudflare
echo "🔐 登录Cloudflare..."
wrangler login

# 创建Worker
echo "📦 创建Worker..."
wrangler deploy --env production

echo "✅ 部署完成！"
echo "🌐 访问地址：https://ai-gateway-v25.your-domain.workers.dev"
