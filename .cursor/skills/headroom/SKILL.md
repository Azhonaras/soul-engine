---
name: headroom
description: >
  Compress tool outputs, logs, JSON, files, and RAG chunks with Headroom
  (local-first library, proxy, and MCP) before they reach the LLM. Same
  answers, fewer tokens; originals stay retrievable via CCR. Use when the
  user mentions Headroom, headroom-ai, token compression, context bloat,
  wrapping Cursor/Claude/Codex, MCP tools headroom_compress /
  headroom_retrieve / headroom_stats, or when large tool dumps threaten
  the context window and Headroom MCP is available.
---

# Headroom

Local-first context compression for agents. Compresses what the model **reads**
(tool outputs, logs, JSON, files). Does not replace Ponytail (what you **write**).

Canonical docs: https://headroom-docs.vercel.app/llms.txt
Repo: https://github.com/headroomlabs-ai/headroom
Install extras, wrap matrix, env, troubleshooting: [reference.md](reference.md)

## Modes (pick one)

| Goal | Do this |
|------|---------|
| Automatic compression of all Cursor traffic | `headroom wrap cursor` then paste the printed base URL into Cursor model settings. Keep the wrapper running. |
| On-demand compress/retrieve in this chat | Add MCP `headroom mcp serve`. Call the three tools below. |
| Both | Wrap **and** MCP. Proxy compresses HTTP traffic; MCP tools run after the model already saw content. They do not double-compress the same blob. |
| Inline in Python/TS | `compress(messages)` / `await compress(messages, { model })`. CLI is **only** the PyPI package, not `npm install headroom-ai`. |

Cursor wrap is **manual**: it starts the proxy and prints base URLs. It does not rewrite Cursor config or launch the app.

Undo durable wraps with `headroom unwrap <agent>` (not `cursor` — stop the wrapper / revert the pasted base URL).

## MCP tools

When Headroom MCP is connected, use it. Do not invent a second compressor.

### `headroom_compress`

Call on **large** tool results before reasoning: JSON arrays, build/test logs, API dumps, long file reads you are **not** about to edit.

Pass the raw `content`. Keep `hash`. Work from `compressed`. Do **not** paste the uncompressed original back into the chat.

Skip: short text (< ~300 tokens), source you are editing, already-compact grep/search, system prompts, content the proxy already compressed.

### `headroom_retrieve`

Call when the compressed form is not enough. Prefer `query` to pull matching slices instead of the whole original.

Local MCP originals: ~1 hour TTL. Proxy originals: ~5 minutes. Expired → recompress or re-run the tool.

### `headroom_stats`

Call when the user asks about savings, or MCP usage looks high. Compare `tokens_saved` to call count. Do not treat host "MCP share" as Headroom overhead.

## Cursor setup

```bash
uv tool install --python 3.13 "headroom-ai[all]"   # preferred CLI
# or: pip install "headroom-ai[all]"
headroom doctor
headroom wrap cursor
```

Then:

1. Copy the printed OpenAI / Anthropic base URL into Cursor Settings → Models (typically `http://127.0.0.1:8787` / `http://127.0.0.1:8787/v1`).
2. Keep that terminal running.
3. Register MCP (stdio). If the host cannot see `headroom` on PATH, use the absolute path from `where headroom` (Windows) or `command -v headroom`:

```json
{
  "mcpServers": {
    "headroom": {
      "command": "headroom",
      "args": ["mcp", "serve", "--proxy-url", "http://127.0.0.1:8787"]
    }
  }
}
```

`headroom mcp install` is Claude Code's registrar. For Cursor, write MCP settings as above.

Verify: `headroom doctor`, then `curl http://127.0.0.1:8787/health`. Optional: `headroom dashboard` while the proxy is up.

## Agent rules

- Prefer Headroom over summarizing huge dumps by hand when MCP or the proxy is available.
- After compressing, reason on the compressed text. Retrieve only what you still need.
- Do not disable compression to "be safe" on JSON/logs — errors, outliers, and failures are retained by default.
- Code mostly passes through on purpose (recent-code and analysis-context gates). Do not fight that while editing.
- Do not send user data to a hosted compression API. Headroom runs locally.
- Sandbox / no local process → skip proxy/wrap; say so. MCP-only still works if the host can spawn `headroom mcp serve`.

## Skip Headroom when

- Short chat, no accumulated tool output
- Code-only read/write of files the user asked to change
- User wants a single provider's native compaction only, and no cross-agent memory
- Environment cannot run a local process
