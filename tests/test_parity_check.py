"""Tests for scripts/parity_check.py — shared-block and identical-file parity."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "parity_check.py"

sys.path.insert(0, str(REPO / "scripts"))
import parity_check  # noqa: E402


def w(tmp_path, name, text):
    # write_bytes: keep the fixture's line endings exactly (write_text would
    # translate \n -> \r\n on Windows and corrupt deliberate-CRLF fixtures)
    p = tmp_path / name
    p.write_bytes(text.encode("utf-8"))
    return p


BLOCK_A = """intro text
<!-- SHARED-BLOCK: rule-1 -->
the rule line one
the rule line two
<!-- /SHARED-BLOCK: rule-1 -->
outro text
"""

BLOCK_A_SAME = """totally different intro
<!-- SHARED-BLOCK: rule-1 -->
the rule line one
the rule line two
<!-- /SHARED-BLOCK: rule-1 -->
different outro
"""

BLOCK_A_DRIFTED = """intro
<!-- SHARED-BLOCK: rule-1 -->
the rule line one
the rule line two CHANGED
<!-- /SHARED-BLOCK: rule-1 -->
outro
"""

NO_BLOCK = "no markers here at all\n"

UNCLOSED = """x
<!-- SHARED-BLOCK: rule-1 -->
never closed
"""


class TestExtractBlocks:
    def test_extracts_named_block(self):
        blocks = parity_check.extract_blocks(BLOCK_A)
        assert list(blocks) == ["rule-1"]
        assert blocks["rule-1"] == "the rule line one\nthe rule line two"

    def test_no_blocks_returns_empty(self):
        assert parity_check.extract_blocks(NO_BLOCK) == {}

    def test_unclosed_block_raises(self):
        with pytest.raises(parity_check.MarkerError):
            parity_check.extract_blocks(UNCLOSED)

    def test_crlf_and_trailing_ws_normalized(self):
        crlf = BLOCK_A.replace("\n", "\r\n").replace("line two", "line two   ")
        blocks = parity_check.extract_blocks(crlf)
        assert blocks["rule-1"] == "the rule line one\nthe rule line two"


class TestCompareBlocks:
    def test_identical_blocks_pass(self, tmp_path):
        f1 = w(tmp_path, "a.md", BLOCK_A)
        f2 = w(tmp_path, "b.md", BLOCK_A_SAME)
        results = parity_check.compare_shared_blocks([f1, f2])
        assert results == [{"block": "rule-1", "status": "PASS", "detail": ""}]

    def test_drifted_block_fails_with_files_named(self, tmp_path):
        f1 = w(tmp_path, "a.md", BLOCK_A)
        f2 = w(tmp_path, "b.md", BLOCK_A_DRIFTED)
        (r,) = parity_check.compare_shared_blocks([f1, f2])
        assert r["status"] == "FAIL"
        assert "a.md" in r["detail"] and "b.md" in r["detail"]

    def test_block_missing_in_one_file_fails(self, tmp_path):
        f1 = w(tmp_path, "a.md", BLOCK_A)
        f2 = w(tmp_path, "b.md", NO_BLOCK)
        (r,) = parity_check.compare_shared_blocks([f1, f2])
        assert r["status"] == "FAIL"
        assert "missing" in r["detail"].lower()
        assert "b.md" in r["detail"]

    def test_no_blocks_anywhere_is_a_fail_not_a_vacuous_pass(self, tmp_path):
        f1 = w(tmp_path, "a.md", NO_BLOCK)
        f2 = w(tmp_path, "b.md", NO_BLOCK)
        results = parity_check.compare_shared_blocks([f1, f2])
        assert len(results) == 1
        assert results[0]["status"] == "FAIL"


class TestIdenticalMode:
    def test_identical_files_pass(self, tmp_path):
        f1 = w(tmp_path, "a.md", BLOCK_A)
        f2 = w(tmp_path, "b.md", BLOCK_A)
        r = parity_check.compare_identical([f1, f2])
        assert r["status"] == "PASS"

    def test_different_files_fail_with_first_diff_line(self, tmp_path):
        f1 = w(tmp_path, "a.md", "same\nline2\n")
        f2 = w(tmp_path, "b.md", "same\nline2 CHANGED\n")
        r = parity_check.compare_identical([f1, f2])
        assert r["status"] == "FAIL"
        assert "line 2" in r["detail"]

    def test_crlf_only_difference_still_passes(self, tmp_path):
        f1 = w(tmp_path, "a.md", "same\nline2\n")
        f2 = w(tmp_path, "b.md", "same\r\nline2\r\n")
        assert parity_check.compare_identical([f1, f2])["status"] == "PASS"

    def test_missing_file_fails(self, tmp_path):
        f1 = w(tmp_path, "a.md", "x\n")
        r = parity_check.compare_identical([f1, tmp_path / "ghost.md"])
        assert r["status"] == "FAIL"
        assert "ghost.md" in r["detail"]


LITE_VARIANT = """<!-- SHARED-BLOCK: rule-1 -->
the rule
line one host-agnostic wording
<!-- /SHARED-BLOCK: rule-1 -->
"""

FULL_VARIANT = """<!-- SHARED-BLOCK: rule-1 -->
the rule line one
plugin-specific wording
<!-- /SHARED-BLOCK: rule-1 -->
"""


class TestSanctionedSubstitutions:
    SUBS = [{"from": "host-agnostic wording", "to": "plugin-specific wording"}]

    def test_sanctioned_difference_passes(self, tmp_path):
        # different wrapping AND a mapped wording difference -> PASS
        f1 = w(tmp_path, "full.md", FULL_VARIANT)
        f2 = w(tmp_path, "lite.md", LITE_VARIANT)
        (r,) = parity_check.compare_shared_blocks(
            [f1, f2], substitutions=self.SUBS, collapse_ws=True)
        assert r["status"] == "PASS", r["detail"]

    def test_unsanctioned_drift_still_fails(self, tmp_path):
        f1 = w(tmp_path, "full.md", FULL_VARIANT)
        f2 = w(tmp_path, "lite.md",
               LITE_VARIANT.replace("the rule", "the CHANGED rule"))
        (r,) = parity_check.compare_shared_blocks(
            [f1, f2], substitutions=self.SUBS, collapse_ws=True)
        assert r["status"] == "FAIL"

    def test_wrapping_only_difference_needs_collapse_ws(self, tmp_path):
        # without collapse_ws, different wrapping is a real difference
        f1 = w(tmp_path, "full.md", FULL_VARIANT)
        f2 = w(tmp_path, "lite.md",
               LITE_VARIANT.replace("host-agnostic", "plugin-specific"))
        (r_strict,) = parity_check.compare_shared_blocks([f1, f2])
        assert r_strict["status"] == "FAIL"
        (r_loose,) = parity_check.compare_shared_blocks(
            [f1, f2], collapse_ws=True)
        assert r_loose["status"] == "PASS"

    def test_substitution_spanning_a_line_wrap_still_matches(self, tmp_path):
        # sanctioned phrases are written single-spaced in the map; they must
        # match even when the source file wraps them across lines
        f1 = w(tmp_path, "full.md", FULL_VARIANT)
        wrapped = LITE_VARIANT.replace("host-agnostic wording",
                                       "host-agnostic\nwording")
        f2 = w(tmp_path, "lite.md", wrapped)
        (r,) = parity_check.compare_shared_blocks(
            [f1, f2], substitutions=self.SUBS, collapse_ws=True)
        assert r["status"] == "PASS", r["detail"]

    def test_cli_substitutions_file(self, tmp_path):
        f1 = w(tmp_path, "full.md", FULL_VARIANT)
        f2 = w(tmp_path, "lite.md", LITE_VARIANT)
        subs = tmp_path / "subs.json"
        subs.write_text(json.dumps(self.SUBS), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--mode", "shared-blocks",
             "--substitutions", str(subs), "--collapse-ws", str(f1), str(f2)],
            capture_output=True, text=True)
        assert proc.returncode == 0, proc.stdout + proc.stderr


class TestCli:
    def test_cli_json_output_and_exit_codes(self, tmp_path):
        f1 = w(tmp_path, "a.md", BLOCK_A)
        f2 = w(tmp_path, "b.md", BLOCK_A_DRIFTED)
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--mode", "shared-blocks", str(f1), str(f2)],
            capture_output=True, text=True,
        )
        assert proc.returncode == 1
        payload = json.loads(proc.stdout)
        assert payload[0]["status"] == "FAIL"

    def test_cli_pass_exits_zero(self, tmp_path):
        f1 = w(tmp_path, "a.md", BLOCK_A)
        f2 = w(tmp_path, "b.md", BLOCK_A_SAME)
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--mode", "shared-blocks", str(f1), str(f2)],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0
