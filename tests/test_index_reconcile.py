"""
Tests for index self-healing (pruning stale entries whose folder was removed
out-of-band) and for the batched save path used by Action.rm.
"""
import json
import os
import sys
import tempfile
import unittest

_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


def _dump(path, data):
    with open(path, "w") as f:
        json.dump(data, f)


def _seed(repos_path, cache_entries, modified_times=None):
    _dump(os.path.join(repos_path, "index_cache.json"), cache_entries)
    _dump(os.path.join(repos_path, "index_script.json"), [])
    _dump(os.path.join(repos_path, "index_experiment.json"), [])
    _dump(
        os.path.join(
            repos_path,
            "modified_times.json"),
        modified_times or {})


def _cache_uids(repos_path):
    with open(os.path.join(repos_path, "index_cache.json")) as f:
        return sorted(e["uid"] for e in json.load(f))


class IndexReconcileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.rp = self.tmp.name
        self.local = os.path.join(self.rp, "local")
        os.makedirs(os.path.join(self.local, "cache"))

    def _make_cache(self, name, uid):
        d = os.path.join(self.local, "cache", name)
        os.makedirs(d)
        _dump(os.path.join(d, "meta.yaml"),
              {"uid": uid, "alias": name, "tags": ["t"],
               "automation_alias": "cache", "automation_uid": "x"})
        return {"uid": uid, "alias": name, "tags": ["t"], "path": d,
                "repo": "local"}

    def _repo(self):
        from mlc.repo import Repo
        return Repo(path=self.local, meta={"alias": "local"})

    def test_prunes_stale_entry_with_missing_folder(self):
        # Entry present in index but whose folder was removed out-of-band and
        # is NOT tracked in modified_times (the reported bug) must be pruned.
        from mlc.index import Index
        good = self._make_cache("good", "1" * 16)
        stale = {"uid": "2" * 16, "alias": "gone", "tags": ["t"],
                 "path": os.path.join(self.local, "cache", "gone"),
                 "repo": "local"}
        _seed(self.rp, [good, stale], modified_times={})
        Index(self.rp, [self._repo()])
        self.assertEqual(_cache_uids(self.rp), ["1" * 16])

    def test_keeps_valid_entry(self):
        from mlc.index import Index
        good = self._make_cache("good", "1" * 16)
        _seed(self.rp, [good], modified_times={})
        Index(self.rp, [self._repo()])
        self.assertEqual(_cache_uids(self.rp), ["1" * 16])

    def test_empty_repo_list_is_conservative(self):
        # With no present repos, nothing is pruned (avoids wiping a valid index
        # when repos.json is transiently unreadable).
        from mlc.index import Index
        stale = {"uid": "2" * 16, "alias": "gone", "tags": ["t"],
                 "path": os.path.join(self.local, "cache", "gone"),
                 "repo": "local"}
        _seed(self.rp, [stale], modified_times={})
        Index(self.rp, [])
        self.assertEqual(_cache_uids(self.rp), ["2" * 16])

    def test_rm_save_false_defers_write_and_save_persists(self):
        from mlc.index import Index
        e0 = self._make_cache("c0", "0" * 16)
        e1 = self._make_cache("c1", "1" * 16)
        e2 = self._make_cache("c2", "2" * 16)
        _seed(self.rp, [e0, e1, e2], modified_times={})
        idx = Index(self.rp, [self._repo()])

        calls = {"n": 0}
        orig = idx._save_indices

        def counting():
            calls["n"] += 1
            return orig()
        idx._save_indices = counting

        idx.rm({"uid": e0["uid"]}, "cache", e0["path"], save=False)
        idx.rm({"uid": e1["uid"]}, "cache", e1["path"], save=False)
        self.assertEqual(calls["n"], 0)          # deferred
        idx.save()
        self.assertEqual(calls["n"], 1)          # single batched write
        self.assertEqual(_cache_uids(self.rp), ["2" * 16])


if __name__ == '__main__':
    unittest.main()
