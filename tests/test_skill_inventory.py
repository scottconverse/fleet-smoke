"""Tests for scripts/skill_inventory.py — duplicates, dead junctions, bad frontmatter."""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
import skill_inventory  # noqa: E402

def GOOD(name):
    return f"---\nname: {name}\ndescription: fine\n---\n\nbody\n"


NO_FRONTMATTER = "just a body, no frontmatter\n"


def mkskill(root, folder, text=None, nested=None):
    d = root / folder
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(text if text is not None else GOOD(folder),
                                encoding="utf-8")
    if nested:
        for sub in nested:
            nd = d / "skills" / sub
            nd.mkdir(parents=True)
            (nd / "SKILL.md").write_text(GOOD(sub), encoding="utf-8")
    return d


class TestInventory:
    def test_healthy_dir_all_pass(self, tmp_path):
        mkskill(tmp_path, "alpha")
        mkskill(tmp_path, "beta")
        report = skill_inventory.scan([tmp_path])
        assert {s["name"] for s in report["skills"]} == {"alpha", "beta"}
        assert report["duplicates"] == []
        assert report["problems"] == []

    def test_duplicate_names_across_dirs_flagged(self, tmp_path):
        d1 = tmp_path / "one"
        d2 = tmp_path / "two"
        mkskill(d1, "alpha")
        mkskill(d2, "alpha")
        report = skill_inventory.scan([d1, d2])
        assert len(report["duplicates"]) == 1
        assert report["duplicates"][0]["name"] == "alpha"
        assert len(report["duplicates"][0]["paths"]) == 2

    def test_nested_plugin_skills_are_seen(self, tmp_path):
        mkskill(tmp_path, "det", nested=["install-thing"])
        report = skill_inventory.scan([tmp_path])
        names = {s["name"] for s in report["skills"]}
        assert "det" in names and "install-thing" in names

    def test_missing_frontmatter_is_a_problem(self, tmp_path):
        mkskill(tmp_path, "bad", text=NO_FRONTMATTER)
        report = skill_inventory.scan([tmp_path])
        assert any("bad" in p["path"] for p in report["problems"])

    def test_folder_without_skill_md_reported(self, tmp_path):
        (tmp_path / "empty-folder").mkdir()
        mkskill(tmp_path, "alpha")
        report = skill_inventory.scan([tmp_path])
        assert any("empty-folder" in p["path"] for p in report["problems"])

    def test_dead_junction_reported(self, tmp_path):
        # a symlink/junction whose target is gone
        target = tmp_path / "target"
        target.mkdir()
        link = tmp_path / "skills-root" / "linked"
        link.parent.mkdir()
        try:
            link.symlink_to(target, target_is_directory=True)
        except OSError:
            import subprocess
            subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                           capture_output=True)
        (target / "SKILL.md").write_text(GOOD("linked"), encoding="utf-8")
        import shutil
        shutil.rmtree(target)
        report = skill_inventory.scan([link.parent])
        assert any(p["kind"] == "dead-link" for p in report["problems"])
