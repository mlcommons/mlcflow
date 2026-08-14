"""
Thread safety tests for core mlc operations:
- mlc rm cache
- mlc mark-tmp cache
- register_repo / unregister_repo (repos.json)
"""

import json
import os
import shutil
import tempfile
import threading
import unittest
from unittest import mock

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
        for name, tags in [("cache-a", "get,dataset,a"),
                           ("cache-b", "get,dataset,b")]:
            res = action.add(
                {"target_name": "cache", "item": name, "tags": tags})
            self.assertEqual(res["return"], 0)

    def _restore_env(self):
        if self.previous_mlc_repos is None:
            os.environ.pop("MLC_REPOS", None)
        else:
            os.environ["MLC_REPOS"] = self.previous_mlc_repos

    def test_concurrent_rm_cache_does_not_raise(self):
        """Two threads deleting the same cache item must not raise an exception,
        and the item must be gone from the filesystem and index afterwards.

        The race is forced rather than left to the scheduler: rm() checks
        os.path.exists(item_path) and only then calls shutil.rmtree(), so the
        window is a few microseconds wide and is almost never hit naturally.
        The barrier below holds both threads at the entry to rmtree -- which
        they can only reach after passing that existence check -- and the lock
        then serialises the deletions, so the second caller always meets an
        already-removed directory.
        """
        errors = []
        # Record the path of the item before deletion
        action_pre = Action()
        action_pre.parent = None
        res_pre = action_pre.search(
            {"target_name": "cache", "tags": "get,dataset,a"})
        self.assertEqual(res_pre["return"], 0)
        self.assertGreater(len(res_pre["list"]),
                           0, "Item must exist before test")
        item_path = res_pre["list"][0].path

        real_rmtree = shutil.rmtree
        # 2 parties: one per racing thread, so neither proceeds until both have
        # cleared the existence check. The timeout is a safety net rather than
        # part of the choreography -- if a thread never arrives, wait() raises
        # BrokenBarrierError, which rm_cache records in `errors` and the
        # assertion below reports, instead of hanging CI until it is killed.
        both_threads_past_exists_check = threading.Barrier(2, timeout=30)
        deletion_order = threading.Lock()

        def racing_rmtree(path, *args, **kwargs):
            # Only coordinate on the contended item; any other rmtree call
            # (temp dirs, index internals) must pass straight through or it
            # would pair up with the barrier and deadlock.
            if os.path.abspath(path) != os.path.abspath(item_path):
                return real_rmtree(path, *args, **kwargs)
            # Blocking here *before* deleting guarantees the item is still on
            # disk and in the index for the other thread's search, so both
            # threads are certain to reach this point and the barrier cannot
            # time out.
            both_threads_past_exists_check.wait()
            with deletion_order:
                return real_rmtree(path, *args, **kwargs)

        def rm_cache(tags):
            try:
                action = Action()
                action.parent = None
                # Call rm directly with target_name set (same as CacheAction.rm
                # does)
                action.rm({"target_name": "cache", "tags": tags, "f": True})
            except Exception as exc:
                errors.append(exc)

        with mock.patch.object(shutil, "rmtree", racing_rmtree):
            t1 = threading.Thread(target=rm_cache, args=("get,dataset,a",))
            t2 = threading.Thread(target=rm_cache, args=("get,dataset,a",))
            t1.start()
            t2.start()
            t1.join()
            t2.join()

        self.assertEqual(errors, [], f"Unexpected exceptions: {errors}")
        self.assertFalse(
            os.path.exists(item_path),
            f"Item directory still exists after concurrent rm: {item_path}"
        )
        # Index must also not list the item anymore
        action_post = Action()
        action_post.parent = None
        res_post = action_post.search(
            {"target_name": "cache", "tags": "get,dataset,a"})
        self.assertEqual(res_post["return"], 0)
        self.assertEqual(
            len(res_post["list"]), 0,
            f"Item still in index after concurrent rm: {res_post['list']}"
        )


class ConcurrentMarkTmpTest(unittest.TestCase):
    """mark_tmp must re-read meta inside the lock to avoid lost updates."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.previous_mlc_repos = os.environ.get("MLC_REPOS")
        self.addCleanup(self._restore_env)

        repos_dir = os.path.join(self.temp_dir.name, "repos")
        os.environ["MLC_REPOS"] = repos_dir

        action = Action()
        action.parent = None
        res = action.add(
            {"target_name": "cache", "item": "shared-cache", "tags": "get,shared"})
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
                cache = CacheAction(action)
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

    def test_mark_tmp_does_not_clobber_concurrent_tag_writes(self):
        """mark_tmp must re-read meta from disk inside the lock so that a tag written
        by another process between search() and lock acquisition is not silently lost."""
        import unittest.mock as mock

        meta_json = os.path.join(self.cache_path, "meta.json")
        original_search = CacheAction.search

        def patched_search(self_inner, i):
            result = original_search(self_inner, i)
            # Simulate a concurrent write that adds 'extra-tag' to the meta file
            # after search() has already populated item.meta but before the
            # lock.
            if os.path.exists(meta_json):
                with open(meta_json) as fh:
                    on_disk = json.load(fh)
                if 'extra-tag' not in on_disk.get('tags', []):
                    on_disk['tags'] = on_disk.get('tags', []) + ['extra-tag']
                    with open(meta_json, 'w') as fh:
                        json.dump(on_disk, fh)
            return result

        with mock.patch.object(CacheAction, 'search', patched_search):
            action = Action()
            cache = CacheAction(action)
            cache.mark_tmp({"tags": "get,shared"})

        with open(meta_json) as f:
            meta = json.load(f)

        self.assertIn('tmp', meta['tags'])
        self.assertIn(
            'extra-tag', meta['tags'],
            "extra-tag was lost: mark_tmp used stale meta instead of re-reading inside lock"
        )


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
