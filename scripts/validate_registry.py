from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ALLOWED_FORMATS = {"standard_mcpServers", "opencode_mcp", "zed_context_servers"}
AGENT_ID_RE = re.compile(r"^[a-z0-9_]+$")
PATH_START_RE = re.compile(r"^(~|%|/|([A-Za-z]:))")


def validate(path: Path) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "version" in data and isinstance(data["version"], str), "missing version"
    assert "updated_at" in data and isinstance(data["updated_at"], str), "missing updated_at"
    agents = data.get("agents")
    assert isinstance(agents, dict) and agents, "agents must be non-empty object"
    for agent_id, meta in sorted(agents.items()):
        assert AGENT_ID_RE.match(agent_id), f"invalid agent id {agent_id}"
        assert isinstance(meta.get("name"), str) and meta["name"].strip(), f"{agent_id} missing name"
        assert meta.get("format") in ALLOWED_FORMATS, f"{agent_id} invalid format"
        paths = meta.get("paths")
        assert isinstance(paths, dict) and paths, f"{agent_id} missing paths"
        for plat, tmpl in paths.items():
            assert isinstance(tmpl, str) and tmpl.strip(), f"{agent_id} path {plat} empty"
            assert PATH_START_RE.match(tmpl) or tmpl.startswith("~"), f"{agent_id} path {plat} must start with ~ % / or drive"
    # duplicate path check
    seen = {}
    for agent_id, meta in agents.items():
        for plat, tmpl in meta["paths"].items():
            key = (plat, tmpl)
            if key in seen:
                print(f"warning: duplicate path {tmpl} for {plat} in {agent_id} and {seen[key]}", file=sys.stderr)
            seen[key] = agent_id
    print(f"Registry {path} valid: {len(agents)} agents")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    sys.exit(validate(args.input))


if __name__ == "__main__":
    main()
