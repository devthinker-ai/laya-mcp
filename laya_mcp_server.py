#!/usr/bin/env python3
"""Laya-MLX as an MCP stdio server.

Typed decisions, not generated text:
  laya_decide  - choice over named options
  laya_score   - ordered rubric score
  laya_is_true - probability that a proposition holds

Wire protocol: newline-delimited JSON-RPC 2.0 on stdin/stdout (MCP stdio).
All logging goes to stderr — stdout is reserved for the protocol.

Environment:
  LAYA_MODEL   checkpoint id (default: aac6fef/laya-multilingual-mlx)
"""
import json
import os
import sys
import time
import traceback

import laya_mlx as laya

MODEL = os.environ.get("LAYA_MODEL", "aac6fef/laya-multilingual-mlx")

AGENT = None


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def agent():
    """Lazy singleton. Model download happens on first use (stderr only)."""
    global AGENT
    if AGENT is None:
        t0 = time.time()
        log(f"[laya-mcp] loading model {MODEL} ...")
        # redirect stdout during load: huggingface/progress bars must not
        # corrupt the JSON-RPC stream
        saved = sys.stdout
        sys.stdout = sys.stderr
        try:
            AGENT = laya.load(MODEL, dtype="float16")
        finally:
            sys.stdout = saved
        log(f"[laya-mcp] ready in {time.time() - t0:.1f}s")
    return AGENT


TOOLS = [
    {
        "name": "laya_decide",
        "description": (
            "Pick the best option for a typed decision. On-device decision model, "
            "~10ms after warm-up, no cloud. Use for routing/triage/classification."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "state": {"type": "string", "description": "Context text (email, ticket, lead)"},
                "question": {"type": "string", "description": "What to decide"},
                "options": {"type": "array", "items": {"type": "string"},
                            "description": "Named options to choose from"},
            },
            "required": ["state", "question", "options"],
        },
    },
    {
        "name": "laya_score",
        "description": (
            "Score the state against an ordered rubric (0..n-1), e.g. "
            "low/medium/high urgency. On-device, ~10ms."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "state": {"type": "string"},
                "question": {"type": "string", "description": "What to score"},
                "levels": {"type": "array", "items": {"type": "string"},
                           "description": "Ordered rubric levels, low to high"},
            },
            "required": ["state", "question", "levels"],
        },
    },
    {
        "name": "laya_is_true",
        "description": (
            "Probability that a proposition about the state is true "
            "(e.g. 'the invoice is overdue'). On-device, ~10ms."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "state": {"type": "string"},
                "proposition": {"type": "string"},
            },
            "required": ["state", "proposition"],
        },
    },
]


def run_tool(name: str, args: dict) -> dict:
    t0 = time.time()
    if name == "laya_decide":
        r = agent().predict(args["state"], {"d": {
            "type": "choice", "instructions": args["question"],
            "criteria": args["options"]}})
        a = r["answers"]["d"]
        payload = {"choice": a["choice"], "confidence": a["confidence"],
                   "probabilities": a["probabilities"]}
    elif name == "laya_score":
        r = agent().predict(args["state"], {"s": {
            "type": "score", "instructions": args["question"],
            "criteria": args["levels"]}})
        a = r["answers"]["s"]
        payload = {"score": a["score"], "confidence": a["confidence"],
                   "probabilities": a["probabilities"], "legend": a["legend"]}
    elif name == "laya_is_true":
        r = agent().predict(args["state"], {"p": {
            "type": "noul", "instructions": args["proposition"]}})
        a = r["answers"]["p"]
        payload = {"p_true": a["noul"], "confidence": a["confidence"]}
    else:
        raise ValueError(f"unknown tool: {name}")
    payload["ms"] = round((time.time() - t0) * 1000, 1)
    return payload


def handle(method: str, params: dict):
    if method == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "laya-mlx", "version": "0.2.0"},
        }
    if method == "tools/list":
        return {"tools": TOOLS}
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            payload = run_tool(name, args)
            return {"content": [{"type": "text",
                                  "text": json.dumps(payload, ensure_ascii=False)}]}
        except Exception as e:  # noqa: BLE001
            log(f"[laya-mcp] tool {name} failed: {e}\n{traceback.format_exc()}")
            return {"content": [{"type": "text", "text": f"error: {e}"}],
                    "isError": True}
    return None


def main() -> None:
    log(f"[laya-mcp] stdio server starting (model={MODEL})")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            log(f"[laya-mcp] bad json line skipped: {line[:120]!r}")
            continue
        if "id" not in msg:
            continue  # notification (e.g. notifications/initialized)
        result = handle(msg.get("method"), msg.get("params") or {})
        if result is not None:
            out = {"jsonrpc": "2.0", "id": msg["id"], "result": result}
        else:
            out = {"jsonrpc": "2.0", "id": msg["id"],
                   "error": {"code": -32601, "message": "method not found"}}
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()
    log("[laya-mcp] stdin closed, exiting")


if __name__ == "__main__":
    main()
