from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", nargs="*", default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base", type=Path, required=True)
    args = parser.parse_args()
    # No-op merge for initial version: keep base file unchanged
    # If scrapers produced data, this is where merging would happen
    if not args.base.exists():
        print(f"base {args.base} not found", file=sys.stderr)
        sys.exit(1)
    # Validate base is still valid
    json.loads(args.base.read_text(encoding="utf-8"))
    print(f"merge skipped, keeping {args.base}")


if __name__ == "__main__":
    main()
