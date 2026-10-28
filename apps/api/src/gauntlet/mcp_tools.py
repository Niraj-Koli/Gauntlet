"""The third-party MCP servers the agents run as subprocesses, and their pinned versions.

By default they run through uvx and npx, which download them on first use. Container
images install them ahead of time instead, so a run never waits on (or trusts) a package
registry:

    python mcp_tools.py /opt/mcp-tools

and set MCP_TOOLS_DIR to that directory. This file imports nothing from gauntlet, so the
image can run it before the application is installed.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# Pinned so a compromised or breaking release can't reach the agents unreviewed.
FETCH_VERSION = "2026.8.18"
TAVILY_VERSION = "0.2.22"
MEMORY_VERSION = "0.0.17"
MASSIVE_REF = "v0.10.0"
# tavily-mcp 0.2.22 bundles an MCP SDK with known vulnerabilities; installs use a patched one.
NODE_OVERRIDES = {"@modelcontextprotocol/sdk": "1.32.1"}

MCP_PIN = "mcp<2"
MASSIVE_SOURCE = f"git+https://github.com/massive-com/mcp_massive@{MASSIVE_REF}"

NODE_BIN = "node/node_modules/.bin"

# name: (how uvx or npx runs it, the installed executable)
TOOLS: dict[str, tuple[list[str], str]] = {
    "fetch": (["uvx", "--with", MCP_PIN, f"mcp-server-fetch=={FETCH_VERSION}"], "bin/mcp-server-fetch"),
    "tavily": (["npx", "-y", f"tavily-mcp@{TAVILY_VERSION}"], f"{NODE_BIN}/tavily-mcp"),
    "memory": (["npx", "-y", f"mcp-memory-libsql@{MEMORY_VERSION}"], f"{NODE_BIN}/mcp-memory-libsql"),
    "massive": (["uvx", "--with", MCP_PIN, "--from", MASSIVE_SOURCE, "mcp_massive"], "bin/mcp_massive"),
}


def command(name: str, tools_dir: Path | None) -> tuple[str, list[str]]:
    """The command and arguments that start a tool: installed if tools_dir is set, else uvx/npx."""
    on_demand, installed = TOOLS[name]
    if tools_dir is None:
        return on_demand[0], on_demand[1:]
    return str(tools_dir / installed), []


def install(tools_dir: Path) -> None:
    tools_dir.mkdir(parents=True, exist_ok=True)
    uv_env = {
        **os.environ,
        "UV_TOOL_DIR": str(tools_dir / "uv"),
        "UV_TOOL_BIN_DIR": str(tools_dir / "bin"),
    }
    for spec, extra in (
        (f"mcp-server-fetch=={FETCH_VERSION}", []),
        ("mcp_massive", ["--from", MASSIVE_SOURCE]),
    ):
        subprocess.run(
            ["uv", "tool", "install", "--compile-bytecode", "--with", MCP_PIN, *extra, spec],
            env=uv_env,
            check=True,
        )
    node_dir = tools_dir / "node"
    node_dir.mkdir(exist_ok=True)
    manifest = {"private": True, "overrides": NODE_OVERRIDES}
    (node_dir / "package.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    subprocess.run(
        [
            "npm",
            "install",
            "--prefix",
            str(node_dir),
            "--save-exact",
            "--omit=dev",
            "--no-audit",
            "--no-fund",
            f"tavily-mcp@{TAVILY_VERSION}",
            f"mcp-memory-libsql@{MEMORY_VERSION}",
        ],
        check=True,
    )
    for name in TOOLS:
        executable = Path(command(name, tools_dir)[0])
        if not executable.exists():
            raise SystemExit(f"{name}: expected {executable} after installing")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python mcp_tools.py <install directory>")
    install(Path(sys.argv[1]))
