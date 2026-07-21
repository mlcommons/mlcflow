from mlc.index import Index
import json
import os
import sys
import tempfile
import unittest

# Ensure the in-tree mlc package is imported (not an installed copy) regardless
# of how the test is invoked.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


UID = "abcdef0123456789"


class _FakeRepo:
    """Minimal stand-in for mlc.repo.Repo — only ``readonly`` is read by
    Index._process_config_file for the priority decision."""

    def __init__(self, path, readonly):
        self.path = path
        self.readonly = readonly


class IndexScriptPriorityTest(unittest.TestCase):
    """The bundled read-only mlc-scripts package must win over a registered
    (dev/local) repo on a UID clash by default; MLC_PREFER_DEV_SCRIPTS restores
    dev-first. The outcome must be independent of processing order (full vs
    incremental index builds process repos in different orders)."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self._prev = os.environ.get("MLC_PREFER_DEV_SCRIPTS")
        self.addCleanup(self._restore_env)

    def _restore_env(self):
        if self._prev is None:
            os.environ.pop("MLC_PREFER_DEV_SCRIPTS", None)
        else:
            os.environ["MLC_PREFER_DEV_SCRIPTS"] = self._prev

    def _make_meta(self, alias):
        d = os.path.join(self.temp_dir.name, alias)
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, "meta.json")
        with open(p, "w") as f:
            json.dump({"uid": UID, "alias": alias, "tags": [alias]}, f)
        return p, d

    def _fresh_index(self):
        idx = object.__new__(Index)  # bypass the heavy __init__ (disk I/O)
        idx.indices = {"script": []}
        return idx

    def _winner(self, idx):
        entries = [e for e in idx.indices["script"] if e["uid"] == UID]
        self.assertEqual(len(entries), 1, entries)
        return "package" if entries[0]["readonly"] else "dev"

    def _run(self, prefer_dev, dev_first):
        os.environ.pop("MLC_PREFER_DEV_SCRIPTS", None)
        if prefer_dev:
            os.environ["MLC_PREFER_DEV_SCRIPTS"] = "1"
        pkg_meta, pkg_dir = self._make_meta("resnet-pkg")
        dev_meta, dev_dir = self._make_meta("resnet-dev")
        pkg_repo = _FakeRepo(pkg_dir, readonly=True)
        dev_repo = _FakeRepo(dev_dir, readonly=False)
        seq = [(pkg_meta, pkg_dir, pkg_repo), (dev_meta, dev_dir, dev_repo)]
        if dev_first:
            seq.reverse()
        idx = self._fresh_index()
        for meta, d, repo in seq:
            idx._process_config_file(meta, "script", d, repo)
        return self._winner(idx)

    def test_default_package_wins_pkg_first(self):
        self.assertEqual(
            self._run(
                prefer_dev=False,
                dev_first=False),
            "package")

    def test_default_package_wins_dev_first(self):
        self.assertEqual(
            self._run(
                prefer_dev=False,
                dev_first=True),
            "package")

    def test_prefer_dev_wins_pkg_first(self):
        self.assertEqual(self._run(prefer_dev=True, dev_first=False), "dev")

    def test_prefer_dev_wins_dev_first(self):
        self.assertEqual(self._run(prefer_dev=True, dev_first=True), "dev")


if __name__ == "__main__":
    unittest.main()
