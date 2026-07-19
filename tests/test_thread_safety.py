"""
Thread safety tests for core mlc operations:
- mlc rm cache
- mlc mark-tmp cache
- register_repo / unregister_repo (repos.json)
"""

import json
import os
import tempfile
import threading
import unittest

from mlc.action import Action
from mlc.cache_action import CacheAction
from mlc.repo_action import unregister_repo


class ConcurrentRmCacheTest(unittest.TestCase):
    """Concurrent mlc rm cache calls must not raise or corrupt state."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.previous_mlc_repos = os.environ.get("MLC_REPOS")
        self.addCleanup(self._restore_env)

        repos_dir = os.path.join(self.temp_dir.name, "repos")
        os.environ["MLC_REPOS"] = repos_dir

        action = Action()
        action.parent = None
        for name, tags in [("cache-a", "get,dataset,a"), ("cache-b", "get,dataset,b")]:
            res = action.add({"target_name": "cache", "item": name, "tags": tags})
            self.assertEqual(res["return"], 0)

    def _restore_env(self):
        if self.previous_mlc_repos is None:
            os.environ.pop("MLC_REPOS", None)
        else:
            os.environ["MLC_REPOS"] = self.previous_mlc_repos

    def test_concurrent_rm_cache_does_not_raise(self):
        """Two threads deleting the same cache item must not raise an exception."""
        errors = []

        def rm_cache(tags):
            try:
                action = Action()
                action.parent = None
                # Call rm directly with target_name set (same as CacheAction.rm does)
                action.rm({"target_name": "cache", "tags": tags, "f": True})
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=rm_cache, args=("get,dataset,a",))
        t2 = threading.Thread(target=rm_cache, args=("get,dataset,a",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(errors, [], f"Unexpected exceptions: {errors}")


class ConcurrentMarkTmpTest(unittest.TestCase):
    """Concurrent mark-tmp calls on the same item must not duplicate the tag."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.previous_mlc_repos = os.environ.get("MLC_REPOS")
        self.addCleanup(self._restore_env)

        repos_dir = os.path.join(self.temp_dir.name, "repos")
        os.environ["MLC_REPOS"] = repos_dir

        action = Action()
        action.parent = None
        res = action.add({"target_name": "cache", "item": "shared-cache", "tags": "get,shared"})
        self.assertEqual(res["return"], 0)
        self.cache_path = res["path"]

    def _restore_env(self):
        if self.previous_mlc_repos is None:
            os.environ.pop("MLC_REPOS", None)
        else:
            os.environ["MLC_REPOS"] = self.previous_mlc_repos

    def test_concurrent_mark_tmp_no_duplicate_tag(self):
        """Concurrent mark-tmp calls must not produce a duplicated 'tmp' tag."""
        errors = []

        def mark_tmp():
            try:
                action = Action()
                action.parent = None
                # CacheAction.__init__ does self.__dict__.update(vars(parent)),
                # which would overwrite self.parent with parent.parent (None).
                # Reassign explicitly so mark_tmp's self.search works via parent.
                cache = CacheAction(action)
                cache.parent = action
                cache.mark_tmp({"tags": "get,shared"})
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=mark_tmp) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Unexpected exceptions: {errors}")

        meta_json = os.path.join(self.cache_path, "meta.json")
        with open(meta_json) as f:
            meta = json.load(f)
        self.assertIn("tmp", meta["tags"])
        self.assertEqual(meta["tags"].count("tmp"), 1,
                         "Expected exactly one 'tmp' tag after concurrent mark-tmp calls")


class ConcurrentReposJsonTest(unittest.TestCase):
    """Concurrent unregister_repo calls must not corrupt repos.json."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.previous_mlc_repos = os.environ.get("MLC_REPOS")
        self.addCleanup(self._restore_env)

        self.repos_dir = os.path.join(self.temp_dir.name, "repos")
        os.makedirs(self.repos_dir, exist_ok=True)
        self.repos_file = os.path.join(self.repos_dir, "repos.json")

        local_path = os.path.join(self.repos_dir, "local")
        os.makedirs(local_path, exist_ok=True)
        with open(os.path.join(local_path, "meta.yaml"), "w") as f:
            f.write("uid: 0000000000000000\nalias: local\n")
        with open(self.repos_file, "w") as f:
            json.dump([local_path], f)

        os.environ["MLC_REPOS"] = self.repos_dir

    def _restore_env(self):
        if self.previous_mlc_repos is None:
            os.environ.pop("MLC_REPOS", None)
        else:
            os.environ["MLC_REPOS"] = self.previous_mlc_repos

    def test_concurrent_unregister_no_corruption(self):
        """Concurrent unregister_repo calls must leave repos.json as valid JSON
        and must not lose any update due to a read-modify-write race."""
        paths = [os.path.join(self.repos_dir, f"repo{i}") for i in range(10)]
        with open(self.repos_file, "w") as f:
            json.dump(paths, f)

        errors = []

        def unreg(p):
            try:
                unregister_repo(p, self.repos_file)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=unreg, args=(p,)) for p in paths]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Unexpected exceptions: {errors}")

        with open(self.repos_file) as f:
            remaining = json.load(f)
        self.assertIsInstance(remaining, list)
        for p in paths:
            self.assertNotIn(p, remaining,
                             f"{p} should have been removed but was still in repos.json")


if __name__ == "__main__":
    unittest.main()
