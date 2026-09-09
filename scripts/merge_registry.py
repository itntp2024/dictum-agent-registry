from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path


def _load_agents(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return {}
        data = json.loads(text)
        # support both {"agents": {...}} and flat {...}
        if isinstance(data, dict) and "agents" in data and isinstance(data["agents"], dict):
            return data["agents"]
        if isinstance(data, dict):
            # heuristic: if keys look like agent entries with format/paths
            # treat as agents dict directly if no top-level version
            if "version" not in data and "agents" not in data:
                # could be {"cursor": {...}} style
                return data
        return {}
    except Exception as exc:
        print(f"warn: failed to load {path}: {exc}", file=sys.stderr)
        return {}


def _bump_version(current: str, added_agents: bool, added_format: bool) -> str:
    try:
        major, minor, patch = map(int, current.split("."))
    except Exception:
        print(f"warn: invalid version {current!r}, resetting to 1.0.0", file=sys.stderr)
        major, minor, patch = 1, 0, 0
    if added_format:
        # minor bump, patch reset
        minor += 1
        patch = 0
    elif added_agents:
        patch += 1
    return f"{major}.{minor}.{patch}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge scraper outputs into registry")
    parser.add_argument("--inputs", nargs="*", default=[], help="input json files from scrapers (tmp/*.json)")
    parser.add_argument("--output", type=Path, required=True, help="output registry path")
    parser.add_argument("--base", type=Path, required=True, help="base registry path (existing agents_master_registry.json)")
    args = parser.parse_args()

    if not args.base.exists():
        print(f"base {args.base} not found", file=sys.stderr)
        sys.exit(1)

    try:
        base_data = json.loads(args.base.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"base {args.base} invalid json: {exc}", file=sys.stderr)
        sys.exit(1)

    base_agents: dict = base_data.get("agents", {}) if isinstance(base_data.get("agents"), dict) else {}
    base_version: str = str(base_data.get("version", "1.0.0"))
    base_formats = {meta.get("format") for meta in base_agents.values() if isinstance(meta, dict) and "format" in meta}

    # collect all input agents
    merged_agents: dict = dict(base_agents)  # start with base
    discovered: dict = {}
    for inp in args.inputs:
        p = Path(inp)
        if not p.exists():
            print(f"skip missing input {p}", file=sys.stderr)
            continue
        # handle glob pattern expansion already done by shell; if inputs contains literal "tmp/*.json" when no files, skip
        if "*" in str(p):
            continue
        agents = _load_agents(p)
        if not agents:
            print(f"input {p} empty or no agents", file=sys.stderr)
            continue
        for agent_id, meta in agents.items():
            if not isinstance(meta, dict):
                continue
            # basic validation: require name/format/paths
            if "name" not in meta or "format" not in meta or "paths" not in meta:
                print(f"warn: skip incomplete agent {agent_id!r} from {p}", file=sys.stderr)
                continue
            discovered[agent_id] = meta
            if agent_id not in merged_agents:
                merged_agents[agent_id] = meta
                print(f"merge: adding new agent {agent_id} from {p}")
            else:
                # if same id but different format/paths, keep base but log
                existing = merged_agents[agent_id]
                if existing != meta:
                    print(f"info: agent {agent_id} from {p} differs from base, keeping base (base={existing.get('format')} vs new={meta.get('format')})", file=sys.stderr)

    # sort alphabetically
    sorted_agents = {k: merged_agents[k] for k in sorted(merged_agents.keys())}

    # detect changes for version bump
    added_agents = any(k not in base_agents for k in sorted_agents)
    merged_formats = {meta.get("format") for meta in sorted_agents.values() if isinstance(meta, dict)}
    added_format = bool(merged_formats - base_formats)

    new_version = base_version
    if added_agents or added_format:
        new_version = _bump_version(base_version, added_agents, added_format)
        bump_type = "minor" if added_format else "patch"
        print(f"version bump {base_version} -> {new_version} ({bump_type}: added_agents={added_agents} added_format={added_format})")
    else:
        print("no new agents or formats, version unchanged")

    # updated_at now UTC ISO8601
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    output_data = {
        "version": new_version,
        "updated_at": now,
        "agents": sorted_agents,
    }

    # if output == base and no changes, we still update updated_at? spec says set updated_at ISO8601 UTC always when merge runs
    # but to keep idempotent, only update if changed; we'll update anyway if any merge attempted
    # compare with base file content sorted
    base_sorted = {k: base_agents[k] for k in sorted(base_agents.keys())}
    base_normalized = {"version": base_version, "updated_at": base_data.get("updated_at"), "agents": base_sorted}
    # if agents equal and version not bumped, we still update updated_at (per spec)
    # write output
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"merged {len(sorted_agents)} agents -> {args.output} (version {new_version}, updated_at {now})")
    # exit 0
    # validation hint
    if len(sorted_agents) != len(base_agents):
        print(f"merged: {len(sorted_agents)-len(base_agents):+d} agents vs base")


if __name__ == "__main__":
    main()
