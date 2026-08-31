# Headroom reference

Live index: https://headroom-docs.vercel.app/llms.txt
Full blob: https://headroom-docs.vercel.app/llms-full.txt

## Install

Python 3.10+. Prefer **3.13** so dashboard dollar savings work (LiteLLM does not install on 3.14+). Token savings still track on 3.14; `$` stays `$0.00`.

```bash
uv tool install --python 3.13 "headroom-ai[all]"
uv tool update-shell
headroom --version

pip install "headroom-ai[all]"
npm install headroom-ai          # TypeScript SDK only — no `headroom` CLI
docker pull ghcr.io/headroomlabs-ai/headroom:latest
```

Granular extras: `[proxy]`, `[mcp]`, `[ml]`, `[code]`, `[memory]`, `[vector]` (needs C++ toolchain; **not** in `[all]`), `[relevance]`, `[image]`, `[agno]`, `[langchain]`, `[evals]`, `[pytorch-mps]`.

`[all]` excludes framework adapters. Add `[langchain]`, `[agno]`, `[strands]`, `[anyllm]`, `[bedrock]` separately.

Wheels: Windows `win_amd64`, Linux x86_64/aarch64, macOS Apple Silicon and Intel. x86 without AVX2 falls back off ONNX (BM25 / heuristics).

Update: `headroom update` / `headroom update --check` / `headroom update --pre`.

## Wrap / unwrap

```bash
headroom wrap claude|codex|grok|copilot|cursor|aider|opencode|cline|continue|goose|openhands|openclaw|vibe|omp|zcode
headroom unwrap claude|copilot|codex|grok|kimi|omp|opencode|openclaw|zcode
```

Cursor wrap is **manual**: starts the proxy and prints base URLs for Settings → Models. It does not rewrite Cursor config.

VS Code Copilot: `headroom copilot-auth login` then `headroom wrap vscode`. VS Code Claude Code: `headroom wrap vscode-claude`, reload, keep running.

Default wrap registers **Serena** (semantic code nav) at user scope. Skip: `--code-memory none`.

## Proxy

```bash
headroom proxy --port 8787
curl http://127.0.0.1:8787/health
headroom dashboard
headroom doctor
headroom perf
```

Default savings profile: `coding` (cache mode — compress live zone only, keep prefix cache). Aggressive: `HEADROOM_SAVINGS_PROFILE=agent-90`.

Point clients at `http://127.0.0.1:8787` (Anthropic) or `http://127.0.0.1:8787/v1` (OpenAI-compatible).

Output shaping (trim what the model **writes**): `HEADROOM_OUTPUT_SHAPER=1` before launch. Learn terseness: `headroom learn --verbosity` then `--apply`.

## MCP CLI

```bash
headroom mcp install                 # Claude Code registrar
headroom mcp serve                   # stdio for Cursor / any host
headroom mcp serve --proxy-url http://127.0.0.1:8787
headroom mcp status
headroom mcp uninstall
headroom mcp serve --transport http --host 127.0.0.1 --port 8788 --path /mcp
```

The HTTP proxy is **not** an MCP endpoint at `/mcp`. Canonical descriptor: repo `server.json`.

## Library

```python
from headroom import compress
result = compress(messages, model="claude-sonnet-4-5-20250929")
```

```typescript
import { compress } from 'headroom-ai';
const result = await compress(messages, { model: 'claude-sonnet-4-5-20250929' });
```

Wrappers: `withHeadroom(new Anthropic())`, `withHeadroom(new OpenAI())`, Vercel AI middleware, LiteLLM `HeadroomCallback()`, LangChain `HeadroomChatModel`, Agno `HeadroomAgnoModel`.

## What compresses vs passthrough

Helps: JSON arrays (dict/string/number), structured logs, long agent sessions, build/test output.

Little value: short chats, code-only edit sessions, single-turn with no tool pile-up.

Passthrough by default: short messages, most source code (recent-code + analysis-context gates), compact grep, system prompts. JSON objects with no arrays, arrays < 5 items, < 200 tokens, malformed JSON.

Failures return the original. Compression that enlarges output is discarded.

## Windows / PATH

MCP `command: "headroom"` fails if the host's PATH lacks the uv/pipx shim. Use `where headroom` and the absolute `.exe` path.

Corporate SSL inspection: install Rust first, or `pip install --only-binary headroom-ai headroom-ai`. Strict CA errors on 3.13+: `HEADROOM_TLS_STRICT=0` (narrower than disabling verify).
