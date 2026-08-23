# 1.1.1 notes (not a second GitHub repo)

Ship the **parent** `soul-engine` tree (PR onto `main`). Do not `git init` this folder. Do not publish `github-ready/`.

Human origin: type **SEAL** in any MCP chat to approve quarantined memory. MCP cannot mint `origin_kind=human`. Then in a tty: `py -3 -m soul_host seal review_packet.json` (type **SEAL** then **COMMIT**). MCP `soul_review_commit` is the same tool everywhere; it needs that human `host_events` row.

NLI is a token heuristic. Default recall is reviewed memory after commit.

Tests: `python -m unittest discover -s tests`
