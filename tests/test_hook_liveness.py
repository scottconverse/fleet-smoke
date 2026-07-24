"""Tests for scripts/hook_liveness.py — tier-1 hook wiring checks."""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import hook_liveness  # noqa: E402


def write_settings(tmp_path, hooks):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"hooks": hooks}), encoding="utf-8")
    return p


class TestExtractScriptPath:
    def test_bare_script_path(self):
        assert hook_liveness.extract_script_path(
            "C:/Users/x/.claude/hooks/foo.py"
        ) == "C:/Users/x/.claude/hooks/foo.py"

    def test_powershell_file_wrapper(self):
        cmd = 'powershell -NoProfile -ExecutionPolicy Bypass -File "C:\\Users\\x\\hooks\\notify.ps1"'
        assert hook_liveness.extract_script_path(cmd) == "C:\\Users\\x\\hooks\\notify.ps1"

    def test_python_wrapper(self):
        cmd = "python3 C:/Users/x/.claude/skills/fleet-smoke/scripts/staleness_nudge.py"
        assert hook_liveness.extract_script_path(cmd) == (
            "C:/Users/x/.claude/skills/fleet-smoke/scripts/staleness_nudge.py"
        )

    def test_cmd_shim(self):
        assert hook_liveness.extract_script_path(
            "C:/Users/x/.orca/agent-hooks/claude-hook.cmd"
        ) == "C:/Users/x/.orca/agent-hooks/claude-hook.cmd"

    def test_no_recognizable_path_returns_none(self):
        assert hook_liveness.extract_script_path("echo hello") is None


class TestCheckHookSource:
    def test_live_hook_passes(self, tmp_path):
        script = tmp_path / "hook.cmd"
        script.write_text("@echo off\n")
        src = write_settings(tmp_path, {
            "Stop": [{"hooks": [{"type": "command", "command": str(script)}]}],
        })
        results = hook_liveness.check_hook_source(src)
        assert len(results) == 1
        assert results[0]["status"] == "PASS"
        assert results[0]["event"] == "Stop"

    def test_missing_script_fails(self, tmp_path):
        src = write_settings(tmp_path, {
            "Stop": [{"hooks": [{"type": "command",
                                 "command": str(tmp_path / "ghost.cmd")}]}],
        })
        (r,) = hook_liveness.check_hook_source(src)
        assert r["status"] == "FAIL"
        assert "ghost.cmd" in r["detail"]

    def test_unparseable_source_is_single_fail(self, tmp_path):
        src = tmp_path / "settings.json"
        src.write_text("{not json", encoding="utf-8")
        (r,) = hook_liveness.check_hook_source(src)
        assert r["status"] == "FAIL"

    def test_missing_source_file_is_single_fail(self, tmp_path):
        (r,) = hook_liveness.check_hook_source(tmp_path / "nope.json")
        assert r["status"] == "FAIL"

    def test_plugin_hooks_json_shape(self, tmp_path):
        # plugin hooks.json: top-level events, no "hooks" wrapper key
        script = tmp_path / "ruff_hook.py"
        script.write_text("pass\n")
        p = tmp_path / "hooks.json"
        p.write_text(json.dumps({
            "PostToolUse": [{"matcher": "Write|Edit",
                             "hooks": [{"type": "command",
                                        "command": f"python3 {script}"}]}],
        }), encoding="utf-8")
        (r,) = hook_liveness.check_hook_source(p)
        assert r["status"] == "PASS"
        assert r["event"] == "PostToolUse"

    def test_claude_plugin_root_placeholder_expands_to_plugin_root(self, tmp_path):
        # ${CLAUDE_PLUGIN_ROOT} in a plugin's hooks.json means the plugin root
        # (the hooks.json's parent's parent); it must not be reported missing.
        plugin = tmp_path / "myplugin"
        hookdir = plugin / "hooks"
        hookdir.mkdir(parents=True)
        (hookdir / "ruff_feedback.py").write_text("pass\n")
        src = hookdir / "hooks.json"
        src.write_text(json.dumps({
            "PostToolUse": [{"hooks": [{
                "type": "command",
                "command": 'python "${CLAUDE_PLUGIN_ROOT}/hooks/ruff_feedback.py"'}]}],
        }), encoding="utf-8")
        (r,) = hook_liveness.check_hook_source(src)
        assert r["status"] == "PASS", r["detail"]

    def test_plugin_root_placeholder_with_script_actually_missing_fails(self, tmp_path):
        hookdir = tmp_path / "myplugin" / "hooks"
        hookdir.mkdir(parents=True)
        src = hookdir / "hooks.json"
        src.write_text(json.dumps({
            "PostToolUse": [{"hooks": [{
                "type": "command",
                "command": 'python "${CLAUDE_PLUGIN_ROOT}/hooks/ghost.py"'}]}],
        }), encoding="utf-8")
        (r,) = hook_liveness.check_hook_source(src)
        assert r["status"] == "FAIL"

    def test_command_with_no_path_is_partial(self, tmp_path):
        src = write_settings(tmp_path, {
            "Stop": [{"hooks": [{"type": "command", "command": "echo done"}]}],
        })
        (r,) = hook_liveness.check_hook_source(src)
        assert r["status"] == "PARTIAL"

    def test_empty_event_lists_are_skipped_silently(self, tmp_path):
        src = write_settings(tmp_path, {"SessionStart": []})
        assert hook_liveness.check_hook_source(src) == []
