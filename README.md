# laya-mcp — on-device typed decisions in ~10ms

**Laya-MLX** as an [MCP](https://modelcontextprotocol.io) server (and plain-HTTP
API). It answers **typed decisions** — *choose an option / score a rubric / is
this true?* — on your own machine (Apple Silicon / MLX), with **no cloud and
~10ms after warm-up**.

Not a chatbot. No token-by-token text, no JSON that can break. One forward pass
returns a structured answer you can branch on. Ideal for **routing, triage,
classification, lead scoring, and guardrails** where an LLM would be slow,
expensive, or would ship your data to the cloud.

> ⚡ **Runs on Apple Silicon (M-series) out of the box.** Multi-language
> checkpoint (EN/DE + more) by default, so it triages real inbox/ticket text.

## Tools
| tool | returns | use |
|---|---|---|
| `laya_decide` | `{choice, confidence, probabilities}` | route / classify / pick |
| `laya_score` | `{score, confidence, probabilities, legend}` | urgency / fit / priority rubric |
| `laya_is_true` | `{p_true, confidence}` | yes/no gate (e.g. "invoice overdue?") |

## Quick start (MCP)
One-liner via `uvx` (no install):
```bash
uvx --from laya-mcp laya-mcp
```

**Claude Desktop / Cursor / any MCP client** → add:
```json
{
  "mcpServers": {
    "laya-mlx": {
      "command": "uvx",
      "args": ["--from", "laya-mcp", "laya-mcp"]
    }
  }
}
```

> First call downloads the model (~30s, cached after). After that: **~10ms.**

## Raw stdio (no MCP client)
Newline-delimited JSON-RPC 2.0:
```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"laya_decide","arguments":{
     "state":"Der Kunde wurde doppelt berechnet, bitte erstatten.","question":"Which team handles this?","options":["billing","technical","sales"]}}}' \
  | uvx --from laya-mcp laya-mcp
# -> id 2: {"choice":"billing","confidence":0.9999,"probabilities":{"billing":1.0,...},"ms":...}
```

## HTTP API (n8n / Make / curl)
For nodes that just POST JSON — no MCP client required:
```bash
uvx --from laya-mcp laya-http          # listens on 127.0.0.1:8901
```
| endpoint | body |
|---|---|
| `POST /decide` | `{state, question, options}` |
| `POST /score`  | `{state, question, levels}` |
| `POST /is_true`| `{state, proposition}` |
| `GET  /health` | `{status, model, loaded}` |

```bash
curl -s localhost:8901/decide -H 'Content-Type: application/json' -d '{
  "state":"Wir suchen einen Partner für die Digitalisierung unserer Buchhaltung.",
  "question":"Pursue this lead?","options":["pursue","maybe","drop"]}'
# -> {"choice":"pursue","confidence":0.74,"probabilities":{"pursue":0.92,...},"ms":1.8}
```

## Environment
| var | default | meaning |
|---|---|---|
| `LAYA_MODEL` | `aac6fef/laya-multilingual-mlx` | checkpoint id |
| `LAYA_ADDR`  | `127.0.0.1:8901` | HTTP listen address |

## Why on-device
- **Privacy / GDPR** — data never leaves the machine.
- **Latency** — ~10ms = real-time routing, not "fast".
- **Cost** — ~zero marginal; millions of decisions/day are practical.

## Works with
Tested end-to-end against a Go **MCP gateway** (stdio transport, tool policy,
per-key budget + kill switch, metering) — so it slots into an existing
agent/LLM gateway as one more, very cheap, local tool.

## License
MIT
