// AI Gateway v25 - Cloudflare Worker
// FastAPI + Vue3 AI aggregation gateway

addEventListener("fetch", event => {
  event.respondWith(handleRequest(event.request))
})

async function handleRequest(request) {
  const url = new URL(request.url)
  
  // 静态文件处理
  if (url.pathname === "/" || url.pathname.startsWith("/admin/")) {
    return new Response(`
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🤖 AI Gateway v25 - Cloudflare Worker</title>
    <meta name="description" content="AI聚合网关 - FastAPI + Vue3 支持OpenAI/Claude双协议互转">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .container {
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            padding: 40px;
            max-width: 900px;
            width: 90%;
            margin: 20px;
        }
        
        .header {
            text-align: center;
            margin-bottom: 30px;
        }
        
        .title {
            font-size: 2.5rem;
            font-weight: 700;
            color: #2d3748;
            margin-bottom: 10px;
        }
        
        .subtitle {
            font-size: 1.2rem;
            color: #718096;
            margin-bottom: 20px;
        }
        
        .status {
            display: inline-block;
            background: #48bb78;
            color: white;
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 0.9rem;
            font-weight: 600;
        }
        
        .info-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .info-card {
            background: #f7fafc;
            border-radius: 12px;
            padding: 20px;
            border-left: 4px solid #4299e1;
        }
        
        .info-card h3 {
            color: #2d3748;
            margin-bottom: 10px;
            font-size: 1.1rem;
        }
        
        .info-card p {
            color: #4a5568;
            line-height: 1.5;
        }
        
        .feature-list {
            list-style: none;
            margin-bottom: 30px;
        }
        
        .feature-list li {
            padding: 8px 0;
            color: #4a5568;
            display: flex;
            align-items: center;
        }
        
        .feature-list li:before {
            content: "✨";
            margin-right: 10px;
        }
        
        .github-section {
            background: #f8f9fa;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
        }
        
        .github-link {
            display: inline-flex;
            align-items: center;
            background: #24292e;
            color: white;
            padding: 12px 24px;
            border-radius: 8px;
            text-decoration: none;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        
        .github-link:hover {
            background: #1a1e22;
            transform: translateY(-2px);
        }
        
        .github-icon {
            width: 20px;
            height: 20px;
            margin-right: 8px;
        }
        
        .footer {
            text-align: center;
            color: #718096;
            font-size: 0.9rem;
            margin-top: 30px;
        }
        
        .version {
            background: #edf2f7;
            padding: 4px 8px;
            border-radius: 4px;
            font-family: monospace;
            font-size: 0.8rem;
            color: #4a5568;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 class="title">🤖 AI Gateway v25</h1>
            <p class="subtitle">AI聚合网关 - FastAPI + Vue3</p>
            <span class="status">✅ 已部署到 Cloudflare Workers</span>
        </div>
        
        <div class="info-grid">
            <div class="info-card">
                <h3>📋 项目信息</h3>
                <p><strong>版本：</strong><span class="version">v25</span></p>
                <p><strong>技术栈：</strong>FastAPI + Vue3</p>
                <p><strong>部署平台：</strong>Cloudflare Workers</p>
            </div>
            
            <div class="info-card">
                <h3>🚀 核心特性</h3>
                <ul class="feature-list">
                    <li>OpenAI/Claude双协议互转</li>
                    <li>智能路由和故障隔离</li>
                    <li>双端口安全隔离</li>
                    <li>全链路日志和计费</li>
                    <li>Vue3可视化管理台</li>
                </ul>
            </div>
        </div>
        
        <div class="github-section">
            <h3>🔗 GitHub 仓库</h3>
            <a href="https://github.com/openfun-26/ai-gateway-v25" class="github-link" target="_blank">
                <svg class="github-icon" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
                </svg>
                查看源码
            </a>
        </div>
        
        <div class="info-card">
            <h3>📖 使用说明</h3>
            <p><strong>1. 克隆仓库：</strong> <code>git clone https://github.com/openfun-26/ai-gateway-v25.git</code></p>
            <p><strong>2. 安装依赖：</strong> <code>cd backend && pip install -r requirements.txt</code></p>
            <p><strong>3. 启动服务：</strong> <code>bash start.sh</code></p>
            <p><strong>4. 访问管理台：</strong> http://127.0.0.1:9009</p>
            <p><strong>5. API接口：</strong> http://127.0.0.1:9010/v1/chat/completions</p>
        </div>
        
        <div class="footer">
            <p>🌐 本项目已永久托管在 Cloudflare Workers</p>
            <p>💻 由 openfun-26 维护 | 📅 部署时间：2026-10-25</p>
        </div>
    </div>
</body>
</html>
    `, {
      headers: { 
        "Content-Type": "text/html",
        "Cache-Control": "public, max-age=3600",
        "X-Content-Type-Options": "nosniff"
      }
    })
  }
  
  // API请求处理
  if (url.pathname.startsWith("/api/")) {
    return new Response(JSON.stringify({
      error: "API endpoint not available in Cloudflare Worker deployment",
      message: "This is a static demo deployment. For full API functionality, deploy the complete FastAPI backend.",
      github_repo: "https://github.com/openfun-26/ai-gateway-v25",
      deployment_info: {
        platform: "Cloudflare Workers",
        environment: process.env.ENVIRONMENT || "production",
        version: process.env.VERSION || "v25",
        timestamp: new Date().toISOString()
      }
    }), {
      headers: { 
        "Content-Type": "application/json",
        "Cache-Control": "public, max-age=300"
      },
      status: 200
    })
  }
  
  // 404处理
  return new Response(JSON.stringify({
    error: "404 Not Found",
    message: "The requested resource was not found on this server.",
    available_endpoints: ["/", "/admin/", "/api/"]
  }), {
    headers: { "Content-Type": "application/json" },
    status: 404
  })
}
