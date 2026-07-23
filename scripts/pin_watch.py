#!/usr/bin/env python3
"""Pin watch: report-only drift check for pinned dependencies.

For each pin in the manifest: query PyPI for the latest version and (optionally)
gh for a watched upstream issue's state. NEVER bumps anything — a version bump
is a deliberate owner-triggered re-validation.

Usage: pin_watch.py MANIFEST.json   (reads manifest["pins"]; JSON output)
Exit codes: 0 always (informational lane) unless the manifest is unreadable (2).
"""
import argparse
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

_NUM_RE = re.compile(r"^\d+")


def _numeric_prefix_tuple(version):
    parts = []
    for seg in version.split("."):
        m = _NUM_RE.match(seg)
        if not m:
            return tuple(parts) if parts else None
        parts.append(int(m.group()))
    return tuple(parts)


def assess(pinned, latest):
    """CURRENT / BEHIND / AHEAD-OF-INDEX / UNKNOWN."""
    a, b = _numeric_prefix_tuple(pinned), _numeric_prefix_tuple(latest)
    if a is None or b is None:
        return "UNKNOWN"
    if a == b:
        return "CURRENT"
    return "BEHIND" if a < b else "AHEAD-OF-INDEX"


def latest_from_pypi_payload(payload):
    try:
        return payload["info"]["version"]
    except (KeyError, TypeError):
        return None


def fetch_latest(package, timeout=10):
    url = f"https://pypi.org/pypi/{package}/json"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return latest_from_pypi_payload(json.load(resp))
    except Exception:
        return None


def parse_issue_ref(ref):
    m = re.match(r"^([\w.-]+)/([\w.-]+)#(\d+)$", ref or "")
    return (m.group(1), m.group(2), int(m.group(3))) if m else None


def fetch_issue_state(ref, timeout=15):
    parsed = parse_issue_ref(ref)
    if not parsed:
        return None
    owner, repo, num = parsed
    try:
        out = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo}/issues/{num}", "--jq", ".state"],
            capture_output=True, text=True, timeout=timeout)
        return out.stdout.strip() or None if out.returncode == 0 else None
    except Exception:
        return None


def build_row(pin, latest, issue_state):
    pkg, pinned = pin["package"], pin["pinned"]
    if latest is None:
        assessment = "UNKNOWN"
        detail = f"{pkg}=={pinned}; PyPI unreachable or no data — re-run to confirm"
    else:
        assessment = assess(pinned, latest)
        detail = f"{pkg} pinned {pinned}, latest on PyPI {latest}"
        if assessment == "BEHIND":
            detail += " — re-validate before any bump (owner decision)"
    row = {"package": pkg, "pinned": pinned, "latest": latest,
           "assessment": assessment, "detail": detail}
    if pin.get("issue") or issue_state is not None:
        row["issue"] = pin.get("issue")
        row["issue_state"] = issue_state or "unknown"
        if issue_state == "closed":
            ref = pin.get("issue") or "watched issue"
            row["detail"] += f"; watched issue {ref} is CLOSED upstream"
    return row


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("manifest")
    args = ap.parse_args(argv)
    try:
        manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8-sig"))
    except Exception as e:
        print(f"manifest unreadable: {e}", file=sys.stderr)
        return 2
    rows = []
    for pin in manifest.get("pins", []):
        latest = fetch_latest(pin["package"])
        issue_state = fetch_issue_state(pin.get("issue")) if pin.get("issue") else None
        rows.append(build_row(pin, latest, issue_state))
    print(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
