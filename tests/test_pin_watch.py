"""Tests for scripts/pin_watch.py — offline logic only (no network in tests)."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import pin_watch  # noqa: E402


class TestVersionCompare:
    def test_equal_versions_current(self):
        assert pin_watch.assess("2.3.7", "2.3.7") == "CURRENT"

    def test_newer_upstream_flags_behind(self):
        assert pin_watch.assess("2.3.7", "2.4.0") == "BEHIND"

    def test_numeric_not_lexicographic(self):
        # 2.10.0 > 2.9.0 numerically; lexicographic compare would get this wrong
        assert pin_watch.assess("2.9.0", "2.10.0") == "BEHIND"

    def test_pin_ahead_of_index_is_flagged_weird(self):
        assert pin_watch.assess("3.0.0", "2.9.0") == "AHEAD-OF-INDEX"

    def test_nonnumeric_segment_does_not_crash(self):
        assert pin_watch.assess("2.3.7", "2.4.0rc1") in ("BEHIND", "UNKNOWN")


class TestParsePypiPayload:
    def test_extracts_latest_version(self):
        payload = {"info": {"version": "2.4.1"}}
        assert pin_watch.latest_from_pypi_payload(payload) == "2.4.1"

    def test_malformed_payload_returns_none(self):
        assert pin_watch.latest_from_pypi_payload({"nope": 1}) is None


class TestIssueRef:
    def test_parses_owner_repo_number(self):
        assert pin_watch.parse_issue_ref("tirth8205/code-review-graph#720") == (
            "tirth8205", "code-review-graph", 720)

    def test_bad_ref_returns_none(self):
        assert pin_watch.parse_issue_ref("not-a-ref") is None


class TestReportRow:
    def test_offline_row_is_honest_unknown(self):
        row = pin_watch.build_row(
            {"package": "code-review-graph", "pinned": "2.3.7"},
            latest=None, issue_state=None)
        assert row["assessment"] == "UNKNOWN"
        assert "unreachable" in row["detail"].lower() or "no data" in row["detail"].lower()

    def test_behind_row_names_both_versions(self):
        row = pin_watch.build_row(
            {"package": "code-review-graph", "pinned": "2.3.7"},
            latest="2.5.0", issue_state="closed")
        assert row["assessment"] == "BEHIND"
        assert "2.3.7" in row["detail"] and "2.5.0" in row["detail"]
        assert row["issue_state"] == "closed"
