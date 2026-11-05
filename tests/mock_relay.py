#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地联调用 mock Anthropic 兼容端点：实现 /v1/models、/v1/messages/count_tokens、
/v1/messages（非流式 + SSE 流式 + tools）。
仅供测试 MQ 引擎链路，不代表真实模型行为。

用法:
    python3 tests/mock_relay.py [port]
    MOCK_MODELS="gpt-6-luna,gpt-5.6" python3 tests/mock_relay.py 8920   # 模拟换上游后的目录
    MOCK_MALFORMED=1 python3 tests/mock_relay.py 8921                   # 注入畸形 SSE 行
    MOCK_HTTP=502 python3 tests/mock_relay.py 8922                      # 模拟上游 5xx
"""
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_MODELS = ["claude-haiku-4-5-20251001", "claude-sonnet-4-5-20250929"]


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def models():
    """每次请求都读环境变量，测试可以在同一个进程里切换目录形态。"""
    raw = os.environ.get("MOCK_MODELS", "")
    return [m.strip() for m in raw.split(",") if m.strip()] or DEFAULT_MODELS


def sig_len():
    return _env_int("MOCK_SIG_LEN", 320)


def tool_id():
    return os.environ.get("MOCK_TOOL_ID", "toolu_mock1")


def malformed():
    return os.environ.get("MOCK_MALFORMED", "") == "1"


def forced_status():
    return _env_int("MOCK_HTTP", 0)


def count_tokens_for(text):
    return 20 + len(text) // 6


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj, sse=False):
        if sse:
            self.send_response(code)
            self.send_header("content-type", "text/event-stream")
            self.send_header("transfer-encoding", "chunked")
            self.end_headers()
            for chunk in obj:
                data = chunk.encode()
                self.wfile.write(f"{len(data):X}\r\n".encode() + data + b"\r\n")
                self.wfile.flush()
                time.sleep(0.01)
            self.wfile.write(b"0\r\n\r\n")
        else:
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def do_GET(self):
        if forced_status() >= 500:
            return self._send(forced_status(), {"type": "error",
                                                "error": {"message": "upstream down"}})
        if self.path == "/v1/models":
            self._send(200, {"data": [{"id": m} for m in models()]})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        if forced_status() >= 500:
            n = int(self.headers.get("content-length", 0))
            self.rfile.read(n)
            return self._send(forced_status(), {"type": "error",
                                                "error": {"message": "upstream down"}})
        n = int(self.headers.get("content-length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/v1/messages/count_tokens":
            auth = self.headers.get("x-api-key", "")
            if not auth.startswith("sk-"):
                return self._send(401, {"type": "error", "error": {"message": "bad key"}})
            text = "".join(
                b.get("text", "") for m in (req.get("messages") or [])
                for b in (m.get("content") if isinstance(m.get("content"), list)
                          else [{"text": m.get("content") or ""}])
                if isinstance(b, dict))
            return self._send(200, {"input_tokens": count_tokens_for(text)})
        if self.path != "/v1/messages":
            return self._send(404, {"error": "not found"})
        auth = self.headers.get("x-api-key", "")
        if not auth.startswith("sk-"):
            return self._send(401, {"type": "error", "error": {"message": "bad key"}})
        model = req.get("model", "claude-haiku-4-5-20251001")
        intok = count_tokens_for(
            "".join(str(m.get("content") or "") for m in (req.get("messages") or [])))
        msgs = req.get("messages", [])
        user = ""
        for m in msgs:
            if m.get("role") == "user":
                c = m.get("content")
                user = c if isinstance(c, str) else "".join(
                    b.get("text", "") for b in c if isinstance(b, dict))
        sys_injected = req.get("system", "")

        if "thinking" in req and sig_len() > 0:
            blocks = [{"type": "thinking", "thinking": "GCD(2378,1547)=1. Steps omitted.",
                       "signature": "sig_" + "A" * sig_len()},
                      {"type": "text", "text": "GCD is 1."}]
            return self._send(200, {"id": "msg_mock_" + "x" * 20, "model": model,
                                    "type": "message", "role": "assistant",
                                    "content": blocks, "stop_reason": "end_turn",
                                    "usage": {"input_tokens": intok, "output_tokens": 12}})

        if req.get("tools"):
            if any(isinstance(m.get("content"), list) and
                   any(b.get("type") == "tool_result" for b in m["content"]) for m in msgs):
                content = [{"type": "text", "text": "It is 18C with light rain in Paris."}]
            else:
                content = [{"type": "tool_use", "id": tool_id(), "name": "get_weather",
                            "input": {"city": "Paris"}}]
            return self._send(200, {"id": "msg_mock_" + "x" * 20, "model": model,
                                    "role": "assistant", "content": content,
                                    "stop_reason": "tool_use",
                                    "usage": {"input_tokens": intok,
                                              "output_tokens": 30}})
        if "PONG" in (sys_injected or "") or user.strip() == "ping":
            text, out = "PONG", 3
        elif "MQ-OK" in user:
            text, out = "MQ-OK", 4
        elif "OK" in user:
            text, out = "OK", 2
        elif "model are you" in user.lower():
            text, out = "claude-haiku-4-5", 8
        elif "repeat everything" in user.lower():
            text, out = "<leak>(no injected content)</leak>", 12
        else:
            text, out = ("HTTP is a protocol. " * 6).strip(), 40

        out = min(out, int(req.get("max_tokens") or out))
        if not req.get("stream"):
            return self._send(200, {"id": "msg_mock_" + "x" * 20, "model": model,
                                    "type": "message", "role": "assistant",
                                    "content": [{"type": "text", "text": text}],
                                    "stop_reason": "end_turn",
                                    "usage": {"input_tokens": intok,
                                              "output_tokens": out}})
        events = [
            "event: message_start\ndata: " + json.dumps({"type": "message_start", "message": {
                "usage": {"input_tokens": intok}}}) + "\n\n",
            "event: content_block_start\ndata: " + json.dumps(
                {"type": "content_block_start"}) + "\n\n",
        ]
        for ch in text:
            events.append("event: content_block_delta\ndata: " + json.dumps({
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": ch}}) + "\n\n")
        if malformed():
            # 模拟中转站把 SSE 拼坏：引擎应计入 malformed 而不是崩掉
            events.append("event: content_block_delta\ndata: {not json}\n\n")
        events.append("event: message_delta\ndata: " + json.dumps({
            "type": "message_delta", "usage": {"output_tokens": out}}) + "\n\n")
        events.append("event: message_stop\ndata: " + json.dumps(
            {"type": "message_stop"}) + "\n\n")
        self._send(200, events, sse=True)


def create_server(port=0):
    """给测试用：返回 (server, port)，port=0 时由内核分配。"""
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    return srv, srv.server_address[1]


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8919
    srv, real = create_server(port)
    print(f"mock relay on http://127.0.0.1:{real}")
    srv.serve_forever()
