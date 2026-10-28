"""The researcher's third-party MCP servers: run on demand, or from an image's install."""

from pathlib import Path

import pytest
from pydantic import SecretStr

from gauntlet import mcp_tools
from gauntlet.mcp_servers import researcher_mcp_servers, trader_mcp_servers


def test_tools_run_through_uvx_and_npx_by_default(settings):
    fetch, search, memory = researcher_mcp_servers(settings, "warren")
    assert fetch.params.command == "uvx"  # pyright: ignore[reportAttributeAccessIssue]
    assert f"mcp-server-fetch=={mcp_tools.FETCH_VERSION}" in fetch.params.args  # pyright: ignore[reportAttributeAccessIssue]
    assert search.params.args == ["-y", f"tavily-mcp@{mcp_tools.TAVILY_VERSION}"]  # pyright: ignore[reportAttributeAccessIssue]
    assert memory.params.command == "npx"  # pyright: ignore[reportAttributeAccessIssue]
    assert memory.params.cwd == str(settings.data_dir)  # pyright: ignore[reportAttributeAccessIssue]


def test_installed_tools_run_from_the_tools_directory(settings, tmp_path):
    settings.mcp_tools_dir = tmp_path / "tools"
    settings.massive_api_key = SecretStr("key")
    fetch, search, memory = researcher_mcp_servers(settings, "warren")
    commands = [Path(server.params.command) for server in (fetch, search, memory)]  # pyright: ignore[reportAttributeAccessIssue]
    assert commands == [
        tmp_path / "tools" / "bin" / "mcp-server-fetch",
        tmp_path / "tools" / "node" / "node_modules" / ".bin" / "tavily-mcp",
        tmp_path / "tools" / "node" / "node_modules" / ".bin" / "mcp-memory-libsql",
    ]
    assert all(server.params.args == [] for server in (fetch, search, memory))  # pyright: ignore[reportAttributeAccessIssue]
    _, massive = trader_mcp_servers(settings, "token")
    assert Path(massive.params.command) == tmp_path / "tools" / "bin" / "mcp_massive"  # pyright: ignore[reportAttributeAccessIssue]
    assert massive.params.env == {"MASSIVE_API_KEY": "key"}  # pyright: ignore[reportAttributeAccessIssue]


def test_every_tool_has_a_pinned_version():
    for on_demand, _ in mcp_tools.TOOLS.values():
        spec = on_demand[-1] if on_demand[0] == "npx" else " ".join(on_demand)
        assert any(pin in spec for pin in ("==", "@v", "@0", "@1", "@2")), spec


def test_install_puts_every_pinned_tool_in_place(tmp_path, monkeypatch):
    commands: list[list[str]] = []

    def fake_run(args, env=None, check=False):
        commands.append(args)
        # What uv and npm would leave behind.
        for name in mcp_tools.TOOLS:
            path = Path(mcp_tools.command(name, tmp_path)[0])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()

    monkeypatch.setattr(mcp_tools.subprocess, "run", fake_run)
    mcp_tools.install(tmp_path)
    uv_installs = [c for c in commands if c[:3] == ["uv", "tool", "install"]]
    assert any(f"mcp-server-fetch=={mcp_tools.FETCH_VERSION}" in c for c in uv_installs)
    assert any(mcp_tools.MASSIVE_SOURCE in c for c in uv_installs)
    [npm] = [c for c in commands if c[0] == "npm"]
    assert f"tavily-mcp@{mcp_tools.TAVILY_VERSION}" in npm
    assert f"mcp-memory-libsql@{mcp_tools.MEMORY_VERSION}" in npm


def test_install_fails_when_a_tool_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_tools.subprocess, "run", lambda *a, **k: None)
    with pytest.raises(SystemExit, match="expected"):
        mcp_tools.install(tmp_path)
