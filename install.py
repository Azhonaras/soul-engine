#!/usr/bin/env python3
"""
Soul MCP Universal Auto-Installer & Self-Registration Script v1.1.1
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
                                                                      
    Bio-Homeostatic Epistemic Identity Engine & MCP Server (v1.1.1)    
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
    paths.append(home / ".config" / "goose" / "config.yaml")

    return paths


def install_dependencies(editable: bool = True):
    log("Installing Python package dependencies...")
    cmd = [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"]
    try:
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL)
        log_ok("Dependencies installed successfully.")
    except Exception as exc:
        log_warn(f"Failed to run pip install requirements.txt: {exc}. Attempting setup.py develop...")
        try:
            subprocess.check_call([sys.executable, "setup.py", "develop"], stdout=subprocess.DEVNULL)
            log_ok("Package installed via setup.py.")
        except Exception as e2:
            log_warn(f"Pip setup warning: {e2}. Continuing with local module execution.")


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


def register_mcp_config(target_config: Path, server_script_path: Path, db_path: Path, python_exe: str):
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
            data = {}

    if "mcpServers" not in data:
        data["mcpServers"] = {}

    data["mcpServers"]["soul"] = {
        "command": python_exe,
        "args": [str(server_script_path.resolve())],
        "env": {
            "SOUL_DB_PATH": str(db_path.resolve())
        }
    }

    with open(target_config, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    log_ok(f"Registered 'soul' MCP server into {target_config}")


def copy_schemas_if_needed(target_schema_dir: Path):
    src_dir = Path(__file__).parent / "schemas"
    if src_dir.exists() and src_dir.is_dir():
        target_schema_dir.mkdir(parents=True, exist_ok=True)
        for schema_file in src_dir.glob("*.json"):
            shutil.copy(schema_file, target_schema_dir / schema_file.name)
        n = len(list(src_dir.glob("*.json")))
        log_ok(f"Copied {n} MCP JSON schemas to {target_schema_dir}")


def seal_skill_user_dirs() -> list[Path]:
    """Standard Agent Skills dirs. Same SKILL.md; any machine that runs install.py."""
    home = Path.home()
    return [
        home / ".claude" / "skills" / "soul-seal",
        home / ".hermes" / "skills" / "soul-seal",
        home / ".cursor" / "skills" / "soul-seal",
        home / ".gemini" / "config" / "skills" / "soul-seal",
        home / ".gemini" / "antigravity-cli" / "skills" / "soul-seal",
        home / ".agents" / "skills" / "soul-seal",
        home / ".pi" / "agent" / "skills" / "soul-seal",
    ]


def _seal_skill_src(repo_root: Path) -> Path | None:
    candidates = [
        Path(__file__).resolve().parent / "skills" / "soul-seal" / "SKILL.md",
        repo_root / "skills" / "soul-seal" / "SKILL.md",
        Path(sys.prefix) / "share" / "soul-engine" / "skills" / "soul-seal" / "SKILL.md",
    ]
    for p in candidates:
        if p.is_file():
            return p
    return None


def install_seal_skill(repo_root: Path):
    """Copy the published soul-seal skill into standard user skill dirs (any machine that runs install.py)."""
    src = _seal_skill_src(repo_root)
    if src is None:
        log_warn("skills/soul-seal/SKILL.md missing; skip skill install")
        return
    for dest in seal_skill_user_dirs():
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest / "SKILL.md")
        log_ok(f"Installed soul-seal skill at {dest}")


def main():
    print(BANNER)
    parser = argparse.ArgumentParser(description="Install and configure Soul MCP Server for AI agents.")
    parser.add_argument("--db-path", type=str, default=str(Path.home() / ".soul" / "soul.db"), help="Target SQLite database path")
    parser.add_argument("--config-path", type=str, default=None, help="Explicit MCP config path (e.g. claude_desktop_config.json)")
    parser.add_argument("--no-deps", action="store_true", help="Skip pip dependencies installation")
    args = parser.parse_args()

    # 1. Dependencies
    if not args.no_deps:
        install_dependencies()

    # 2. Database
    db_path = Path(args.db_path).resolve()
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
            register_mcp_config(cfg, server_script, db_path, python_exe)
        except Exception as exc:
            log_warn(f"Could not register into {cfg}: {exc}")

    # 5. Schema Copy for Antigravity if present
    ag_schema_dir = Path.home() / ".gemini" / "antigravity" / "mcp" / "soul"
    copy_schemas_if_needed(ag_schema_dir)

    # 6. Same SEAL skill for Claude / Hermes / Cursor (MCP initialize covers every client)
    install_seal_skill(Path(__file__).parent.resolve())

    print("\n" + "=" * 70)
    print("                SOUL MCP SERVER INSTALLATION COMPLETE                ")
    print(f" • Server Script   : {server_script}")
    print(f" • SQLite Database : {db_path}")
    print(f" • Python Executable: {python_exe}")
    print(" • Registered Tools: 20 Active MCP Tools (12 Core + 8 Review Cycle)")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
