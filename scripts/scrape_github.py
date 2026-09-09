from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Query https://api.github.com/search/repositories?q=topic:mcp-server

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories?q=topic:mcp-server&per_page=20&sort=stars&order=desc"
AGENT_ID_RE = re.compile(r"[^a-z0-9_]")


def _sanitize_id(name: str) -> str:
    # repo full_name like owner/repo -> owner_repo
    s = name.lower().replace("/", "_").replace("-", "_").replace(".", "_")
    s = AGENT_ID_RE.sub("_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s or s[0].isdigit():
        s = "gh_" + (s or "mcp")
    return s[:32]


def _fetch_github(timeout: int = 10) -> dict:
    agents: dict = {}
    try:
        headers = {"Accept": "application/vnd.github+json"}
        token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        data = None
        try:
            import httpx

            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                resp = client.get(GITHUB_SEARCH_URL, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                elif resp.status_code == 403:
                    print(f"warn: github rate limited {resp.text[:200]}", file=sys.stderr)
                    return agents
                else:
                    print(f"warn: github status {resp.status_code} {resp.text[:200]}", file=sys.stderr)
                    return agents
        except ImportError:
            import urllib.request

            req = urllib.request.Request(GITHUB_SEARCH_URL, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print(f"warn: github fetch failed: {e}", file=sys.stderr)
            return agents

        if not data or not isinstance(data, dict):
            return agents
        items = data.get("items", []) if isinstance(data.get("items"), list) else []
        for item in items:
            full_name = item.get("full_name", "") if isinstance(item, dict) else ""
            description = item.get("description", "") or ""
            topics = item.get("topics", []) or []
            # filter topic mcp-server
            has_topic = any("mcp" in str(t).lower() for t in topics)
            text = f"{full_name} {description}".lower()
            if not has_topic and "mcp" not in text:
                continue
            agent_id = _sanitize_id(full_name or item.get("name", "gh_mcp"))
            if agent_id in {"cursor", "opencode", "claude_code", "zed", "windsurf", "vscode"}:
                agent_id = f"gh_{agent_id}"
            if agent_id in agents:
                # ensure unique
                base = agent_id
                n = 1
                while agent_id in agents:
                    agent_id = f"{base}_{n}"
                    n += 1
            # map repo to agent; use standard format with generic path
            # For github mcp servers, they are typically npm/pip packages, but we map to standard
            agents[agent_id] = {
                "name": full_name[:64] or "github-mcp",
                "format": "standard_mcpServers",
                "paths": {"all": f"~/.config/{agent_id}/mcp.json"},
            }
            if len(agents) >= 10:
                break
        print(f"github: found {len(items)} repos, filtered {len(agents)} agents", file=sys.stderr)
    except Exception as exc:
        print(f"warn: github scrape error: {exc}", file=sys.stderr)
    return agents


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape GitHub for MCP server repos")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    agents = _fetch_github()
    output = {"agents": agents}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(agents)} agents to {args.out}")


if __name__ == "__main__":
    main()
