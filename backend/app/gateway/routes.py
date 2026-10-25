"""对外网关端点：/v1/chat/completions、/v1/models、/v1/embeddings、/anthropic/v1/messages。"""
from fastapi import APIRouter, Request

from ..gateway.auth import authenticate
from ..services import forward

router = APIRouter()

# main.py 中将 authenticate 注入 app.state，供 forward 服务调用


@router.post("/v1/chat/completions")
async def openai_chat(request: Request):
    from ..gateway.auth import _err
    try:
        body = await request.json()
    except Exception:
        return _err(400, "invalid_request_error", "请求体必须是 JSON", False)
    if not isinstance(body, dict) or not body.get("model"):
        return _err(400, "invalid_request_error", "缺少 model 字段", False)
    return await forward.handle_chat(request, body, anthropic=False)


@router.get("/v1/models")
async def openai_models(request: Request):
    return await forward.handle_models(request)


@router.post("/v1/embeddings")
async def openai_embeddings(request: Request):
    from ..gateway.auth import _err
    try:
        body = await request.json()
    except Exception:
        return _err(400, "invalid_request_error", "请求体必须是 JSON", False)
    if not isinstance(body, dict):
        return _err(400, "invalid_request_error", "请求体必须是 JSON", False)
    return await forward.handle_embeddings(request, body)


@router.post("/anthropic/v1/messages")
async def anthropic_messages(request: Request):
    from ..gateway.auth import _err
    try:
        body = await request.json()
    except Exception:
        return _err(400, "invalid_request_error", "请求体必须是 JSON", True)
    if not isinstance(body, dict) or not body.get("model"):
        return _err(400, "invalid_request_error", "缺少 model 字段", True)
    return await forward.handle_chat(request, body, anthropic=True)
