"""OpenAI 透传反代：catch-all 匹配 proxy_rules 前缀 -> 透传上游（强制日志）。"""
import json
import time

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse, Response as FResponse

from ..core.config import GATEWAY_RESERVED, now_local_str
from ..core.state import state
from ..db import repo
from ..gateway.auth import _client_ip


def _extract_tokens_from_json(data) -> tuple[int, int]:
    if isinstance(data, dict):
        u = data.get("usage") or {}
        pt = u.get("prompt_tokens") or u.get("input_tokens") or 0
        ct = u.get("completion_tokens") or u.get("output_tokens") or 0
        return int(pt or 0), int(ct or 0)
    return 0, 0


def _estimate(text_len: int) -> int:
    return max(1, text_len // 4) if text_len else 0


async def handle_proxy(request: Request) -> FResponse:
    """在网关保留端点之后、静态托管之前调用。未命中返回 None。"""
    rules = [r for r in await repo.list_proxy_rules(enabled_only=True)]
    if not rules:
        return None
    path = request.url.path
    if path in GATEWAY_RESERVED or path.startswith("/admin") or path.startswith("/anthropic"):
        return None
    # 最长前缀匹配
    rules.sort(key=lambda r: len(r.get("path_prefix") or ""), reverse=True)
    rule = next((r for r in rules if r.get("path_prefix") and path.startswith(r["path_prefix"])), None)
    if not rule:
        return None

    rest = path[len(rule["path_prefix"]):]
    target_base = (rule.get("target_url") or "").rstrip("/")
    url = target_base + ("/" + rest.lstrip("/") if rest else "")
    if request.url.query:
        url += "?" + request.url.query

    headers = {k: v for k, v in request.headers.items()
               if k.lower() not in ("host", "content-length", "connection", "transfer-encoding",
                                    "accept-encoding")}
    if rule.get("api_key"):
        headers["Authorization"] = f"Bearer {rule['api_key']}"

    body_bytes = await request.body()
    start = time.monotonic()
    ip = _client_ip(request)
    is_stream = b'"stream": true' in body_bytes or b'"stream":true' in body_bytes

    try:
        client = httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(120.0, connect=15.0))
        req = client.build_request(request.method, url, headers=headers,
                                   content=body_bytes if body_bytes else None,
                                   params=None)
        resp = await client.send(req, stream=True)
    except httpx.HTTPError as e:
        await repo.insert_log({"request_type": "proxy", "protocol": "openai", "key_name": "",
                               "model": "", "vendor_tag": rule.get("vendor_tag", ""), "source_ip": ip,
                               "channel": rule.get("name", "proxy"), "http_status": 502,
                               "status": "failure", "error": f"反代连接失败: {type(e).__name__}",
                               "request_payload": body_bytes.decode("utf-8", "ignore")[:4000]})
        return JSONResponse({"error": {"message": f"Proxy upstream error: {type(e).__name__}",
                                       "type": "api_error", "code": "bad_gateway"}}, status_code=502)

    status = resp.status_code
    latency_ms = int((time.monotonic() - start) * 1000)
    resp_headers = {k: v for k, v in resp.headers.items()
                    if k.lower() not in ("content-length", "transfer-encoding", "content-encoding",
                                         "connection", "keep-alive")}

    content_type = resp.headers.get("content-type", "")

    if "text/event-stream" in content_type or is_stream:
        # 流式透传 + 估算 token
        acc = {"chars": 0, "pt": 0, "ct": 0}
        status_holder = {"logged": False}

        async def gen():
            status_holder["logged"] = True
            try:
                buf = []
                async for line in resp.aiter_lines():
                    if line.startswith("data:"):
                        d = line[5:].strip()
                        if d and d != "[DONE]":
                            try:
                                obj = json.loads(d)
                                ch0 = (obj.get("choices") or [{}])[0]
                                acc["chars"] += len((ch0.get("delta") or {}).get("content") or "")
                                u = obj.get("usage")
                                if u:
                                    acc["pt"] = u.get("prompt_tokens", acc["pt"]) or acc["pt"]
                                    acc["ct"] = u.get("completion_tokens", acc["ct"]) or acc["ct"]
                            except Exception:
                                pass
                    yield line + "\n"
            except Exception:
                pass
            finally:
                await resp.aclose()
                await client.aclose()
                total = int((time.monotonic() - start) * 1000)
                pt = acc["pt"] or _estimate(acc["chars"])
                ct = acc["ct"] or _estimate(acc["chars"])
                try:
                    await repo.insert_log({"request_type": "proxy", "protocol": "openai",
                                           "key_name": "", "model": "", "vendor_tag": rule.get("vendor_tag", ""),
                                           "source_ip": ip, "channel": rule.get("name", "proxy"),
                                           "latency_ms": total, "prompt_tokens": pt, "completion_tokens": ct,
                                           "http_status": status, "status": "success" if status < 400 else "failure",
                                           "error": "" if status < 400 else f"HTTP {status}",
                                           "request_payload": body_bytes.decode("utf-8", "ignore")[:4000]})
                except Exception:
                    pass

        return StreamingResponse(gen(), status_code=status, media_type="text/event-stream",
                                 headers=resp_headers)

    # 非流式
    raw = await resp.aread()
    await resp.aclose()
    await client.aclose()
    total = int((time.monotonic() - start) * 1000)
    pt, ct = 0, 0
    try:
        if "json" in content_type:
            data = json.loads(raw)
            pt, ct = _extract_tokens_from_json(data)
            body_for_log = json.dumps(data, ensure_ascii=False)[:8000]
        else:
            body_for_log = raw.decode("utf-8", "ignore")[:2000]
    except Exception:
        body_for_log = raw.decode("utf-8", "ignore")[:2000]

    try:
        await repo.insert_log({"request_type": "proxy", "protocol": "openai", "key_name": "",
                               "model": "", "vendor_tag": rule.get("vendor_tag", ""), "source_ip": ip,
                               "channel": rule.get("name", "proxy"), "latency_ms": total,
                               "prompt_tokens": pt, "completion_tokens": ct, "http_status": status,
                               "status": "success" if status < 400 else "failure",
                               "error": "" if status < 400 else f"HTTP {status}",
                               "request_payload": body_bytes.decode("utf-8", "ignore")[:4000],
                               "response_payload": body_for_log[:4000]})
    except Exception:
        pass

    return FResponse(content=raw, status_code=status, headers=resp_headers,
                     media_type=content_type or None)
