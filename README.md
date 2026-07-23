# fleet-smoke

A two-minute health check for a Claude Code tool fleet — hooks, plugins, MCP
servers, skills, cross-copy rule parity, and dependency pins — so breakage is
found by a scheduled report instead of mid-task surprise.

## What it checks

| Check | Failure class it catches |
|---|---|
| Hook liveness (tier 1) | hook registered but its script is gone or unparseable — e.g. killed by a client update or a manifest wiring trap |
| MCP/plugin load | server expected but never connected this session (cold-cache races, install-path breakage) |
| Skill inventory | duplicate skill names (nondeterministic resolution), dead junctions, missing/broken SKILL.md frontmatter |
| Parity | a rule that lives in N copies has drifted (SHARED-BLOCK marker diff) or a live skill no longer matches its repo (identical mode) |
| Pin watch | a pinned dependency fell behind PyPI, or a watched upstream issue closed (report-only — never bumps) |
| Staleness stamp | warns at session start when the smoke hasn't run in 7+ days |

Detection only, by design: the report names what is broken with evidence;
fixing is a human/agent decision afterward. Tier-2 (actually firing hooks) is
per-hook opt-in in the manifest, because a smoke check must never send
notifications or mutate state as a side effect.

## Install

1. Clone this repo, then junction it into your skills dir:
   `cmd /c mklink /J "%USERPROFILE%\.claude\skills\fleet-smoke" <clone-path>`
2. Copy `fleet-manifest.example.json` to `fleet-manifest.json` beside it and
   fill in your machine's hook sources, expected MCP servers, parity sets, and
   pins. The manifest is gitignored — machine specifics never leave the box.
3. Run `/fleet-smoke` in a Claude Code session. Re-run after every Claude Code
   client update (the documented hook-killer) and whenever the staleness nudge
   fires.

## Scripts

All stdlib-only, JSON output, meaningful exit codes; each is also usable
standalone or in CI:

- `scripts/parity_check.py --mode shared-blocks|identical FILE...`
- `scripts/hook_liveness.py SOURCE.json...`
- `scripts/skill_inventory.py DIR...`
- `scripts/pin_watch.py MANIFEST.json`
- `scripts/staleness_nudge.py MANIFEST.json` (SessionStart hook)

## Tests

`python -m pytest tests/` — 43 behavioral tests, written red-first.

## License

MIT
