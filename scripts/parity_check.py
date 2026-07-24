#!/usr/bin/env python3
"""Parity checks for rules that live in more than one copy.

Two modes:
  shared-blocks  compare <!-- SHARED-BLOCK: id --> regions across N files
  identical      whole-file comparison (line-ending / trailing-ws tolerant)

Exit 0 = all PASS, 1 = any FAIL, 2 = usage/marker error. Output is JSON.
"""
import argparse
import json
import re
import sys
from pathlib import Path

OPEN_RE = re.compile(r"<!--\s*SHARED-BLOCK:\s*(?P<id>[\w.-]+)\s*-->")
CLOSE_RE = re.compile(r"<!--\s*/SHARED-BLOCK:\s*(?P<id>[\w.-]+)\s*-->")


class MarkerError(Exception):
    pass


def _normalize(text):
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines)


def extract_blocks(text):
    """Return {block_id: normalized_body} for every marked block in text."""
    text = _normalize(text)
    blocks = {}
    open_id, buf = None, []
    for lineno, line in enumerate(text.split("\n"), 1):
        m_open, m_close = OPEN_RE.search(line), CLOSE_RE.search(line)
        if m_open:
            if open_id is not None:
                raise MarkerError(f"line {lineno}: nested SHARED-BLOCK inside '{open_id}'")
            open_id, buf = m_open.group("id"), []
        elif m_close:
            if open_id is None or m_close.group("id") != open_id:
                raise MarkerError(f"line {lineno}: close marker without matching open")
            blocks[open_id] = "\n".join(buf).strip("\n")
            open_id = None
        elif open_id is not None:
            buf.append(line)
    if open_id is not None:
        raise MarkerError(f"SHARED-BLOCK '{open_id}' never closed")
    return blocks


def _canonical(body, substitutions=None, collapse_ws=False):
    """Optionally collapse whitespace runs to single spaces (kills wrapping
    differences), THEN apply sanctioned substitutions — collapse must come
    first so a mapped phrase matches even when the source wraps it across
    lines; map entries are therefore written single-spaced."""
    if collapse_ws:
        body = " ".join(body.split())
    for sub in substitutions or []:
        body = body.replace(sub["from"], sub["to"])
    return body


def compare_shared_blocks(files, substitutions=None, collapse_ws=False):
    """Compare marked blocks across files. One result row per block id seen anywhere.

    Zero blocks anywhere is a FAIL, never a vacuous pass. `substitutions` is a
    list of {"from", "to"} sanctioned rewrites (the ONLY blessed differences
    between copies); `collapse_ws` tolerates different line wrapping.
    """
    per_file = {}
    for f in files:
        f = Path(f)
        if not f.exists():
            return [{"block": "(source)", "status": "FAIL",
                     "detail": f"file missing: {f}"}]
        per_file[f] = extract_blocks(f.read_text(encoding="utf-8"))

    all_ids = sorted({bid for blocks in per_file.values() for bid in blocks})
    if not all_ids:
        return [{"block": "(none)", "status": "FAIL",
                 "detail": "no SHARED-BLOCK markers found in any input file — "
                           "nothing was compared"}]

    results = []
    for bid in all_ids:
        missing = [f.name for f, blocks in per_file.items() if bid not in blocks]
        if missing:
            results.append({"block": bid, "status": "FAIL",
                            "detail": f"missing in: {', '.join(missing)}"})
            continue
        bodies = {f: _canonical(blocks[bid], substitutions, collapse_ws)
                  for f, blocks in per_file.items()}
        canonical = next(iter(bodies.values()))
        drifted = [f.name for f, body in bodies.items() if body != canonical]
        if drifted and len(set(bodies.values())) > 1:
            names = ", ".join(f.name for f in bodies)
            results.append({"block": bid, "status": "FAIL",
                            "detail": f"content differs across: {names}"})
        else:
            results.append({"block": bid, "status": "PASS", "detail": ""})
    return results


def compare_identical(files):
    """Whole-file identity (after newline/trailing-ws normalization)."""
    texts = {}
    for f in files:
        f = Path(f)
        if not f.exists():
            return {"status": "FAIL", "detail": f"file missing: {f}"}
        texts[f] = _normalize(f.read_text(encoding="utf-8"))
    names = [f.name for f in texts]
    first_f, first_t = next(iter(texts.items()))
    for f, t in texts.items():
        if t != first_t:
            for i, (a, b) in enumerate(zip(first_t.split("\n"), t.split("\n")), 1):
                if a != b:
                    return {"status": "FAIL",
                            "detail": f"{first_f.name} vs {f.name} first differ at line {i}"}
            return {"status": "FAIL",
                    "detail": f"{first_f.name} vs {f.name} differ in length"}
    return {"status": "PASS", "detail": f"identical: {', '.join(names)}"}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=["shared-blocks", "identical"], required=True)
    ap.add_argument("--substitutions", metavar="JSON_FILE",
                    help="sanctioned {from,to} rewrites (shared-blocks mode)")
    ap.add_argument("--collapse-ws", action="store_true",
                    help="tolerate line-wrapping differences (shared-blocks mode)")
    ap.add_argument("files", nargs="+")
    args = ap.parse_args(argv)
    if len(args.files) < 2:
        print("need at least two files", file=sys.stderr)
        return 2
    substitutions = None
    if args.substitutions:
        substitutions = json.loads(
            Path(args.substitutions).read_text(encoding="utf-8-sig"))
    try:
        if args.mode == "shared-blocks":
            results = compare_shared_blocks(args.files, substitutions=substitutions,
                                            collapse_ws=args.collapse_ws)
        else:
            results = [compare_identical(args.files)]
    except MarkerError as e:
        print(json.dumps([{"block": "(markers)", "status": "FAIL", "detail": str(e)}]))
        return 2
    print(json.dumps(results, indent=2))
    return 1 if any(r["status"] != "PASS" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
