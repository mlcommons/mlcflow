"""
Unit tests for mlc/compat.py — mlc_compat version-compatibility enforcement.

Covers:
  - no mlc_compat field         → no-op
  - single unmet entry (warn)   → warning printed, execution continues
  - multiple unmet entries      → consolidated notice, all listed
  - fail:true blocking          → error returned, execution blocked
  - version satisfied           → no notice emitted
  - invalid version strings     → gracefully skipped
  - None installed version      → gracefully skipped
"""
import unittest

from mlc.compat import (
    check_mlc_compat,
    format_compat_notice,
    scan_repo_for_compat,
)


# ---------------------------------------------------------------------------
# check_mlc_compat
# ---------------------------------------------------------------------------

class TestCheckMlcCompat(unittest.TestCase):

    def test_no_entries_returns_empty(self):
        w, b = check_mlc_compat([], "1.0.0")
        self.assertEqual(w, [])
        self.assertEqual(b, [])

    def test_none_entries_returns_empty(self):
        w, b = check_mlc_compat(None, "1.0.0")
        self.assertEqual(w, [])
        self.assertEqual(b, [])

    def test_none_installed_version_returns_empty(self):
        entries = [{"min_version": "2.0.0", "message": "needs 2.0"}]
        w, b = check_mlc_compat(entries, None)
        self.assertEqual(w, [])
        self.assertEqual(b, [])

    def test_version_satisfied_returns_empty(self):
        entries = [{"min_version": "1.0.0", "message": "needs 1.0"}]
        w, b = check_mlc_compat(entries, "1.2.0")
        self.assertEqual(w, [])
        self.assertEqual(b, [])

    def test_version_exactly_met_returns_empty(self):
        entries = [{"min_version": "1.2.0", "message": "needs 1.2"}]
        w, b = check_mlc_compat(entries, "1.2.0")
        self.assertEqual(w, [])
        self.assertEqual(b, [])

    def test_single_unmet_warn(self):
        entries = [{"min_version": "2.0.0", "message": "new feature"}]
        w, b = check_mlc_compat(entries, "1.2.0")
        self.assertEqual(len(w), 1)
        self.assertEqual(b, [])
        self.assertEqual(w[0]["min_version"], "2.0.0")
        self.assertEqual(w[0]["message"], "new feature")

    def test_single_unmet_blocker(self):
        entries = [{"min_version": "2.0.0", "message": "critical fix", "fail": True}]
        w, b = check_mlc_compat(entries, "1.2.0")
        self.assertEqual(w, [])
        self.assertEqual(len(b), 1)
        self.assertEqual(b[0]["min_version"], "2.0.0")

    def test_multiple_unmet_cumulative(self):
        entries = [
            {"min_version": "1.3.0", "message": "feature A"},
            {"min_version": "1.5.0", "message": "feature B", "fail": False},
            {"min_version": "2.0.0", "message": "critical C", "fail": True},
        ]
        w, b = check_mlc_compat(entries, "1.2.0")
        self.assertEqual(len(w), 2)
        self.assertEqual(len(b), 1)
        warn_versions = {e["min_version"] for e in w}
        self.assertIn("1.3.0", warn_versions)
        self.assertIn("1.5.0", warn_versions)
        self.assertEqual(b[0]["min_version"], "2.0.0")

    def test_mixed_satisfied_and_unmet(self):
        entries = [
            {"min_version": "1.0.0", "message": "already met"},
            {"min_version": "2.0.0", "message": "not met"},
        ]
        w, b = check_mlc_compat(entries, "1.2.0")
        self.assertEqual(len(w), 1)
        self.assertEqual(w[0]["min_version"], "2.0.0")

    def test_invalid_min_version_is_skipped(self):
        entries = [
            {"min_version": "not-a-version", "message": "bad entry"},
            {"min_version": "2.0.0", "message": "valid entry"},
        ]
        w, b = check_mlc_compat(entries, "1.2.0")
        # Only the valid entry should contribute
        self.assertEqual(len(w), 1)
        self.assertEqual(w[0]["min_version"], "2.0.0")

    def test_non_dict_entry_is_skipped(self):
        entries = ["not-a-dict", {"min_version": "2.0.0", "message": "valid"}]
        w, b = check_mlc_compat(entries, "1.2.0")
        self.assertEqual(len(w), 1)

    def test_default_fail_is_false(self):
        entries = [{"min_version": "2.0.0", "message": "no fail key"}]
        w, b = check_mlc_compat(entries, "1.2.0")
        # Should be a warning, not a blocker
        self.assertEqual(len(w), 1)
        self.assertEqual(len(b), 0)


# ---------------------------------------------------------------------------
# format_compat_notice
# ---------------------------------------------------------------------------

class TestFormatCompatNotice(unittest.TestCase):

    def test_no_unmet_returns_empty(self):
        notice, blocking = format_compat_notice("my-script", [], [], "1.2.0")
        self.assertEqual(notice, "")
        self.assertFalse(blocking)

    def test_warnings_only_not_blocking(self):
        warnings = [{"min_version": "2.0.0", "message": "feature A"}]
        notice, blocking = format_compat_notice("my-script", warnings, [], "1.2.0")
        self.assertFalse(blocking)
        self.assertIn("my-script", notice)
        self.assertIn("2.0.0", notice)
        self.assertIn("feature A", notice)
        self.assertIn("[warn", notice)

    def test_blockers_are_blocking(self):
        blockers = [{"min_version": "2.0.0", "message": "critical fix"}]
        notice, blocking = format_compat_notice("my-script", [], blockers, "1.2.0")
        self.assertTrue(blocking)
        self.assertIn("[ERROR]", notice)
        self.assertIn("pip install --upgrade mlcflow", notice)

    def test_consolidated_notice_lists_all_entries(self):
        warnings = [{"min_version": "1.3.0", "message": "feature A"}]
        blockers = [{"min_version": "2.0.0", "message": "critical C"}]
        notice, blocking = format_compat_notice("my-script", warnings, blockers, "1.2.0")
        self.assertTrue(blocking)
        self.assertIn("1.3.0", notice)
        self.assertIn("2.0.0", notice)
        self.assertIn("feature A", notice)
        self.assertIn("critical C", notice)

    def test_unknown_installed_version(self):
        warnings = [{"min_version": "2.0.0", "message": "feat"}]
        notice, blocking = format_compat_notice("s", warnings, [], None)
        self.assertIn("(unknown)", notice)


# ---------------------------------------------------------------------------
# scan_repo_for_compat (filesystem-level)
# ---------------------------------------------------------------------------

class TestScanRepoForCompat(unittest.TestCase):

    def setUp(self):
        import tempfile
        import os
        import yaml

        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.repo_path = self.temp_dir.name
        self.script_dir = os.path.join(self.repo_path, "script")
        os.makedirs(self.script_dir)

    def _write_script_meta(self, script_name, meta):
        import os
        import yaml

        d = os.path.join(self.script_dir, script_name)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "meta.yaml"), "w") as f:
            yaml.dump(meta, f)

    def test_no_scripts_returns_empty(self):
        results = scan_repo_for_compat(self.repo_path, "1.2.0")
        self.assertEqual(results, [])

    def test_script_without_mlc_compat_not_in_results(self):
        self._write_script_meta("plain-script", {
            "alias": "plain-script",
            "uid": "abc123",
        })
        results = scan_repo_for_compat(self.repo_path, "1.2.0")
        self.assertEqual(results, [])

    def test_script_with_satisfied_compat_not_in_results(self):
        self._write_script_meta("happy-script", {
            "alias": "happy-script",
            "uid": "abc124",
            "mlc_compat": [{"min_version": "1.0.0", "message": "already met"}],
        })
        results = scan_repo_for_compat(self.repo_path, "1.2.0")
        self.assertEqual(results, [])

    def test_script_with_unmet_warn_in_results(self):
        self._write_script_meta("needs-upgrade", {
            "alias": "needs-upgrade",
            "uid": "abc125",
            "mlc_compat": [{"min_version": "2.0.0", "message": "new feature"}],
        })
        results = scan_repo_for_compat(self.repo_path, "1.2.0")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["script_alias"], "needs-upgrade")
        self.assertEqual(len(results[0]["unmet_warnings"]), 1)
        self.assertEqual(results[0]["unmet_blockers"], [])

    def test_script_with_blocker_in_results(self):
        self._write_script_meta("blocker-script", {
            "alias": "blocker-script",
            "uid": "abc126",
            "mlc_compat": [{"min_version": "2.0.0", "message": "critical", "fail": True}],
        })
        results = scan_repo_for_compat(self.repo_path, "1.2.0")
        self.assertEqual(len(results), 1)
        self.assertEqual(len(results[0]["unmet_blockers"]), 1)

    def test_multiple_scripts_summarised(self):
        self._write_script_meta("script-a", {
            "alias": "script-a", "uid": "a1",
            "mlc_compat": [{"min_version": "2.0.0", "message": "feat A"}],
        })
        self._write_script_meta("script-b", {
            "alias": "script-b", "uid": "b1",
            "mlc_compat": [{"min_version": "3.0.0", "message": "feat B", "fail": True}],
        })
        self._write_script_meta("script-ok", {
            "alias": "script-ok", "uid": "c1",
            "mlc_compat": [{"min_version": "1.0.0", "message": "already satisfied"}],
        })
        results = scan_repo_for_compat(self.repo_path, "1.2.0")
        aliases = {r["script_alias"] for r in results}
        self.assertIn("script-a", aliases)
        self.assertIn("script-b", aliases)
        self.assertNotIn("script-ok", aliases)


if __name__ == "__main__":
    unittest.main()
