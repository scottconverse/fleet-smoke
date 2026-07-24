---
name: fleet-smoke
description: >
  Run the fleet health smoke — a two-minute check of the Claude Code tool
  fleet on this machine: hook liveness, MCP/plugin load, skill inventory
  (duplicates, dead junctions), cross-copy rule parity, and dependency pin
  watch. Use when the user says "/fleet-smoke", "fleet smoke", "check my
  hooks", "check my plugins", "fleet health", or after any Claude Code client
  update. Detection only — reports with evidence, never auto-fixes, never
  fires side-effectful hooks without per-hook opt-in.
license: MIT
---

# fleet-smoke

Health check for the tool fleet on this machine. Every check runs for real;
no PASS without its command having actually run. On a failure: report it
honestly with verbatim output and continue to the next check — never
silently skip, never fake green. The output is a report; fixing anything is
a separate decision afterward.

All scripts live beside this file in `scripts/` and are stdlib-only. The
machine's inventory lives in `fleet-manifest.json` beside this file
(gitignored; copy `fleet-manifest.example.json` on a new machine).

## Steps

0. **Manifest.** Read `fleet-manifest.json` from this skill's directory. If
   absent, copy the example into place, tell the user to review it, and run
   the checks the unfilled manifest still supports (skill inventory of the
   default skills dir). Never invent manifest entries.

1. **Hook liveness (tier 1 — all hooks).**
   `python3 scripts/hook_liveness.py <each path in hook_sources>`
   One row per registered hook: config parses, referenced script exists.
   PARTIAL rows (no recognizable script path) are reported, not hidden.

2. **Hook fire (tier 2 — opt-in only).** For each manifest `fireable_hooks`
   entry, follow its recipe (e.g. the ruff hook: write a scratch `.py` with a
   deliberate violation via the normal Write/Edit tool path, confirm the
   hook's stderr feedback arrives, delete the scratch file). NEVER fire a
   hook not listed as fireable — hooks can notify or mutate state.

3. **MCP/plugin load.** For each name in `expected_mcp_servers`, confirm this
   session actually has its tools (check the tool listing; use ToolSearch if
   deferred). A server that is configured but absent from the session is a
   FAIL with the likely cause noted (cold cache, install-path breakage,
   auth-pending).

4. **Skill inventory.**
   `python3 scripts/skill_inventory.py <each dir in skills_dirs>`
   Duplicates and problems (dead junctions, missing/bad SKILL.md) are FAILs;
   list the exact colliding names and paths.

5. **Parity.** For each entry in `parity_sets`:
   `python3 scripts/parity_check.py --mode <mode> <files...>`
   `identical` = whole-file (live skill vs repo copy); `shared-blocks` =
   marked SHARED-BLOCK regions across N copies. Zero markers found is a
   FAIL, never a vacuous pass. If the entry carries `substitutions` (path to
   a sanctioned-rewrites JSON) pass `--substitutions <path>`, and pass
   `--collapse-ws` when it sets `collapse_ws` — host-adapted copies compare
   through the map; drift outside it still fails. A git-pull of the repos
   named in the set precedes the check (stale clones prove nothing).

6. **Pin watch (report-only).**
   `python3 scripts/pin_watch.py fleet-manifest.json`
   BEHIND or a closed watched issue is informational — flag it, recommend
   the owner schedule a re-validation, never bump anything.

7. **Stamp.** Write the current ISO timestamp to the manifest's
   `stamp_file`. This is what the SessionStart staleness nudge reads.

8. **Report.** One table, most severe first:

   ```
   check | item | PASS / FAIL / PARTIAL | verbatim evidence
   ```

   Follow with: what each FAIL means in plain English and the recommended
   next action. End with the stamp confirmation. If everything passed, say
   so in one line — no padding.
