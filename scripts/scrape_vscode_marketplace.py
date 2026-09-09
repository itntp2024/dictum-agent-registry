from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Query https://marketplace.visualstudio.com/_apis/public/gallery with filter mcp
# API: POST https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery
# Body: {"filters":[{"criteria":[{"filterType":10,"value":"mcp"}],"pageSize":20}]}

MARKETPLACE_URL = "https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery"
AGENT_ID_RE = re.compile(r"[^a-z0-9_]")


def _sanitize_id(name: str) -> str:
    s = name.lower().replace("-", "_").replace(".", "_").replace(" ", "_")
    s = AGENT_ID_RE.sub("_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s or s[0].isdigit():
        s = "vscode_" + (s or "mcp")
    return s[:32]


def _fetch_vscode(timeout: int = 10) -> dict:
    agents: dict = {}
    try:
        payload = {
            "filters": [
                {
                    "criteria": [{"filterType": 10, "value": "mcp"}],
                    "pageSize": 20,
                    "pageNumber": 1,
                }
            ],
            "assetTypes": [],
            "flags": 0x1,
        }
        data = None
        try:
            import httpx

            with httpx.Client(timeout=timeout) as client:
                resp = client.post(
                    MARKETPLACE_URL,
                    json=payload,
                    headers={"Accept": "application/json;api-version=3.0-preview.1", "Content-Type": "application/json"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                else:
                    print(f"warn: vscode marketplace status {resp.status_code} {resp.text[:200]}", file=sys.stderr)
        except ImportError:
            import urllib.request

            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                MARKETPLACE_URL,
                data=body,
                headers={"Accept": "application/json;api-version=3.0-preview.1", "Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print(f"warn: vscode fetch failed: {e}", file=sys.stderr)
            data = None

        if not data:
            return agents

        results = data.get("results", []) if isinstance(data, dict) else []
        for result in results:
            extensions = result.get("extensions", []) if isinstance(result, dict) else []
            for ext in extensions:
                publisher = ext.get("publisher", {}).get("publisherName", "") if isinstance(ext.get("publisher"), dict) else ""
                ext_name = ext.get("extensionName", "") if isinstance(ext, dict) else ""
                full = f"{publisher}.{ext_name}" if publisher and ext_name else ext.get("extensionName", "vscode-mcp")
                display = ext.get("displayName", full) if isinstance(ext, dict) else full
                # filter: must contain mcp in name or tags
                text = f"{full} {display}".lower()
                if "mcp" not in text:
                    continue
                agent_id = _sanitize_id(full)
                if agent_id in {"cursor", "opencode", "claude_code", "zed", "windsurf", "vscode"}:
                    agent_id = f"vscode_{agent_id}"
                    n = 1
                    base = agent_id
                    while agent_id in agents:
                        agent_id = f"{base}_{n}"
                        n += 1
                if agent_id in agents:
                    continue
                # use unique path per extension to avoid duplicate lintas-platform error (vscode base uses ~/.vscode/mcp.json)
                agents[agent_id] = {
                    "name": display[:64] or full[:64],
                    "format": "standard_mcpServers",
                    "paths": {"all": f"~/.vscode/extensions/{agent_id}/mcp.json"},
                }
                if len(agents) >= 10:
                    break
            if len(agents) >= 10:
                break
        print(f"vscode: found {len(agents)} agents", file=sys.stderr)
    except Exception as exc:
        print(f"warn: vscode scrape error: {exc}", file=sys.stderr)
    return agents


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape VSCode Marketplace for MCP extensions")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    agents = _fetch_vscode()
    output = {"agents": agents}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(agents)} agents to {args.out}")


if __name__ == "__main__":
    main()
