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
            if cmd[0] == "git" and "status" in cmd and "--porcelain" in cmd and "--untracked-files=no" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout=" M tracked.txt\n")
            return subprocess.CompletedProcess(cmd, 0, stdout="")

        mock_run.side_effect = fake_run

        res = self.repo_action.pull_repo("mlcommons@test-repo", repo_path=self.repo_path, force=False)

        self.assertEqual(res["return"], 0)
        self.assertIn("warning", res)
        self.assertFalse(any("pull" in cmd for cmd in calls))

    @patch.object(RepoAction, "register_repo", return_value={"return": 0})
    @patch("mlc.repo_action.subprocess.run")
    def test_pull_force_stash_apply_and_drop(self, mock_run, _mock_register):
        calls = []
        stash_list_call_count = 0

        def fake_run(cmd, **kwargs):
            nonlocal stash_list_call_count
            calls.append(cmd)
            if cmd[0] == "git" and "status" in cmd and "--porcelain" in cmd and "--untracked-files=no" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout=" M tracked.txt\n")
            if cmd[0] == "git" and "stash" in cmd and "list" in cmd:
                stash_list_call_count += 1
                if stash_list_call_count == 1:
                    return subprocess.CompletedProcess(cmd, 0, stdout="")
                return subprocess.CompletedProcess(cmd, 0, stdout="stash@{0}: On dev: mlc pull repo --force\n")
            return subprocess.CompletedProcess(cmd, 0, stdout="ok")

        mock_run.side_effect = fake_run

        res = self.repo_action.pull_repo("mlcommons@test-repo", repo_path=self.repo_path, force=True)

        self.assertEqual(res["return"], 0)
        self.assertNotIn("warning", res)
        self.assertTrue(any("pull" in cmd for cmd in calls))
        self.assertTrue(any("stash" in cmd and "apply" in cmd for cmd in calls))
        self.assertTrue(any("stash" in cmd and "drop" in cmd for cmd in calls))

    @patch.object(RepoAction, "register_repo", return_value={"return": 0})
    @patch("mlc.repo_action.subprocess.run")
    def test_pull_force_conflict_reverts_partial_apply(self, mock_run, _mock_register):
        calls = []
        stash_list_call_count = 0

        def fake_run(cmd, **kwargs):
            nonlocal stash_list_call_count
            calls.append(cmd)
            if cmd[0] == "git" and "status" in cmd and "--porcelain" in cmd and "--untracked-files=no" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout=" M tracked.txt\n")
            if cmd[0] == "git" and "stash" in cmd and "list" in cmd:
                stash_list_call_count += 1
                if stash_list_call_count == 1:
                    return subprocess.CompletedProcess(cmd, 0, stdout="")
                return subprocess.CompletedProcess(cmd, 0, stdout="stash@{0}: On dev: mlc pull repo --force\n")
            if "stash" in cmd and "apply" in cmd:
                raise subprocess.CalledProcessError(1, cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="ok")

        mock_run.side_effect = fake_run

        res = self.repo_action.pull_repo("mlcommons@test-repo", repo_path=self.repo_path, force=True)

        self.assertEqual(res["return"], 0)
        self.assertIn("warning", res)
        self.assertIn("stash apply had conflicts", res["warning"])
        self.assertTrue(any("reset" in cmd and "--hard" in cmd and "HEAD" in cmd for cmd in calls))
        self.assertFalse(any("stash" in cmd and "drop" in cmd for cmd in calls))


if __name__ == "__main__":
    unittest.main()
