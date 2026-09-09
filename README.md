# dictum-agent-registry

Public catalog for Dictum MCP agent configurations. This repository is updated automatically by GitHub Actions and consumed by `dictum link` on local developer machines. It contains no secrets, no private gateway code, and no user data.

## Purpose

The registry maps agent identifiers to standardized MCP configuration formats and platform-specific paths. The private gateway `arbiterAI` fetches this file at `dictum link` time to detect installed agents and safely inject the `arbiter-gateway` MCP entry without manual editing.

Separation of repositories:

- Private `arbiterAI`: evaluation gateway daemon, SQLite ledger, hash-chained checkpoints, evidence verification, Text Registry, MCP bridge `dictum-mcp`, and CLI `dictum`. Requires `ARBITER_API_KEY` and holds `~/.dictum/dictum.db`.
- Public `dictum-agent-registry`: this repository, only the catalog and scraper workflow. Safe to publish and share raw URL.

```
Private (arbiterAI)                Public (dictum-agent-registry)
----------------                  -------------------------------
app/api, app/engines, app/db  ->  agents_master_registry.json  <-  dictum link (HTTP GET)
dictum_mcp/server.py               .github/workflows/scrape.yml
cli/dictum.py  ---------------->   README.md, schema docs
```

## File

Single source of truth: `agents_master_registry.json` at repository root.

Schema:

```json
{
  "version": "1.0.0",
  "updated_at": "2026-09-09T00:00:00Z",
  "agents": {
    "cursor": {
      "name": "Cursor IDE",
      "format": "standard_mcpServers",
      "paths": {
        "darwin": "~/Library/.../mcp.json",
        "linux": "~/.config/.../mcp.json",
        "windows": "%APPDATA%/.../mcp.json"
      }
    }
  }
}
```

### Top Level

- `version`: string `MAJOR.MINOR.PATCH` of registry schema. Increment `MAJOR` for breaking structure, `MINOR` for new agents, `PATCH` for path or name fixes.
- `updated_at`: ISO 8601 UTC timestamp of last successful scrape. Set by workflow, not manually.
- `agents`: object keyed by stable agent id `^[a-z0-9_]+$` lower snake case.

### Agent Entry

- `name`: human readable display name, e.g. `Cursor IDE`.
- `format`: one of `standard_mcpServers`, `opencode_mcp`, `zed_context_servers`. Determines injection location in local config file.
  - `standard_mcpServers`: top level `mcpServers` object.
  - `opencode_mcp`: `mcp` or `mcpServers` object inside `opencode.jsonc` (JSON with comments).
  - `zed_context_servers`: `context_servers` object inside `settings.json`.
- `paths`: platform to path template. Keys `all` for cross platform, or `darwin`, `linux`, `windows`. Values are path templates containing `~` for home, `%APPDATA%` on Windows, and forward slashes. `dictum link` expands with `os.path.expanduser` and `expandvars`.

### Entry Script

Injected `arbiter-gateway` entry is minimal and deterministic:

```json
{
  "mcpServers": {
    "arbiter-gateway": {
      "command": "python",
      "args": ["-m", "dictum_mcp.server"]
    }
  }
}
```

For `zed_context_servers` the same command and args are placed under `context_servers`.

## Consumption by CLI

`dictum link` performs:

1. Fetch `https://raw.githubusercontent.com/<org>/dictum-agent-registry/main/agents_master_registry.json` with 5 second timeout, fallback to `registry/agents_master_registry.json` bundled in private repo.
2. Resolve platform key `darwin` / `linux` / `windows` via `platform.system`.
3. For each agent, expand path template and check `candidate.exists()` and `candidate.parent.exists()` to classify `FOUND`, `CREATE`, or `SKIP`.
4. If file exists and not `--no-backup`, copy to `candidate.with_suffix(.bak)` once.
5. Read existing JSON with tolerant JSONC stripping for `.jsonc`, inject or merge the gateway entry under the correct top level key, and write formatted JSON with trailing newline.

Dry run `dictum link --dry-run` prints classification without writing. `dictum doctor` verifies `arbiter-gateway` presence per agent.

## Update Workflow

Workflow: `.github/workflows/scrape.yml`

Schedule: daily cron `0 2 * * *` UTC plus `workflow_dispatch` and push to `main` affecting `agents/**`.

Steps:

1. Checkout
2. Setup Python 3.11 and Node 20 for marketplace scrapers
3. Install scraper dependencies `pip install -r scripts/requirements.txt`
4. Run scrapers in `scripts/scrape_npm.py`, `scripts/scrape_pypi.py`, `scripts/scrape_vscode_marketplace.py`, `scripts/scrape_github.py` that produce partial catalogs in `tmp/`
5. Merge via `scripts/merge_registry.py` that validates schema, sorts agents alphabetically, sets `version` patch bump if only additions, and writes `agents_master_registry.json` with `updated_at` now
6. If file changed, commit with message `chore: registry update <date>` and push
7. Tag `v<version>` if `version` changed

Validation performed by merge script:

- `agents_master_registry.json` must be valid JSON and match schema
- Every `paths` value must be non-empty string and start with `~`, `%`, or `/` or contain `:` for Windows drive
- `format` must be known enum
- No duplicate paths across agents on same platform

Example workflow excerpt is provided in `.github/workflows/scrape.yml` with pinned action SHAs.

## Adding a New Agent

1. Fork and branch `feat/agent-<id>`.
2. Edit `agents_master_registry.json`: add key under `agents`, choose stable id, set `name`, `format`, and at least `paths.all` or platform specific paths.
3. Run local validation: `python scripts/validate_registry.py`.
4. Test locally: in private repo run `python -m cli.dictum link --dry-run` and verify `FOUND` detection on your OS.
5. Open pull request. CI runs validation and dry-run link. Maintainer reviews path correctness.
6. On merge to `main`, workflow bumps `version` and updates `updated_at`. Consumers receive update on next `dictum link`.

Do not include secrets, tokens, or private gateway URLs in this repository. The file contains only agent metadata and templated local paths.

## Versioning

- `1.0.0` initial catalog with 6 agents: cursor, opencode, claude_code, zed, windsurf, vscode.
- Patch increments for path fixes.
- Minor increments for new agent additions.
- Major increments for schema changes such as new `format` values or top level keys.

Raw URL stability: `https://raw.githubusercontent.com/<org>/dictum-agent-registry/main/agents_master_registry.json` is immutable per commit and cached by CLI fallback.

## License

MIT. See `LICENSE`. Contributions are accepted under the same license. Scraper scripts retain their own license headers where applicable.
