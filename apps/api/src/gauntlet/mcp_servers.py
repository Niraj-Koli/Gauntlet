"""The MCP servers each trader and researcher connects to."""

from agents.mcp import (
    MCPServer,
    MCPServerStdio,
    MCPServerStreamableHttp,
    create_static_tool_filter,
)

from .mcp_tools import command
from .settings import Settings

TIMEOUT = 120


def _http(name: str, url: str, token: str) -> MCPServerStreamableHttp:
    return MCPServerStreamableHttp(
        {"url": url, "headers": {"Authorization": f"Bearer {token}"}, "timeout": 30},
        name=name,
        client_session_timeout_seconds=TIMEOUT,
    )


def trader_mcp_servers(settings: Settings, token: str) -> list[MCPServer]:
    """The trader's MCP servers: its account and market data, both hosted by the API and
    authenticated with the run's token. (Notifications are an in-process tool.)"""
    servers: list[MCPServer] = [_http("accounts_server", settings.mcp_accounts_url, token)]
    if massive_key := settings.secret("massive_api_key"):
        # With a key, hand the agent Massive's own market data server, run locally over stdio.
        program, args = command("massive", settings.mcp_tools_dir)
        servers.append(
            MCPServerStdio(
                {"command": program, "args": args, "env": {"MASSIVE_API_KEY": massive_key}},
                client_session_timeout_seconds=TIMEOUT,
            )
        )
    else:
        servers.append(_http("market_server", settings.mcp_market_url, token))
    return servers


def researcher_mcp_servers(settings: Settings, name: str) -> list[MCPServer]:
    """The researcher's MCP servers: Fetch, Tavily web search and Memory.

    Tavily's server offers several tools; we restrict it to web search so the
    researcher reaches for plain search rather than its heavier crawl or deep-research tools.
    """
    tools_dir = settings.mcp_tools_dir
    program, args = command("fetch", tools_dir)
    fetch = MCPServerStdio({"command": program, "args": args}, client_session_timeout_seconds=TIMEOUT)
    program, args = command("tavily", tools_dir)
    search = MCPServerStdio(
        {
            "command": program,
            "args": args,
            "env": {"TAVILY_API_KEY": settings.secret("tavily_api_key") or ""},
        },
        client_session_timeout_seconds=TIMEOUT,
        tool_filter=create_static_tool_filter(allowed_tool_names=["tavily_search"]),
    )
    # The memory URL is relative, so run the server from the data directory.
    settings.memory_dir.mkdir(parents=True, exist_ok=True)
    program, args = command("memory", tools_dir)
    memory = MCPServerStdio(
        {
            "command": program,
            "args": args,
            "env": {"LIBSQL_URL": f"file:./memory/{name}.db"},
            "cwd": str(settings.data_dir),
        },
        client_session_timeout_seconds=TIMEOUT,
    )
    return [fetch, search, memory]
