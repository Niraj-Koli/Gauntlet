# 0006: Images built once and configured at runtime

**Status:** accepted

## Context

In GitOps, the image CI builds for a commit is the one that runs in every environment, and only configuration differs. Two parts of the dashboard broke that:
- `NEXT_PUBLIC_*` variables are inlined into the browser bundle at build time.
- `next.config.ts` rewrites, used to forward `/api/v1` to the API, are fixed at build time in standalone output.

On the backend, the researcher's MCP servers were fetched with `uvx` and `npx` on first use. So a run's code depended on what a package registry served that day.

## Decision

**Web:**
- A `proxy.ts` forwards `/api/v1` to `API_URL`, read for each request.
- The root layout renders per request and passes `SUPABASE_URL` and `SUPABASE_ANON_KEY` from the server's environment to the client, through context.
- No `NEXT_PUBLIC_*` variables remain.

**API:** `mcp_tools.py` holds the pinned version of each third-party MCP server. The image installs them at build time into `MCP_TOOLS_DIR`, and runs start them from there. Outside containers, they still run through `uvx` and `npx`.

## Consequences

- **One image per commit:** the same images run in compose, the k3d demo and production, configured only by environment. The Helm values say everything that differs.
- **No downloads at run time:** runs make no package downloads, and the tools work with networking switched off. Upgrading a tool is a reviewed code change, and the scanners see the exact versions shipped.
- **A dynamic layout:** the dashboard is rendered per request, so it isn't statically cached. That's fine for a live dashboard.
- **A bigger, slower build:** the API image carries Node and the tools (about 800 MB), and builds take longer.
