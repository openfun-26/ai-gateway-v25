"""协议转换矩阵：OpenAI <-> Anthropic 双向转换（请求 / 响应 / SSE 流式）。"""
import json
import time
import uuid
from typing import Any


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


# ======================================================================
# 请求：OpenAI -> Anthropic
# ======================================================================

def openai_to_anthropic(body: dict) -> dict:
    system_parts: list[str] = []
    messages: list[dict] = []
    tools_out: list[dict] = []

    for msg in body.get("messages", []):
        role = msg.get("role")
        if role == "system":
            c = msg.get("content")
            if isinstance(c, str):
                system_parts.append(c)
            elif isinstance(c, list):
                system_parts.append(" ".join(p.get("text", "") for p in c if isinstance(p, dict)))
            continue

        if role == "tool":
            # OpenAI tool 结果 -> Anthropic user 消息中的 tool_result block
            messages.append({
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": msg.get("tool_call_id", ""),
                             "content": msg.get("content") or ""}],
            })
            continue

        content = msg.get("content")
        blocks: list[dict] = []

        if role == "assistant":
            # 文本部分
            if isinstance(content, str) and content:
                blocks.append({"type": "text", "text": content})
            elif isinstance(content, list):
                for p in content:
                    if isinstance(p, dict) and p.get("type") == "text" and p.get("text"):
                        blocks.append({"type": "text", "text": p["text"]})
            # tool_calls -> tool_use blocks
            for tc in msg.get("tool_calls") or []:
                fn = tc.get("function", {})
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except Exception:
                    args = {}
                blocks.append({"type": "tool_use", "id": tc.get("id") or f"toolu_{uuid.uuid4().hex[:12]}",
                               "name": fn.get("name", ""), "input": args})
        else:
            # user：支持多模态图片（url/base64 -> image block）
            if isinstance(content, str):
                blocks.append({"type": "text", "text": content})
            elif isinstance(content, list):
                for p in content:
                    if not isinstance(p, dict):
                        continue
                    t = p.get("type")
                    if t == "text":
                        blocks.append({"type": "text", "text": p.get("text", "")})
                    elif t == "image_url":
                        url = (p.get("image_url") or {}).get("url", "")
                        if url.startswith("data:"):
                            # data:image/jpeg;base64,....
                            try:
                                meta, b64 = url.split(",", 1)
                                media = meta.split(":")[1].split(";")[0]
                                blocks.append({"type": "image", "source": {"type": "base64",
                                                                            "media_type": media, "data": b64}})
                            except Exception:
                                pass
                        # 非 data url 图片跳过（尽力映射）

        if blocks:
            messages.append({"role": "assistant" if role == "assistant" else "user", "content": blocks})

    for t in body.get("tools") or []:
        fn = t.get("function") or {}
        if fn.get("name"):
            tools_out.append({"name": fn["name"], "description": fn.get("description", ""),
                              "input_schema": fn.get("parameters") or {"type": "object", "properties": {}}})

    stop = body.get("stop")
    if isinstance(stop, str):
        stop = [stop]

    out: dict[str, Any] = {
        "model": body.get("model", ""),
        "messages": messages,
        "max_tokens": int(body.get("max_tokens") or body.get("max_completion_tokens") or 4096),
    }
    if system_parts:
        out["system"] = "\n".join(system_parts)
    if body.get("temperature") is not None:
        out["temperature"] = body["temperature"]
    if body.get("top_p") is not None:
        out["top_p"] = body["top_p"]
    if stop:
        out["stop_sequences"] = stop
    if tools_out:
        out["tools"] = tools_out
    if body.get("stream"):
        out["stream"] = True
    return out


# ======================================================================
# 请求：Anthropic -> OpenAI
# ======================================================================

def anthropic_to_openai(body: dict) -> dict:
    messages: list[dict] = []
    tools_out: list[dict] = []

    sys = body.get("system")
    if sys:
        if isinstance(sys, list):
            sys_text = " ".join(p.get("text", "") for p in sys if isinstance(p, dict))
        else:
            sys_text = sys
        if sys_text:
            messages.append({"role": "system", "content": sys_text})

    for msg in body.get("messages", []):
        role = msg.get("role", "user")
        content = msg.get("content")
        oai_content: Any = ""
        tool_calls: list[dict] = []

        if isinstance(content, str):
            oai_content = content
        elif isinstance(content, list):
            texts = []
            for p in content:
                if not isinstance(p, dict):
                    continue
                t = p.get("type")
                if t == "text":
                    texts.append(p.get("text", ""))
                elif t == "image":
                    src = p.get("source") or {}
                    if src.get("type") == "base64":
                        texts.append("[图片内容已省略]")  # OpenAI 上游尽力映射
                elif t == "tool_use":
                    tool_calls.append({
                        "id": p.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                        "type": "function",
                        "function": {"name": p.get("name", ""),
                                     "arguments": json.dumps(p.get("input") or {}, ensure_ascii=False)},
                    })
                elif t == "tool_result":
                    rc = p.get("content")
                    if isinstance(rc, list):
                        rc = " ".join(x.get("text", "") for x in rc if isinstance(x, dict))
                    messages.append({"role": "tool", "tool_call_id": p.get("tool_use_id", ""),
                                     "content": rc if isinstance(rc, str) else json.dumps(rc or "", ensure_ascii=False)})
            oai_content = "\n".join(texts)

        m: dict[str, Any] = {"role": "assistant" if role == "assistant" else "user", "content": oai_content}
        if tool_calls:
            m["tool_calls"] = tool_calls
            if not oai_content:
                m["content"] = None
        messages.append(m)

    for t in body.get("tools") or []:
        if t.get("name"):
            tools_out.append({"type": "function", "function": {
                "name": t["name"], "description": t.get("description", ""),
                "parameters": t.get("input_schema") or {"type": "object", "properties": {}}}})

    out: dict[str, Any] = {
        "model": body.get("model", ""),
        "messages": messages,
        "max_tokens": int(body.get("max_tokens") or 4096),
    }
    if body.get("temperature") is not None:
        out["temperature"] = body["temperature"]
    if body.get("top_p") is not None:
        out["top_p"] = body["top_p"]
    if body.get("stop_sequences"):
        out["stop"] = body["stop_sequences"]
    if tools_out:
        out["tools"] = tools_out
    if body.get("stream"):
        out["stream"] = True
    return out


# ======================================================================
# 响应：Anthropic -> OpenAI（非流式）
# ======================================================================

def anthropic_resp_to_openai(resp: dict, request_model: str) -> dict:
    content_blocks = resp.get("content") or []
    texts, tool_calls = [], []
    for b in content_blocks:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "text":
            texts.append(b.get("text", ""))
        elif b.get("type") == "tool_use":
            tool_calls.append({
                "id": b.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                "type": "function",
                "function": {"name": b.get("name", ""),
                             "arguments": json.dumps(b.get("input") or {}, ensure_ascii=False)},
            })
    msg: dict[str, Any] = {"role": "assistant", "content": "".join(texts) or None}
    if tool_calls:
        msg["tool_calls"] = tool_calls
        msg["content"] = "".join(texts) or None

    stop = resp.get("stop_reason")
    finish = {"end_turn": "stop", "stop_sequence": "stop", "max_tokens": "length",
              "tool_use": "tool_calls"}.get(stop, "stop")
    usage = resp.get("usage") or {}
    return {
        "id": "chatcmpl-" + (resp.get("id") or uuid.uuid4().hex),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request_model,
        "choices": [{"index": 0, "message": msg, "finish_reason": finish}],
        "usage": {
            "prompt_tokens": usage.get("input_tokens", 0),
            "completion_tokens": usage.get("output_tokens", 0),
            "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
        },
    }


# ======================================================================
# 响应：OpenAI -> Anthropic（非流式）
# ======================================================================

def openai_resp_to_anthropic(resp: dict, request_model: str) -> dict:
    choices = resp.get("choices") or [{}]
    ch = choices[0]
    msg = ch.get("message") or {}
    content: list[dict] = []
    text = msg.get("content")
    if isinstance(text, list):
        text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
    if text:
        content.append({"type": "text", "text": text})
    if not content:
        content.append({"type": "text", "text": ""})
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function", {})
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except Exception:
            args = {}
        content.append({"type": "tool_use", "id": tc.get("id") or f"toolu_{uuid.uuid4().hex[:12]}",
                        "name": fn.get("name", ""), "input": args})

    fr = ch.get("finish_reason")
    stop = {"stop": "end_turn", "length": "max_tokens", "tool_calls": "tool_use"}.get(fr, "end_turn")
    u = resp.get("usage") or {}
    return {
        "id": "msg_" + uuid.uuid4().hex[:24],
        "type": "message",
        "role": "assistant",
        "model": request_model,
        "content": content,
        "stop_reason": stop,
        "stop_sequence": None,
        "usage": {"input_tokens": u.get("prompt_tokens", 0), "output_tokens": u.get("completion_tokens", 0)},
    }


# ======================================================================
# SSE 流式转换：Anthropic 上游事件 -> OpenAI chunk
# ======================================================================

class AnthropicToOpenAIStream:
    """把 anthropic SSE 事件流转换为 OpenAI chat.completion.chunk 序列。"""

    def __init__(self, request_model: str):
        self.model = request_model
        self.id = "chatcmpl-" + uuid.uuid4().hex
        self.created = int(time.time())
        self.input_tokens = 0
        self.output_tokens = 0
        self.started = False
        self.finished = False
        self.tool_name = ""
        self.tool_id = ""
        self.tool_args = ""

    def _chunk(self, delta: dict, finish: str | None = None) -> str:
        data = {
            "id": self.id, "object": "chat.completion.chunk", "created": self.created,
            "model": self.model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
        }
        return "data: " + json.dumps(data, ensure_ascii=False) + "\n\n"

    def feed(self, event: str, data: dict) -> list[str]:
        out: list[str] = []
        if event == "message_start":
            u = (data.get("message") or {}).get("usage") or {}
            self.input_tokens = u.get("input_tokens", 0)
            out.append(self._chunk({"role": "assistant", "content": ""}))
            self.started = True
        elif event == "content_block_start":
            b = data.get("content_block") or {}
            if b.get("type") == "tool_use":
                self.tool_id = b.get("id") or f"call_{uuid.uuid4().hex[:12]}"
                self.tool_name = b.get("name", "")
                self.tool_args = ""
        elif event == "content_block_delta":
            d = data.get("delta") or {}
            if d.get("type") == "text_delta":
                out.append(self._chunk({"content": d.get("text", "")}))
            elif d.get("type") == "input_json_delta":
                self.tool_args += d.get("partial_json", "")
        elif event == "content_block_stop":
            if self.tool_name:
                out.append(self._chunk({"tool_calls": [{"index": 0, "id": self.tool_id, "type": "function",
                                                        "function": {"name": self.tool_name, "arguments": self.tool_args}}]}))
                self.tool_name = ""
        elif event == "message_delta":
            d = data.get("delta") or {}
            u = data.get("usage") or {}
            self.output_tokens = u.get("output_tokens", self.output_tokens)
            if not self.finished:
                finish = {"end_turn": "stop", "max_tokens": "length", "stop_sequence": "stop",
                          "tool_use": "tool_calls"}.get(d.get("stop_reason") or "", "stop")
                out.append(self._chunk({}, finish))
                self.finished = True
        elif event == "message_stop":
            if not self.finished:
                out.append(self._chunk({}, "stop"))
                self.finished = True
            out.append("data: [DONE]\n\n")
        elif event == "error":
            err = data.get("error") or {}
            out.append("data: " + json.dumps({"error": err}, ensure_ascii=False) + "\n\n")
            out.append("data: [DONE]\n\n")
        return out

    @property
    def usage_tuple(self) -> tuple[int, int]:
        return self.input_tokens, self.output_tokens or _estimate_tokens("")


# ======================================================================
# SSE 流式转换：OpenAI chunk -> Anthropic 事件
# ======================================================================

class OpenAIToAnthropicStream:
    """把 openai SSE chunk 流转换为 anthropic 事件序列。"""

    def __init__(self, request_model: str):
        self.model = request_model
        self.msg_id = "msg_" + uuid.uuid4().hex[:24]
        self.started = False
        self.block_open = False
        self.block_idx = 0
        self.output_tokens = 0
        self.input_tokens = 0
        self.finished = False
        # tool 状态
        self.tool_index = {}   # openai tool index -> (anthropic block_idx, name, id)

    def _event(self, name: str, data: dict) -> str:
        return f"event: {name}\ndata: " + json.dumps(data, ensure_ascii=False) + "\n\n"

    def _start_message(self):
        self.started = True
        return self._event("message_start", {
            "type": "message_start",
            "message": {"id": self.msg_id, "type": "message", "role": "assistant",
                        "model": self.model, "content": [], "stop_reason": None, "stop_sequence": None,
                        "usage": {"input_tokens": self.input_tokens, "output_tokens": 0}},
        })

    def feed(self, chunk: dict) -> list[str]:
        out: list[str] = []
        if not self.started:
            out.append(self._start_message())
        choices = chunk.get("choices") or []
        if not choices:
            u = chunk.get("usage")
            if u:
                self.input_tokens = u.get("prompt_tokens", self.input_tokens)
                self.output_tokens = u.get("completion_tokens", self.output_tokens)
            return out
        c = choices[0]
        delta = c.get("delta") or {}

        text = delta.get("content")
        if isinstance(text, list):  # 多模态数组
            text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
        if text:
            if not self.block_open:
                out.append(self._event("content_block_start", {
                    "type": "content_block_start", "index": self.block_idx,
                    "content_block": {"type": "text", "text": ""}}))
                self.block_open = True
            out.append(self._event("content_block_delta", {
                "type": "content_block_delta", "index": self.block_idx,
                "delta": {"type": "text_delta", "text": text}}))

        for tc in delta.get("tool_calls") or []:
            idx = tc.get("index", 0)
            if idx not in self.tool_index:
                if self.block_open:
                    out.append(self._event("content_block_stop", {"type": "content_block_stop", "index": self.block_idx}))
                    self.block_open = False
                    self.block_idx += 1
                fn = tc.get("function") or {}
                self.tool_index[idx] = (self.block_idx, fn.get("name", ""), tc.get("id") or f"toolu_{uuid.uuid4().hex[:12]}")
                out.append(self._event("content_block_start", {
                    "type": "content_block_start", "index": self.block_idx,
                    "content_block": {"type": "tool_use", "id": self.tool_index[idx][2],
                                      "name": self.tool_index[idx][1], "input": {}}}))
            if (tc.get("function") or {}).get("arguments"):
                out.append(self._event("content_block_delta", {
                    "type": "content_block_delta", "index": self.tool_index[idx][0],
                    "delta": {"type": "input_json_delta", "partial_json": tc["function"]["arguments"]}}))

        u = chunk.get("usage")
        if u:
            self.input_tokens = u.get("prompt_tokens", self.input_tokens)
            self.output_tokens = u.get("completion_tokens", self.output_tokens)

        if c.get("finish_reason") and not self.finished:
            self.finished = True
            if self.block_open:
                out.append(self._event("content_block_stop", {"type": "content_block_stop", "index": self.block_idx}))
                self.block_open = False
            fr = c.get("finish_reason")
            stop = {"stop": "end_turn", "length": "max_tokens", "tool_calls": "tool_use"}.get(fr, "end_turn")
            out.append(self._event("message_delta", {
                "type": "message_delta",
                "delta": {"stop_reason": stop, "stop_sequence": None},
                "usage": {"output_tokens": self.output_tokens}}))
        return out

    def close(self) -> list[str]:
        out: list[str] = []
        if not self.started:
            out.append(self._start_message())
        if self.block_open:
            out.append(self._event("content_block_stop", {"type": "content_block_stop", "index": self.block_idx}))
            self.block_open = False
        if not self.finished:
            out.append(self._event("message_delta", {
                "type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                "usage": {"output_tokens": self.output_tokens}}))
        out.append(self._event("message_stop", {"type": "message_stop"}))
        return out

    @property
    def usage_tuple(self) -> tuple[int, int]:
        return self.input_tokens, self.output_tokens or 1
