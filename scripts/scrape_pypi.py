from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Query https://pypi.org with tag mcp
# Strategy: try https://pypi.org/search/?q=mcp (html) fallback to simple index
# For robustness, query PyPI JSON for known mcp packages and simple index.

PYPI_SIMPLE_URL = "https://pypi.org/simple/"
PYPI_SEARCH_CANDIDATES = [
    "mcp",
    "model-context-protocol",
    "mcp-server",
]
AGENT_ID_RE = re.compile(r"[^a-z0-9_]")


def _sanitize_id(name: str) -> str:
    s = name.lower().replace("-", "_").replace(".", "_")
    s = AGENT_ID_RE.sub("_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s or s[0].isdigit():
        s = "pypi_" + s if s else "pypi_mcp"
    return s[:32]


def _fetch_pypi(timeout: int = 10) -> dict:
    agents: dict = {}
    # Try simple index
    try:
        import urllib.request

        # Fetch simple index html
        try:
            import httpx

            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                resp = client.get(PYPI_SIMPLE_URL, headers={"Accept": "text/html"})
                resp.raise_for_status()
                html = resp.text
        except ImportError:
            with urllib.request.urlopen(PYPI_SIMPLE_URL, timeout=timeout) as r:
                html = r.read().decode("utf-8", errors="ignore")
        except Exception as e:
            print(f"warn: pypi simple fetch failed: {e}", file=sys.stderr)
            html = ""

        # parse href="/simple/<name>/"
        if html:
            names = re.findall(r'href="/simple/([^"/]+)/"', html)
            mcp_names = [n for n in names if "mcp" in n.lower()]
            # limit
            for name in mcp_names[:10]:
                agent_id = _sanitize_id(name)
                if agent_id in {"cursor", "opencode", "claude_code", "zed", "windsurf", "vscode"}:
                    agent_id = f"pypi_{agent_id}"
                if agent_id in agents:
                    continue
                # try to fetch package json for description
                desc = name
                try:
                    pkg_url = f"https://pypi.org/pypi/{name}/json"
                    try:
                        import httpx

                        with httpx.Client(timeout=5) as c:
                            pr = c.get(pkg_url)
                            if pr.status_code == 200:
                                pj = pr.json()
                                desc = pj.get("info", {}).get("summary", name)[:64] or name
                    except ImportError:
                        import urllib.request, json as js

                        with urllib.request.urlopen(pkg_url, timeout=5) as pr:
                            pj = js.loads(pr.read().decode())
                            desc = pj.get("info", {}).get("summary", name)[:64] or name
                except Exception:
                    pass
                agents[agent_id] = {
                    "name": desc[:64],
                    "format": "standard_mcpServers",
                    "paths": {"all": f"~/.config/{agent_id}/mcp.json"},
                }
                if len(agents) >= 10:
                    break
            print(f"pypi: simple index found {len(mcp_names)} mcp names, filtered {len(agents)}", file=sys.stderr)
        # fallback: try known candidates via json
        if not agents:
            for cand in PYPI_SEARCH_CANDIDATES:
                try:
                    url = f"https://pypi.org/pypi/{cand}/json"
                    try:
                        import httpx

                        with httpx.Client(timeout=5) as c:
                            r = c.get(url)
                            if r.status_code != 200:
                                continue
                            info = r.json().get("info", {})
                            name = info.get("name", cand)
                    except ImportError:
                        import urllib.request, json as js

                        with urllib.request.urlopen(url, timeout=5) as r:
                            info = js.loads(r.read().decode()).get("info", {})
                            name = info.get("name", cand)
                    agent_id = _sanitize_id(name)
                    if agent_id not in agents and agent_id not in {"cursor", "opencode", "claude_code", "zed", "windsurf", "vscode"}:
                        agents[agent_id] = {
                            "name": info.get("summary", name)[:64] or name,
                            "format": "standard_mcpServers",
                            "paths": {"all": f"~/.config/{agent_id}/mcp.json"},
                        }
                except Exception:
                    continue
    except Exception as exc:
        print(f"warn: pypi scrape error: {exc}", file=sys.stderr)
    return agents


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape PyPI for MCP packages")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    agents = _fetch_pypi()
    output = {"agents": agents}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(agents)} agents to {args.out}")


if __name__ == "__main__":
    main()
