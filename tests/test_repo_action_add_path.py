import os
import tempfile
import unittest

from mlc.action import Action
from mlc.repo_action import _looks_like_filesystem_path


class LooksLikeFilesystemPathTest(unittest.TestCase):
    def test_bare_repo_names_are_not_paths(self):
        for name in ["mlcommons@mlperf-automations", "aocc-scripts", "myrepo"]:
            self.assertFalse(
                _looks_like_filesystem_path(name),
                msg=f"{name!r} should not be treated as a path",
            )

    def test_windows_drive_paths_are_detected(self):
        # Detected regardless of the host OS so behaviour is testable anywhere.
        for path in [r"Z:\pa\aocc-scripts", "Z:/pa/aocc-scripts",
                     r"\\server\share\aocc-scripts"]:
            self.assertTrue(
                _looks_like_filesystem_path(path),
                msg=f"{path!r} should be treated as a path",
            )

    def test_posix_absolute_and_relative_paths_are_detected(self):
        self.assertTrue(_looks_like_filesystem_path("/tmp/aocc-scripts"))
        self.assertTrue(
            _looks_like_filesystem_path(os.path.join("sub", "aocc-scripts")))


class AddRepoPathTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.previous_cwd = os.getcwd()
        self.addCleanup(os.chdir, self.previous_cwd)
        os.chdir(self.temp_dir.name)

        self.previous_mlc_repos = os.environ.get("MLC_REPOS")
        self.addCleanup(self._restore_env)
        self.repos_path = os.path.join(self.temp_dir.name, "repos")
        os.environ["MLC_REPOS"] = self.repos_path

    def _restore_env(self):
        if self.previous_mlc_repos is None:
            os.environ.pop("MLC_REPOS", None)
        else:
            os.environ["MLC_REPOS"] = self.previous_mlc_repos

    def _add_repo(self, repo):
        action = Action()
        action.parent = None
        return action.access({
            "action": "add",
            "target": "repo",
            "repo": repo,
        })

    def test_missing_explicit_path_errors_without_creating_wrong_folder(self):
        missing = os.path.join(self.temp_dir.name, "not-mounted", "aocc-scripts")
        res = self._add_repo(missing)
        self.assertEqual(res["return"], 1)
        self.assertIn("does not exist", res["error"])
        # The wrong folder must not be silently created under the repos dir.
        self.assertFalse(
            os.path.exists(os.path.join(self.repos_path, "aocc-scripts")))

    def test_windows_style_path_errors_on_any_platform(self):
        res = self._add_repo(r"Z:\pa\aocc-scripts")
        self.assertEqual(res["return"], 1)
        self.assertIn("does not exist", res["error"])
        self.assertFalse(
            os.path.exists(os.path.join(self.repos_path, "aocc-scripts")))

    def test_existing_external_path_is_registered_as_is(self):
        external = os.path.join(self.temp_dir.name, "external", "aocc-scripts")
        os.makedirs(external)
        res = self._add_repo(external)
        self.assertEqual(res["return"], 0)
        with open(os.path.join(self.repos_path, "repos.json")) as f:
            content = f.read()
        self.assertIn(os.path.abspath(external), content)


if __name__ == "__main__":
    unittest.main()
