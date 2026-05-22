import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from mlc.action import Action
from mlc.repo_action import RepoAction


class TestRepoPullForce(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        self.old_mlc_repos = os.environ.get("MLC_REPOS")
        os.environ["MLC_REPOS"] = os.path.join(self.tmp_dir.name, "repos")
        self.addCleanup(self._restore_env)

        self.parent = Action()
        self.repo_action = RepoAction(self.parent)

        self.repo_path = os.path.join(self.tmp_dir.name, "repo")
        os.makedirs(self.repo_path, exist_ok=True)
        with open(os.path.join(self.repo_path, "meta.yaml"), "w", encoding="utf-8") as f:
            f.write("uid: 1234567890abcdef\nalias: test@repo\ngit: true\n")

    def _restore_env(self):
        if self.old_mlc_repos is None:
            os.environ.pop("MLC_REPOS", None)
        else:
            os.environ["MLC_REPOS"] = self.old_mlc_repos

    @patch.object(RepoAction, "register_repo", return_value={"return": 0})
    @patch("mlc.repo_action.subprocess.run")
    def test_pull_without_force_skips_when_local_changes(self, mock_run, _mock_register):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[-3:] == ["status", "--porcelain", "--untracked-files=no"]:
                return subprocess.CompletedProcess(cmd, 0, stdout=" M tracked.txt\n")
            return subprocess.CompletedProcess(cmd, 0, stdout="")

        mock_run.side_effect = fake_run

        res = self.repo_action.pull_repo("mlcommons@test-repo", repo_path=self.repo_path, force=False)

        self.assertEqual(res["return"], 0)
        self.assertIn("warning", res)
        self.assertFalse(any(cmd[-1] == "pull" for cmd in calls))

    @patch.object(RepoAction, "register_repo", return_value={"return": 0})
    @patch("mlc.repo_action.subprocess.run")
    def test_pull_force_stash_apply_and_drop(self, mock_run, _mock_register):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[-3:] == ["status", "--porcelain", "--untracked-files=no"]:
                return subprocess.CompletedProcess(cmd, 0, stdout=" M tracked.txt\n")
            return subprocess.CompletedProcess(cmd, 0, stdout="ok")

        mock_run.side_effect = fake_run

        res = self.repo_action.pull_repo("mlcommons@test-repo", repo_path=self.repo_path, force=True)

        self.assertEqual(res["return"], 0)
        self.assertNotIn("warning", res)
        self.assertTrue(any(cmd[-1] == "pull" for cmd in calls))
        self.assertTrue(any(cmd[-2:] == ["stash", "apply"] for cmd in calls))
        self.assertTrue(any(cmd[-2:] == ["stash", "drop"] for cmd in calls))

    @patch.object(RepoAction, "register_repo", return_value={"return": 0})
    @patch("mlc.repo_action.subprocess.run")
    def test_pull_force_conflict_reverts_partial_apply(self, mock_run, _mock_register):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            if cmd[-3:] == ["status", "--porcelain", "--untracked-files=no"]:
                return subprocess.CompletedProcess(cmd, 0, stdout=" M tracked.txt\n")
            if cmd[-2:] == ["stash", "apply"]:
                raise subprocess.CalledProcessError(1, cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="ok")

        mock_run.side_effect = fake_run

        res = self.repo_action.pull_repo("mlcommons@test-repo", repo_path=self.repo_path, force=True)

        self.assertEqual(res["return"], 0)
        self.assertIn("warning", res)
        self.assertIn("stash apply had conflicts", res["warning"])
        self.assertTrue(any(cmd[-3:] == ["reset", "--hard", "HEAD"] for cmd in calls))
        self.assertFalse(any(cmd[-2:] == ["stash", "drop"] for cmd in calls))


if __name__ == "__main__":
    unittest.main()
