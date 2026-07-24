"""Tests for scripts/staleness_nudge.py — SessionStart stamp check."""
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import staleness_nudge  # noqa: E402


def manifest_with_stamp(tmp_path, stamp_path):
    m = tmp_path / "fleet-manifest.json"
    m.write_text(json.dumps({"stamp_file": str(stamp_path)}), encoding="utf-8")
    return m


class TestNudge:
    def test_no_stamp_file_nudges(self, tmp_path):
        m = manifest_with_stamp(tmp_path, tmp_path / "no-such-stamp")
        msg = staleness_nudge.nudge_message(m, max_age_days=7)
        assert msg is not None and "never" in msg.lower()

    def test_fresh_stamp_is_silent(self, tmp_path):
        stamp = tmp_path / ".last-run"
        stamp.write_text("2026-07-23T00:00:00", encoding="utf-8")
        m = manifest_with_stamp(tmp_path, stamp)
        assert staleness_nudge.nudge_message(m, max_age_days=7, now=time.time()) is None

    def test_stale_stamp_nudges_with_age(self, tmp_path):
        stamp = tmp_path / ".last-run"
        stamp.write_text("old", encoding="utf-8")
        ten_days_ago = time.time() - 10 * 86400
        import os
        os.utime(stamp, (ten_days_ago, ten_days_ago))
        m = manifest_with_stamp(tmp_path, stamp)
        msg = staleness_nudge.nudge_message(m, max_age_days=7)
        assert msg is not None and "10 day" in msg

    def test_missing_manifest_is_silent_not_crash(self, tmp_path):
        # a broken nudge must never break session start
        assert staleness_nudge.nudge_message(tmp_path / "ghost.json") is None
