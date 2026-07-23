#!/usr/bin/env python3
"""Skill inventory: enumerate skills dirs, flag duplicate names, dead junctions,
folders without SKILL.md, and SKILL.md files without parseable frontmatter.

Usage: skill_inventory.py DIR [DIR ...]   (JSON output, exit 1 on any problem)
"""
import argparse
import json
import re
import sys
from pathlib import Path

_NAME_RE = re.compile(r"^name:\s*(\S+)", re.MULTILINE)


def _frontmatter_name(skill_md):
    text = skill_md.read_text(encoding="utf-8-sig", errors="replace")
    if not text.startswith("---"):
        return None
    end = text.find("---", 3)
    if end == -1:
        return None
    m = _NAME_RE.search(text[3:end])
    return m.group(1) if m else None


def _triage(entry):
    """'dir' | 'file' | 'dead-link' for a directory entry.

    A junction/symlink whose target vanished still shows up in iterdir() but
    is neither a dir nor a file (stat on it fails / resolves to nothing).
    """
    if entry.is_dir():
        return "dir"
    if entry.is_file():
        return "file"
    return "dead-link"


def _collect(folder, skills, problems, seen_roots):
    """Record folder if it's a skill; recurse into a nested skills/ dir (plugin layout)."""
    if folder in seen_roots:
        return
    seen_roots.add(folder)
    skill_md = folder / "SKILL.md"
    if skill_md.exists():
        name = _frontmatter_name(skill_md)
        if name is None:
            problems.append({"kind": "bad-frontmatter", "path": str(skill_md),
                             "detail": "no parseable frontmatter name"})
            name = folder.name
        skills.append({"name": name, "path": str(folder)})
    else:
        nested = folder / "skills"
        has_nested = nested.is_dir() and any(
            (d / "SKILL.md").exists() for d in nested.iterdir() if d.is_dir())
        if not has_nested:
            problems.append({"kind": "no-skill-md", "path": str(folder),
                             "detail": "folder in skills dir with no SKILL.md "
                                       "and no nested skills/"})
    nested = folder / "skills"
    if nested.is_dir():
        for sub in sorted(nested.iterdir()):
            kind = _triage(sub)
            if kind == "dir":
                _collect(sub, skills, problems, seen_roots)
            elif kind == "dead-link":
                problems.append({"kind": "dead-link", "path": str(sub),
                                 "detail": "entry exists but target is gone"})


def scan(dirs):
    skills, problems, seen = [], [], set()
    for root in dirs:
        root = Path(root)
        if not root.is_dir():
            problems.append({"kind": "missing-dir", "path": str(root),
                             "detail": "skills dir does not exist"})
            continue
        for folder in sorted(root.iterdir()):
            kind = _triage(folder)
            if kind == "dir":
                _collect(folder, skills, problems, seen)
            elif kind == "dead-link":
                problems.append({"kind": "dead-link", "path": str(folder),
                                 "detail": "entry exists but target is gone"})

    by_name = {}
    for s in skills:
        by_name.setdefault(s["name"], []).append(s["path"])
    duplicates = [{"name": n, "paths": ps} for n, ps in sorted(by_name.items())
                  if len(ps) > 1]
    return {"skills": skills, "duplicates": duplicates, "problems": problems}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("dirs", nargs="+")
    args = ap.parse_args(argv)
    report = scan(args.dirs)
    print(json.dumps(report, indent=2))
    return 1 if (report["duplicates"] or report["problems"]) else 0


if __name__ == "__main__":
    sys.exit(main())
