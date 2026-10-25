// AI Gateway Cloudflare Worker
// FastAPI + Vue3 AI aggregation gateway

addEventListener(fetch, event => {
  event.respondWith(handleRequest(event.request))
})

async function handleRequest(request) {
  const url = new URL(request.url)
  
  // 静态文件处理
  if (url.pathname === / || url.pathname.startsWith(/admin/)) {
    return new Response(`
<!DOCTYPE html>
<html>
<head>
    <title>AI Gateway - Cloudflare Worker</title>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
        .container { background: #f5f5f5; padding: 30px; border-radius: 10px; }
        h1 { color: #333; }
        .info { background: #e3f2fd; padding: 15px; border-radius: 5px; margin: 20px 0; }
        .warning { background: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0; }
        .code { background: #f8f9fa; padding: 15px; border-radius: 5px; font-family: monospace; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🤖 AI Gateway v25</h1>
        <div class="info">
            <h3>📋 项目信息</h3>
            <p><strong>版本：</strong>v25</p>
            <p><strong>技术栈：</strong>FastAPI + Vue3</p>
            <p><strong>功能：</strong>AI聚合网关，支持OpenAI/Claude双协议互转、智能路由、故障隔离</p>
        </div>
        
        <div class="warning">
            <h3>⚠️ 重要提示</h3>
            <p>这是一个Cloudflare Worker部署版本，仅用于演示和静态展示。</p>
            <p>完整功能需要部署完整的FastAPI后端，请参考GitHub源码。</p>
        </div>
        
        <div class="code">
            <h3>🔗 GitHub仓库</h3>
            <p>https://github.com/openfun-26/ai-gateway-v25</p>
            <p>包含完整的FastAPI后端、Vue3前端管理台和部署脚本</p>
        </div>
        
        <div class="info">
            <h3>🚀 主要特性</h3>
            <ul>
                <li>双端口安全隔离：API（9010）可穿透公网，管理台（9009）仅内网</li>
                <li>auto智能路由：按问题内容选择模型 + 健康度兜底</li>
                <li>备选降级链：指定模型失败后自动降级</li>
                <li>模型级故障隔离：某(渠道,模型)不可用只冷却该组合</li>
                <li>全链路可观测：请求日志、payload留痕、成功率统计</li>
            </ul>
        </div>
    </div>
</body>
</html>
    `, {
      headers: { Content-Type: text/html }
    })
  }
  
  // API请求转发到GitHub源码说明
  if (url.pathname.startsWith(/api/)) {
    return new Response(JSON.stringify({
      error: "API endpoint not available in Cloudflare Worker deployment",
      message: "This is a static demo deployment. For full API functionality, deploy the complete FastAPI backend.",
      github_repo: "https://github.com/openfun-26/ai-gateway-v25"
    }), {
      headers: { Content-Type: application/json }
    })
  }
  
  // 404处理
  return new Response(404 Not Found, { status: 404 })
}
