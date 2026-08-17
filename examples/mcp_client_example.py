#!/usr/bin/env python3
"""
Example: Direct JSON-RPC Model Context Protocol (MCP) Client Interaction
Demonstrates calling the Soul MCP Server via standard JSON-RPC 2.0 stdio protocol.
"""

import json
import subprocess
import sys
from pathlib import Path

def call_mcp_tool(proc, method: str, params: dict, req_id: int):
    req = {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": method,
        "params": params
    }
    raw = json.dumps(req) + "\n"
    proc.stdin.write(raw)
    proc.stdin.flush()
    resp_line = proc.stdout.readline()
    if resp_line:
        return json.loads(resp_line.strip())
    return None

def main():
    server_path = Path(__file__).parent.parent / "soul_mcp_server.py"
    
    print("Starting Soul MCP Stdio Server process...")
    proc = subprocess.Popen(
        [sys.executable, str(server_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1
    )

    try:
        # 1. Initialize MCP Protocol
        print("\n1. Initializing MCP Protocol handshake...")
        init_resp = call_mcp_tool(proc, "initialize", {}, req_id=1)
        print("MCP Server Info:", json.dumps(init_resp.get("result", {}).get("serverInfo", {}), indent=2))

        # 2. List Available Tools
        print("\n2. Listing available MCP tools...")
        tools_resp = call_mcp_tool(proc, "tools/list", {}, req_id=2)
        tool_names = [t["name"] for t in tools_resp.get("result", {}).get("tools", [])]
        print(f"Loaded {len(tool_names)} Tools:", tool_names)

        # 3. Call soul_get_identity
        print("\n3. Calling 'soul_get_identity'...")
        ident_resp = call_mcp_tool(proc, "tools/call", {"name": "soul_get_identity", "arguments": {}}, req_id=3)
        res_text = ident_resp.get("result", {}).get("content", [{}])[0].get("text", "{}")
        parsed = json.loads(res_text)
        print("Active Soul Version:", parsed.get("result", {}).get("soul_version"))
        print("Constitutional Traits:", parsed.get("result", {}).get("traits"))

        # 4. Call soul_reward
        print("\n4. Calling 'soul_reward' (+1.0 Valence)...")
        rew_resp = call_mcp_tool(proc, "tools/call", {
            "name": "soul_reward",
            "arguments": {
                "source": "client_example",
                "valence": 1.0,
                "confidence": 1.0,
                "task_context": "Validated successful MCP client round-trip."
            }
        }, req_id=4)
        print("Reward Result:", json.dumps(json.loads(rew_resp.get("result", {}).get("content", [{}])[0].get("text", "{}")), indent=2))

    finally:
        proc.terminate()
        print("\nMCP Stdio process terminated cleanly.")

if __name__ == "__main__":
    main()
