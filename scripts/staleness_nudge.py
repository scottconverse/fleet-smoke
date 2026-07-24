#!/usr/bin/env python3
"""SessionStart staleness nudge: print a one-line reminder when /fleet-smoke
hasn't run in max_age_days (stamp file mtime). Silent when fresh.

Deliberately never fails (exit 0 always, errors swallowed) — a broken nudge
must never break session start.

Usage: staleness_nudge.py MANIFEST.json [--max-age-days 7]
"""
import argparse
import json
import sys
import time
from pathlib import Path


def nudge_message(manifest_path, max_age_days=7, now=None):
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8-sig"))
        stamp = Path(manifest["stamp_file"])
        if not stamp.exists():
            return ("fleet-smoke: never run on this machine (no stamp) — "
                    "run /fleet-smoke to baseline fleet health.")
        age_days = ((now or time.time()) - stamp.stat().st_mtime) / 86400
        if age_days > max_age_days:
            return (f"fleet-smoke: last run {int(age_days)} days ago "
                    f"(threshold {max_age_days}) — run /fleet-smoke.")
        return None
    except Exception:
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manifest")
    ap.add_argument("--max-age-days", type=int, default=7)
    args = ap.parse_args(argv)
    msg = nudge_message(args.manifest, args.max_age_days)
    if msg:
        print(msg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
