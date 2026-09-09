from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Query https://registry.npmjs.org/-/v1/search?text=mcp and filter keyword model-context-protocol
# Output: {"agents": {id: {name, format, paths}}}

NPM_SEARCH_URL = "https://registry.npmjs.org/-/v1/search?text=mcp&size=20"
AGENT_ID_RE = re.compile(r"[^a-z0-9_]")


def _sanitize_id(name: str) -> str:
    # npm package name -> agent id lower snake
    s = name.lower().replace("@", "").replace("/", "_").replace("-", "_")
    s = AGENT_ID_RE.sub("_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = "npm_mcp"
    # ensure starts with letter
    if s[0].isdigit():
        s = "npm_" + s
    return s[:32]


def _fetch_npm(timeout: int = 10) -> dict:
    agents: dict = {}
    try:
        # prefer httpx, fallback to urllib
        try:
            import httpx

            with httpx.Client(timeout=timeout) as client:
                resp = client.get(NPM_SEARCH_URL, headers={"Accept": "application/json"})
                resp.raise_for_status()
                data = resp.json()
        except ImportError:
            import urllib.request

            with urllib.request.urlopen(NPM_SEARCH_URL, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print(f"warn: npm fetch failed: {e}", file=sys.stderr)
            return agents

        objects = data.get("objects", []) if isinstance(data, dict) else []
        for obj in objects:
            pkg = obj.get("package", {}) if isinstance(obj, dict) else {}
            name = pkg.get("name", "")
            keywords = pkg.get("keywords", []) or []
            description = pkg.get("description", "") or ""
            # filter keyword model-context-protocol or mcp
            kw_lower = [k.lower() for k in keywords if isinstance(k, str)]
            text = f"{name} {description} {' '.join(kw_lower)}".lower()
            if "model-context-protocol" not in kw_lower and "mcp" not in kw_lower and "mcp" not in text:
                continue
            agent_id = _sanitize_id(name)
            # avoid collision with existing 6 agents
            if agent_id in {"cursor", "opencode", "claude_code", "zed", "windsurf", "vscode"}:
                agent_id = f"npm_{agent_id}"
                # ensure unique
                base = agent_id
                n = 1
                while agent_id in agents:
                    agent_id = f"{base}_{n}"
                    n += 1
            # map to standard_mcpServers with generic path
            agents[agent_id] = {
                "name": name[:64],
                "format": "standard_mcpServers",
                "paths": {"all": f"~/.config/{agent_id}/mcp.json"},
            }
            if len(agents) >= 10:
                break
        print(f"npm: fetched {len(objects)} packages, filtered {len(agents)} agents", file=sys.stderr)
    except Exception as exc:
        print(f"warn: npm scrape error: {exc}", file=sys.stderr)
    return agents


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape npm registry for MCP packages")
    parser.add_argument("--out", type=Path, required=True, help="output json path (tmp/scrape_npm.json)")
    args = parser.parse_args()

    agents = _fetch_npm()
    output = {"agents": agents}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(agents)} agents to {args.out}")


if __name__ == "__main__":
    main()
