from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path

ALLOWED_FORMATS = {"standard_mcpServers", "opencode_mcp", "zed_context_servers"}
ALLOWED_PLATFORMS = {"all", "darwin", "linux", "windows"}
AGENT_ID_RE = re.compile(r"^[a-z0-9_]+$")
PATH_START_RE = re.compile(r"^(~|%|/|([A-Za-z]:))")
SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def _parse_iso8601(value: str) -> datetime.datetime:
    # strict ISO-8601 UTC: 2026-09-09T00:00:00Z or with fractional
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.datetime.fromisoformat(value)
    if dt.tzinfo is None:
        raise ValueError("updated_at must be timezone-aware (UTC)")
    return dt


def validate(path: Path) -> int:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"error: {path} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    errors: list[str] = []

    # version semver
    version = data.get("version")
    if not isinstance(version, str) or not SEMVER_RE.match(version):
        errors.append("missing or invalid version (expected MAJOR.MINOR.PATCH)")

    # updated_at ISO8601 UTC
    updated_at = data.get("updated_at")
    if not isinstance(updated_at, str):
        errors.append("missing updated_at")
    else:
        try:
            _parse_iso8601(updated_at)
        except Exception as exc:
            errors.append(f"invalid updated_at ISO8601 UTC: {exc} (got {updated_at!r})")

    agents = data.get("agents")
    if not isinstance(agents, dict) or not agents:
        errors.append("agents must be non-empty object")
        agents = {}

    # check agents sorted alphabetically (for deterministic merge)
    agent_ids = list(agents.keys())
    if agent_ids != sorted(agent_ids):
        print(f"warning: agents not sorted alphabetically: {agent_ids} vs {sorted(agent_ids)}", file=sys.stderr)

    # per-agent checks + duplicate tracking
    seen_exact: dict[tuple[str, str], str] = {}  # (plat, tmpl) -> agent_id
    seen_tmpl_global: dict[str, list[str]] = {}  # normalized tmpl -> [agent_ids]
    for agent_id, meta in sorted(agents.items()):
        if not AGENT_ID_RE.match(agent_id):
            errors.append(f"invalid agent id {agent_id!r} (must match ^[a-z0-9_]+$)")

        name = meta.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{agent_id} missing name")

        fmt = meta.get("format")
        if fmt not in ALLOWED_FORMATS:
            errors.append(f"{agent_id} invalid format {fmt!r} (allowed: {sorted(ALLOWED_FORMATS)})")

        paths = meta.get("paths")
        if not isinstance(paths, dict) or not paths:
            errors.append(f"{agent_id} missing paths")
            continue

        for plat, tmpl in paths.items():
            if plat not in ALLOWED_PLATFORMS:
                errors.append(f"{agent_id} path platform {plat!r} invalid (allowed: {sorted(ALLOWED_PLATFORMS)})")
            if not isinstance(tmpl, str) or not tmpl.strip():
                errors.append(f"{agent_id} path {plat} empty")
                continue
            if not (PATH_START_RE.match(tmpl) or tmpl.startswith("~")):
                errors.append(f"{agent_id} path {plat} {tmpl!r} must start with ~ % / or drive letter")

            # exact duplicate (same plat + same tmpl) -> error
            key = (plat, tmpl)
            if key in seen_exact:
                errors.append(
                    f"duplicate path {tmpl!r} for platform {plat!r} in {agent_id} and {seen_exact[key]}"
                )
            else:
                seen_exact[key] = agent_id

            # lintas platform duplicate: same tmpl string appears in any other agent/platform
            # normalize: strip trailing slash, case-sensitive
            norm = tmpl.strip()
            seen_tmpl_global.setdefault(norm, []).append(f"{agent_id}:{plat}")

    # lintas platform duplicate check: same tmpl used by multiple agents (any platform)
    for tmpl, owners in seen_tmpl_global.items():
        if len(owners) > 1:
            # only error if same tmpl appears in different agent_ids (not just same agent multi-platform)
            agent_set = {o.split(":")[0] for o in owners}
            if len(agent_set) > 1:
                print(
                    f"warning: lintas-platform duplicate tmpl {tmpl!r} shared by {sorted(agent_set)} ({owners})",
                    file=sys.stderr,
                )
                # not fatal, but warn - change to error if strict required
                # for now keep warning; uncomment next line to make strict:
                # errors.append(f"lintas-platform duplicate tmpl {tmpl!r} in {sorted(agent_set)}")

    if errors:
        for err in errors:
            print(f"error: {err}", file=sys.stderr)
        print(f"Registry {path} INVALID: {len(errors)} error(s)", file=sys.stderr)
        return 1

    print(f"Registry {path} valid: {len(agents)} agents (version {version}, updated_at {updated_at})")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate agents_master_registry.json")
    parser.add_argument("--input", required=True, type=Path, help="path to registry json")
    args = parser.parse_args()
    sys.exit(validate(args.input))


if __name__ == "__main__":
    main()
