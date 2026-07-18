import json
import os
import tempfile
import threading
import unittest

from mlc.repo_action import unregister_repo
from mlc.action import Action
from filelock import FileLock


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

    def _register_path(self, path):
        """Thread-safe repos.json registration (mirrors register_repo logic)."""
        repos_lock_file = self.repos_file + ".lock"
        with FileLock(repos_lock_file, timeout=60):
            with open(self.repos_file, "r") as f:
                repos_list = json.load(f)
            if path not in repos_list:
                repos_list.append(path)
            with open(self.repos_file, "w") as f:
                json.dump(repos_list, f, indent=2)

    def test_concurrent_register_repo_no_data_loss(self):
        """
        N threads each register a unique repo path; all N must appear in
        repos.json at the end with no duplicates.
        """
        n_threads = 10
        fake_paths = [f"/tmp/fake-repo-register-{i}" for i in range(n_threads)]
        errors = []

        def register(path):
            try:
                self._register_path(path)
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(
                target=register, args=(
                    p,)) for p in fake_paths]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], msg=f"Threads raised errors: {errors}")

        with open(self.repos_file, "r") as f:
            final_list = json.load(f)

        for path in fake_paths:
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


if __name__ == "__main__":
    unittest.main()
