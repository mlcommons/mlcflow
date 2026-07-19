import json
import os
import subprocess
import tempfile
import threading
import unittest
import yaml
from unittest.mock import patch, MagicMock

from mlc.repo_action import unregister_repo, RepoAction
from mlc.action import Action
from mlc import utils


class RegisterRepoThreadSafetyTest(unittest.TestCase):
    """
    Verifies that concurrent calls to register_repo / unregister_repo do not
    corrupt repos.json (no entries lost, no duplicates).
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.previous_mlc_repos = os.environ.get("MLC_REPOS")
        self.addCleanup(self._restore_env)
        os.environ["MLC_REPOS"] = os.path.join(self.temp_dir.name, "repos")

        # Bootstrap a minimal MLC environment (creates repos.json, local
        # meta.yaml)
        action = Action()
        action.parent = None
        self.repos_path = action.repos_path
        self.repos_file = os.path.join(self.repos_path, "repos.json")

    def _restore_env(self):
        if self.previous_mlc_repos is None:
            os.environ.pop("MLC_REPOS", None)
        else:
            os.environ["MLC_REPOS"] = self.previous_mlc_repos

    def _make_repo_action(self):
        action = Action()
        action.parent = None
        return RepoAction(parent=action)

    def _make_fake_repo_dir(self, name):
        """Create a temp directory with a minimal meta.yaml that register_repo accepts."""
        repo_dir = os.path.join(self.temp_dir.name, name)
        os.makedirs(repo_dir, exist_ok=True)
        uid = utils.get_new_uid()['uid']
        meta = {'uid': uid, 'alias': name}
        with open(os.path.join(repo_dir, 'meta.yaml'), 'w') as f:
            yaml.dump(meta, f)
        return repo_dir, meta

    def test_concurrent_register_repo_no_data_loss(self):
        """
        N threads each call RepoAction.register_repo with a unique repo path;
        all N must appear in repos.json at the end with no duplicates.
        """
        n_threads = 10
        fake_repos = [self._make_fake_repo_dir(
            f"fake-repo-register-{i}") for i in range(n_threads)]
        errors = []

        def register(repo_path, meta):
            try:
                ra = self._make_repo_action()
                ra.register_repo(repo_path, meta)
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=register, args=(path, meta))
            for path, meta in fake_repos
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], msg=f"Threads raised errors: {errors}")

        with open(self.repos_file, "r") as f:
            final_list = json.load(f)

        for path, _ in fake_repos:
            self.assertIn(
                path,
                final_list,
                msg=f"{path} missing from repos.json")

        # No duplicates
        self.assertEqual(len(final_list), len(set(final_list)),
                         msg="repos.json contains duplicate entries")

    def test_concurrent_unregister_repo_no_data_loss(self):
        """
        Pre-populate repos.json with N paths; N threads each unregister one
        unique path; all fake paths must be gone afterwards with no duplicates.
        """
        n_threads = 10
        fake_paths = [
            f"/tmp/fake-repo-unregister-{i}" for i in range(n_threads)]

        # Seed repos.json with all fake paths
        with open(self.repos_file, "r") as f:
            existing = json.load(f)
        with open(self.repos_file, "w") as f:
            json.dump(existing + fake_paths, f, indent=2)

        errors = []

        def unregister(path):
            try:
                unregister_repo(path, self.repos_file)
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(
                target=unregister, args=(
                    p,)) for p in fake_paths]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], msg=f"Threads raised errors: {errors}")

        with open(self.repos_file, "r") as f:
            final_list = json.load(f)

        for path in fake_paths:
            self.assertNotIn(path, final_list,
                             msg=f"{path} was not removed from repos.json")

        # No duplicates
        self.assertEqual(len(final_list), len(set(final_list)),
                         msg="repos.json contains duplicate entries")

    def test_concurrent_pull_repo_clone_called_once(self):
        """
        N threads all call pull_repo for the same absent repo URL simultaneously;
        git clone must be invoked exactly once (the per-repo FileLock prevents
        duplicate clones).
        """
        n_threads = 5
        repo_url = "https://github.com/example/test-repo.git"
        repo_path = os.path.join(self.repos_path, "example@test-repo")
        clone_call_count = []
        errors = []

        original_subprocess_run = subprocess.run

        def fake_subprocess_run(cmd, *args, **kwargs):
            if cmd[0] == 'git' and len(cmd) > 1 and cmd[1] == 'clone':
                clone_call_count.append(1)
                # Simulate the clone by creating the directory + meta.yaml
                os.makedirs(repo_path, exist_ok=True)
                meta = {
                    'uid': utils.get_new_uid()['uid'],
                    'alias': 'example@test-repo'}
                with open(os.path.join(repo_path, 'meta.yaml'), 'w') as f:
                    yaml.dump(meta, f)
                result = MagicMock()
                result.returncode = 0
                return result
            # Pass-through for any other subprocess calls
            return original_subprocess_run(cmd, *args, **kwargs)

        def do_pull():
            try:
                ra = self._make_repo_action()
                with patch('mlc.repo_action.subprocess.run', side_effect=fake_subprocess_run):
                    ra.pull_repo(repo_url)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=do_pull) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], msg=f"Threads raised errors: {errors}")
        self.assertEqual(
            len(clone_call_count), 1,
            msg=f"git clone was called {len(clone_call_count)} times; expected exactly 1"
        )


if __name__ == "__main__":
    unittest.main()
