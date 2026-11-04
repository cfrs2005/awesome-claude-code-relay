#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地联调用 mock Anthropic 兼容端点：实现 /v1/models、/v1/messages（非流式 + SSE 流式 + tools）。
仅供测试 MQ 引擎链路，不代表真实模型行为。用法: python3 tests/mock_relay.py [port]
"""
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

FIXED_INPUT_TOKENS = 25


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
        if self.path == "/v1/models":
            self._send(200, {"data": [{"id": "claude-haiku-4-5-20251001"},
                                      {"id": "claude-sonnet-4-5-20250929"}]})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("content-length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        if self.path != "/v1/messages":
            return self._send(404, {"error": "not found"})
        auth = self.headers.get("x-api-key", "")
        if not auth.startswith("sk-"):
            return self._send(401, {"type": "error", "error": {"message": "bad key"}})
        if "thinking" in req:
            return self._send(400, {"type": "error",
                                    "error": {"message": "thinking not supported by mock"}})
        model = req.get("model", "claude-haiku-4-5-20251001")
        msgs = req.get("messages", [])
        user = ""
        for m in msgs:
            if m.get("role") == "user":
                c = m.get("content")
                user = c if isinstance(c, str) else "".join(
                    b.get("text", "") for b in c if isinstance(b, dict))
        sys_injected = req.get("system", "")

        if req.get("tools"):
            if any(isinstance(m.get("content"), list) and
                   any(b.get("type") == "tool_result" for b in m["content"]) for m in msgs):
                content = [{"type": "text", "text": "It is 18C with light rain in Paris."}]
            else:
                content = [{"type": "tool_use", "id": "toolu_mock1", "name": "get_weather",
                            "input": {"city": "Paris"}}]
            return self._send(200, {"id": "msg_mock_" + "x" * 20, "model": model,
                                    "role": "assistant", "content": content,
                                    "stop_reason": "tool_use",
                                    "usage": {"input_tokens": FIXED_INPUT_TOKENS,
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

        if not req.get("stream"):
            return self._send(200, {"id": "msg_mock_" + "x" * 20, "model": model,
                                    "role": "assistant",
                                    "content": [{"type": "text", "text": text}],
                                    "stop_reason": "end_turn",
                                    "usage": {"input_tokens": FIXED_INPUT_TOKENS,
                                              "output_tokens": out}})
        events = [
            "event: message_start\ndata: " + json.dumps({"type": "message_start", "message": {
                "usage": {"input_tokens": FIXED_INPUT_TOKENS}}}) + "\n\n",
            "event: content_block_start\ndata: " + json.dumps(
                {"type": "content_block_start"}) + "\n\n",
        ]
        for ch in text:
            events.append("event: content_block_delta\ndata: " + json.dumps({
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": ch}}) + "\n\n")
        events.append("event: message_delta\ndata: " + json.dumps({
            "type": "message_delta", "usage": {"output_tokens": out}}) + "\n\n")
        events.append("event: message_stop\ndata: " + json.dumps(
            {"type": "message_stop"}) + "\n\n")
        self._send(200, events, sse=True)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8919
    print(f"mock relay on http://127.0.0.1:{port}")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
