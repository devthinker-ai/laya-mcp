#!/usr/bin/env python3
"""Laya-MLX over plain HTTP (for n8n / Make / curl — no MCP client needed).

Endpoints (POST, JSON):
  /decide   {state, question, options}  -> {choice, confidence, probabilities, ms}
  /score    {state, question, levels}   -> {score, confidence, probabilities, legend, ms}
  /is_true  {state, proposition}        -> {p_true, confidence, ms}
  /health                             -> {status, model, loaded}

GET /v1/chat/completions-compatible not implemented — this is a decision API,
not a chat API.

Environment:
  LAYA_MODEL  checkpoint id (default: aac6fef/laya-multilingual-mlx)
  LAYA_ADDR   listen address (default: 127.0.0.1:8901)

Stdlib only (http.server) — no extra dependency for the HTTP layer.
"""
import json
import os
import sys

import laya_mlx as laya

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from laya_mcp_server import agent, run_tool  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

ADDR = os.environ.get("LAYA_ADDR", "127.0.0.1:8901")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quiet access log
        print(f"[laya-http] {self.address_string()} {fmt % args}",
              file=sys.stderr, flush=True)

    def _send(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):  # CORS preflight
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path in ("/health", "/"):
            from laya_mcp_server import AGENT
            self._send(200, {"status": "ok", "model": "laya-mlx",
                             "loaded": AGENT is not None})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._send(400, {"error": "invalid json"})
            return

        tool = {
            "/decide": "laya_decide",
            "/score": "laya_score",
            "/is_true": "laya_is_true",
        }.get(self.path)
        if tool is None:
            self._send(404, {"error": f"unknown endpoint {self.path}"})
            return
        try:
            self._send(200, run_tool(tool, req))
        except Exception as e:  # noqa: BLE001
            self._send(500, {"error": str(e)})


def main() -> None:
    host, port = ADDR.rsplit(":", 1)
    print(f"[laya-http] listening on {ADDR}", file=sys.stderr, flush=True)
    ThreadingHTTPServer((host, int(port)), Handler).serve_forever()


if __name__ == "__main__":
    main()
