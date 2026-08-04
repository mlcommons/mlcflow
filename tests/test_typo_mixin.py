"""Tests for TypoMixin — the 'Did you mean?' suggestion layer on argparse errors.

Test structure
--------------
TypoMixinSuggestTests
    Unit tests for TypoMixin.suggest() in isolation (no subprocess needed).

TypoMixinCliTests
    Integration tests that run mlc as a subprocess and assert the hint text
    appears in stderr.  These tests follow the same subprocess pattern used
    by test_cache_mark_tmp.py.
"""

import argparse
import subprocess
import sys
import os
import unittest

from mlc.typo_mixin import TypoMixin

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Minimal concrete class for unit-testing suggest() without a full CLI.
class _TestParser(TypoMixin, argparse.ArgumentParser):
    pass


def _run_mlc(*args):
    """Invoke mlc as a subprocess and return the CompletedProcess."""
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = REPO_ROOT if not existing else REPO_ROOT + os.pathsep + existing
    return subprocess.run(
        [sys.executable, "-m", "mlc.main", *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


# --------------------------------------------------------------------------- #
# Unit tests — suggest()                                                       #
# --------------------------------------------------------------------------- #

class TypoMixinSuggestTests(unittest.TestCase):

    def setUp(self):
        self.parser = _TestParser(prog="mlc")

    # ---- single close match ------------------------------------------------

    def test_suggests_run_for_rune(self):
        candidates = ["run", "pull", "test", "add", "find", "rm"]
        result = self.parser.suggest("rune", candidates)
        self.assertEqual(result, ["run"])

    def test_suggests_script_for_scrip(self):
        candidates = ["script", "cache", "repo", "repos"]
        result = self.parser.suggest("scrip", candidates)
        self.assertEqual(result, ["script"])

    def test_suggests_cache_for_cach(self):
        candidates = ["script", "cache", "repo"]
        result = self.parser.suggest("cach", candidates)
        self.assertEqual(result, ["cache"])

    def test_suggests_find_for_fnd(self):
        candidates = ["run", "pull", "find", "search", "rm", "add"]
        result = self.parser.suggest("fnd", candidates)
        self.assertEqual(result, ["find"])

    def test_suggests_pull_for_pul(self):
        candidates = ["run", "pull", "test", "add"]
        result = self.parser.suggest("pul", candidates)
        self.assertEqual(result, ["pull"])

    def test_suggests_search_for_searche(self):
        candidates = ["run", "find", "search", "rm"]
        result = self.parser.suggest("searche", candidates)
        self.assertEqual(result, ["search"])

    def test_suggests_repo_for_rpo(self):
        candidates = ["script", "cache", "repo", "repos"]
        result = self.parser.suggest("rpo", candidates)
        # 'repo' and 'repos' are both close; at least one must be present
        self.assertTrue(len(result) >= 1)
        self.assertIn("repo", result)

    # ---- multiple suggestions ----------------------------------------------

    def test_returns_multiple_when_several_close(self):
        # 'rm' is very similar to 'rm'; 'cp' and 'mv' less so — just check
        # the result is a list.
        candidates = ["run", "rm", "cp", "mv", "add"]
        result = self.parser.suggest("rm", candidates)
        # exact match should be first
        self.assertIn("rm", result)

    # ---- no match ---------------------------------------------------------

    def test_returns_empty_for_completely_different_word(self):
        candidates = ["run", "pull", "test", "add", "find"]
        result = self.parser.suggest("xyzzy", candidates)
        self.assertEqual(result, [])

    def test_returns_empty_for_empty_string(self):
        candidates = ["run", "pull", "test"]
        result = self.parser.suggest("", candidates)
        self.assertEqual(result, [])

    def test_returns_empty_for_empty_candidates(self):
        result = self.parser.suggest("run", [])
        self.assertEqual(result, [])

    # ---- cutoff & max -------------------------------------------------------

    def test_respects_max_suggestions(self):
        # 'scr' is close to 'script', 'search', 'scratch' — at most 3 returned
        candidates = ["script", "search", "scratch", "screen", "run"]
        result = self.parser.suggest("scr", candidates)
        self.assertLessEqual(len(result), self.parser._TYPO_MAX_SUGGESTIONS)

    def test_exact_match_is_included(self):
        candidates = ["run", "pull", "test"]
        result = self.parser.suggest("run", candidates)
        self.assertIn("run", result)

    def test_one_char_transposition(self):
        # 'mrak-tmp' → 'mark-tmp'
        candidates = ["run", "mark-tmp", "prune", "list"]
        result = self.parser.suggest("mrak-tmp", candidates)
        self.assertIn("mark-tmp", result)


# --------------------------------------------------------------------------- #
# Integration tests — CLI output                                               #
# --------------------------------------------------------------------------- #

class TypoMixinCliTests(unittest.TestCase):
    """Run mlc as a subprocess and verify the hint appears in stderr."""

    # ---- action-level typos ------------------------------------------------

    def test_cli_suggests_run_for_rune(self):
        result = _run_mlc("rune", "script")
        self.assertEqual(result.returncode, 2)
        # 'rune' is close to both 'run' and 'prune'; we just verify a hint
        # containing 'run' is shown (single or multi-suggestion form).
        self.assertIn("Did you mean", result.stderr)
        self.assertIn("run", result.stderr)

    def test_cli_suggests_pull_for_pul(self):
        result = _run_mlc("pul", "repo")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Did you mean 'pull'?", result.stderr)

    def test_cli_suggests_find_for_fidn(self):
        result = _run_mlc("fidn", "script")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Did you mean 'find'?", result.stderr)

    def test_cli_suggests_search_for_serach(self):
        result = _run_mlc("serach", "cache")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Did you mean 'search'?", result.stderr)

    def test_cli_suggests_list_for_lst(self):
        result = _run_mlc("lst", "cache")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Did you mean 'list'?", result.stderr)

    def test_cli_suggests_mark_tmp_for_marktmp(self):
        result = _run_mlc("mark_tmp", "cache")
        self.assertEqual(result.returncode, 2)
        # 'mark_tmp' vs 'mark-tmp' — close enough
        self.assertIn("Did you mean", result.stderr)

    # ---- target-level typos ------------------------------------------------

    def test_cli_suggests_script_for_scrip(self):
        result = _run_mlc("run", "scrip")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Did you mean 'script'?", result.stderr)

    def test_cli_suggests_cache_for_cach(self):
        result = _run_mlc("find", "cach")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Did you mean 'cache'?", result.stderr)

    def test_cli_suggests_repo_for_rpo(self):
        result = _run_mlc("pull", "rpo")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Did you mean", result.stderr)
        self.assertIn("repo", result.stderr)

    # ---- no suggestion for totally wrong input -----------------------------

    def test_cli_no_suggestion_for_garbage_command(self):
        result = _run_mlc("xyzzy123", "script")
        self.assertEqual(result.returncode, 2)
        # Should still fail but not print a Did you mean hint
        self.assertNotIn("Did you mean", result.stderr)

    # ---- error message still present ---------------------------------------

    def test_cli_still_shows_error_message(self):
        result = _run_mlc("rune", "script")
        self.assertIn("error:", result.stderr)
        self.assertIn("rune", result.stderr)

    def test_cli_still_shows_usage(self):
        result = _run_mlc("rune", "script")
        self.assertIn("usage:", result.stderr)


if __name__ == "__main__":
    unittest.main()
