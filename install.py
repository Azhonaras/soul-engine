#!/usr/bin/env python3
"""
Soul MCP Universal Auto-Installer & Self-Registration Script v1.2.0
Allows any AI agent or operator to automatically install and register Soul in their runtime environment.
"""

from __future__ import annotations

import os
import sys
import json
import shutil
import platform
import subprocess
import argparse
from pathlib import Path


BANNER = r"""
======================================================================
     ____             __    __  ___________  ____                      
    / __/___  __ __  / /   /  |/  / ___/ _ \/ __/__ _____  _____ ____ 
   _\ \/ _ \/ // /  / /__ / /|_/ / /__/ ___/\ \/ -_) __/ |/ / -_) __/ 
  /___/\___/\_,_/  /____//_/  /_/\___/_/  /___/\__/_/  |___/\__/_/   
                                                                      
    Bio-Homeostatic Epistemic Identity Engine & MCP Server (v1.2.0)    
======================================================================
"""


def log(msg: str):
    print(f"[*] {msg}")


def log_ok(msg: str):
    print(f"[+] SUCCESS: {msg}")


def log_warn(msg: str):
    print(f"[!] WARNING: {msg}")


def log_err(msg: str):
    print(f"[-] ERROR: {msg}")


def get_default_mcp_config_paths() -> list[Path]:
    """Returns candidate MCP configuration paths across operating systems."""
    home = Path.home()
    system = platform.system()

    paths = []

    # Claude Desktop (JSON). Hermes is YAML (~/.hermes/config.yaml) — installer does not write YAML.
    if system == "Windows":
        appdata = os.environ.get("APPDATA")
        if appdata:
            paths.append(Path(appdata) / "Claude" / "claude_desktop_config.json")
    elif system == "Darwin":
        paths.append(home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json")
    else:
        paths.append(home / ".config" / "Claude" / "claude_desktop_config.json")

    paths.append(home / ".gemini" / "config" / "mcp_config.json")  # Antigravity
    paths.append(home / ".cursor" / "mcp.json")
    # ponytail: goose uses YAML which the installer can't write; dropped until
    # a YAML writer exists (see register_mcp_config skip path).

    return paths


def install_dependencies(editable: bool = True) -> bool:
    """Install this clone so `python -m soul_mcp_server` works from any cwd."""
    log("Installing Soul Engine (editable)...")
    root = str(Path(__file__).resolve().parent)
    cmd = [sys.executable, "-m", "pip", "install"]
    if editable:
        cmd.append("-e")
    cmd.append(root)
    try:
        subprocess.check_call(cmd)
        log_ok("Package installed; python -m soul_mcp_server is available.")
        return True
    except Exception as exc:
        log_warn(f"pip install -e failed: {exc}. MCP configs will use soul_mcp_server.py path.")
        return False


def init_database(db_path: Path):
    log(f"Initializing Soul SQLite Database at: {db_path}")
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Import kernel and initialize genesis
    sys.path.insert(0, str(Path(__file__).parent.resolve()))
    from soul_kernel import SoulKernel
    kernel = SoulKernel(db_path=str(db_path))
    state = kernel.get_current_state()
    log_ok(f"Genesis state verified! Soul Version: {state.soul_version}, State Hash: {state.state_hash[:12]}...")
    return kernel


def init_admin_key(soul_dir: Path) -> Path:
    """Generate or verify cryptographically random admin secret for Tier-2 signing."""
    key_path = soul_dir / "admin.key"
    if not key_path.exists():
        import secrets
        key_hex = secrets.token_hex(32)
        key_path.write_text(key_hex + "\n", encoding="utf-8")
        try:
            os.chmod(key_path, 0o600)
        except Exception:
            pass
        log_ok(f"Generated secure admin signing key at: {key_path}")
    else:
        log(f"Existing admin signing key verified at: {key_path}")
    return key_path


def register_mcp_config(
    target_config: Path,
    server_script_path: Path,
    db_path: Path,
    python_exe: str,
    use_module: bool = False,
):
    if target_config.suffix.lower() in {".yaml", ".yml"}:
        log_warn(f"Skipping YAML config {target_config}; installer writes JSON MCP configs only.")
        return
    log(f"Configuring MCP Server in: {target_config}")
    target_config.parent.mkdir(parents=True, exist_ok=True)

    data = {}
    if target_config.exists():
        try:
            with open(target_config, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            log_warn(f"Skipping {target_config}; existing file is not valid JSON (will not overwrite).")
            return

    if "mcpServers" not in data:
        data["mcpServers"] = {}

    args = ["-m", "soul_mcp_server"] if use_module else [str(server_script_path.resolve())]
    data["mcpServers"]["soul"] = {
        "command": python_exe,
        "args": args,
        "env": {
            "SOUL_DB_PATH": str(db_path.resolve())
        }
    }

    with open(target_config, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    log_ok(f"Registered 'soul' MCP server into {target_config}")


def write_tool_schemas(target_schema_dir: Path) -> int:
    """Write live MCP tool contracts so Antigravity/schema copies cannot drift."""
    from soul_mcp_server import TOOLS
    target_schema_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for tool in TOOLS:
        payload = {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["inputSchema"],
        }
        dest = target_schema_dir / f"{tool['name']}.json"
        dest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        n += 1
    return n


def copy_schemas_if_needed(target_schema_dir: Path):
    repo_schemas = Path(__file__).resolve().parent / "schemas"
    try:
        n = write_tool_schemas(target_schema_dir)
        log_ok(f"Wrote {n} MCP JSON schemas to {target_schema_dir}")
        return
    except Exception as exc:
        log_warn(f"Could not write live schemas ({exc}); copying repo snapshots if present.")
        if repo_schemas.exists() and repo_schemas.is_dir():
            target_schema_dir.mkdir(parents=True, exist_ok=True)
            for schema_file in repo_schemas.glob("*.json"):
                shutil.copy(schema_file, target_schema_dir / schema_file.name)
            log_ok(f"Copied {len(list(repo_schemas.glob('*.json')))} MCP JSON schemas to {target_schema_dir}")


def skill_user_dirs(name: str) -> list[Path]:
    home = Path.home()
    return [
        home / ".claude" / "skills" / name,
        home / ".hermes" / "skills" / name,
        home / ".cursor" / "skills" / name,
        home / ".gemini" / "config" / "skills" / name,
        home / ".gemini" / "antigravity-cli" / "skills" / name,
        home / ".agents" / "skills" / name,
        home / ".pi" / "agent" / "skills" / name,
    ]


def seal_skill_user_dirs() -> list[Path]:
    """soul-seal dirs (tests import this name)."""
    return skill_user_dirs("soul-seal")


def _skill_src(repo_root: Path, name: str) -> Path | None:
    candidates = [
        Path(__file__).resolve().parent / "skills" / name / "SKILL.md",
        repo_root / "skills" / name / "SKILL.md",
        Path(sys.prefix) / "share" / "soul-engine" / "skills" / name / "SKILL.md",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def _seal_skill_src(repo_root: Path) -> Path | None:
    return _skill_src(repo_root, "soul-seal")


def install_seal_skill(repo_root: Path):
    """Copy soul-seal and seacom into standard user skill dirs."""
    for name in ("soul-seal", "seacom"):
        src = _skill_src(repo_root, name)
        if src is None:
            log_warn(f"skills/{name}/SKILL.md missing; skip")
            continue
        for dest in skill_user_dirs(name):
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest / "SKILL.md")
            log_ok(f"Installed {name} skill at {dest}")


def main():
    print(BANNER)
    parser = argparse.ArgumentParser(description="Install and configure Soul MCP Server for AI agents.")
    parser.add_argument("--db-path", type=str, default=str(Path.home() / ".soul" / "soul.db"), help="Target SQLite database path")
    parser.add_argument("--config-path", type=str, default=None, help="Explicit MCP config path (e.g. claude_desktop_config.json)")
    parser.add_argument("--no-deps", action="store_true", help="Skip pip dependencies installation")
    args = parser.parse_args()

    pip_ok = False
    if not args.no_deps:
        pip_ok = install_dependencies()

    # 2. Database & Admin Secret Key
    db_path = Path(args.db_path).resolve()
    init_admin_key(db_path.parent)
    kernel = init_database(db_path)

    # 3. Server Script Path
    server_script = (Path(__file__).parent / "soul_mcp_server.py").resolve()
    python_exe = sys.executable

    # 4. MCP Config Registration
    target_configs = []
    if args.config_path:
        target_configs.append(Path(args.config_path).resolve())
    else:
        candidates = get_default_mcp_config_paths()
        for cand in candidates:
            # Register in existing or default paths
            target_configs.append(cand)

    for cfg in target_configs:
        try:
            register_mcp_config(cfg, server_script, db_path, python_exe, use_module=pip_ok)
        except Exception as exc:
            log_warn(f"Could not register into {cfg}: {exc}")

    # 5. Schema Copy for Antigravity if present
    ag_schema_dir = Path.home() / ".gemini" / "antigravity" / "mcp" / "soul"
    copy_schemas_if_needed(ag_schema_dir)

    # 6. Same SEAL skill for Claude / Hermes / Cursor (MCP initialize covers every client)
    install_seal_skill(Path(__file__).parent.resolve())
    kernel.close()

    print("\n" + "=" * 70)
    print("                SOUL MCP SERVER INSTALLATION COMPLETE                ")
    print(f" • Server Script   : {server_script}")
    print(f" • SQLite Database : {db_path}")
    print(f" • Python Executable: {python_exe}")
    print(" • MCP args        : python -m soul_mcp_server" if pip_ok else f" • MCP args        : {server_script}")
    print(" • Registered Tools: 23 Active MCP Tools (14 Core + 9 Review Cycle)")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
