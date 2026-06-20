import json
import os
import tempfile
import unittest

import mlc.action as _mlc_action
from mlc.action import Action
from mlc.item import Item


class ActionInvalidMetaSearchTest(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.previous_cwd = os.getcwd()
        self.addCleanup(os.chdir, self.previous_cwd)
        os.chdir(self.temp_dir.name)

        self.previous_mlc_repos = os.environ.get("MLC_REPOS")
        self.addCleanup(self._restore_env)
        os.environ["MLC_REPOS"] = os.path.join(self.temp_dir.name, "repos")

    def _restore_env(self):
        if self.previous_mlc_repos is None:
            os.environ.pop("MLC_REPOS", None)
        else:
            os.environ["MLC_REPOS"] = self.previous_mlc_repos

    def _new_action(self):
        a = Action()
        a.parent = None
        return a

    def _seed_stale_index_entry(self, action, folder_name, uid="fake-uid-000", tags=None):
        """
        Bypass the filesystem scanner by directly injecting a stale cache index
        entry that points to a directory with no meta.json.  This replicates the
        production scenario where the on-disk index JSON already contains the
        entry from a previous run that crashed mid-download.
        """
        stale_dir = os.path.join(
            self.temp_dir.name, "repos", "local", "cache", folder_name
        )
        os.makedirs(stale_dir, exist_ok=True)
        # Leave only the incomplete-download marker — no meta.json.
        with open(os.path.join(stale_dir, "mlc_temp_cache.json"), "w") as f:
            json.dump({"status": "incomplete"}, f)

        entry = {
            "uid": uid,
            "tags": tags or [],
            "alias": folder_name,
            "path": stale_dir,
            "repo": "local",
        }
        action.get_index().indices["cache"] = [entry]
        return stale_dir


    def test_search_fetch_all_with_unknown_target_returns_empty_list(self):
        action = self._new_action()

        res = action.search({"target_name": "unknown", "fetch_all": True})

        self.assertEqual(res["return"], 0)
        self.assertEqual(res["list"], [])

    def test_search_fetch_all_skips_item_with_invalid_meta(self):
        action = self._new_action()
        add_res = action.add({
            "target_name": "cache",
            "item": "bad-meta-cache",
            "tags": "a,b",
        })
        self.assertEqual(add_res["return"], 0)

        # Corrupt meta.json so it is not a dict.
        with open(os.path.join(add_res["path"], "meta.json"), "w") as f:
            json.dump([], f)

        res = action.search({"target_name": "cache", "fetch_all": True})

        self.assertEqual(res["return"], 0)
        self.assertEqual(len(res["list"]), 0)

    def test_search_alias_lookup_skips_item_with_invalid_meta(self):
        action = self._new_action()
        add_res = action.add({
            "target_name": "cache",
            "item": "bad-meta-alias",
            "tags": "x,y",
        })
        self.assertEqual(add_res["return"], 0)

        # Corrupt meta.json into a non-dict so it fails verification lookup
        with open(os.path.join(add_res["path"], "meta.json"), "w") as f:
            json.dump([], f)

        res = action.search({"target_name": "cache", "details": "bad-meta-alias"})

        self.assertEqual(res["return"], 0)
        self.assertEqual(len(res["list"]), 0)

    def test_search_alias_lookup_skips_corrupt_index_entry_without_meta(self):
        """
        Index entry points to a path that has no meta file at all.
        Injected directly to bypass the filesystem scanner.
        """
        action = self._new_action()
        self._seed_stale_index_entry(
            action, "bad-whisper-cache", uid="not-a-real-uid", tags=["x", "y"]
        )

        res = action.search({"target_name": "cache", "details": "bad-whisper-cache"})

        self.assertEqual(res["return"], 0)
        self.assertEqual(len(res["list"]), 0)
        

    def test_search_meta_validation_prevents_corrupt_items_in_alias_path(self):
        """
        Regression test for the Whisper inference stale-folder bug.
        Regression test for the Whisper dataset stale-folder bug.
        Simulates a crashed/incomplete download where the index entry persists but meta.json is missing, 
        ensuring the search guard safely skips it.
        """
        action = self._new_action()

        self._seed_stale_index_entry(
            action, "whisper-dataset", uid="fake-whisper-uid-123", tags=["x", "y"]
        )

        res = action.search({"target_name": "cache", "details": "whisper-dataset"})

        self.assertEqual(res["return"], 0)
        self.assertEqual(
            len(res["list"]), 0,
            msg="search() must skip cache items whose meta.json is absent or invalid.",
        )

    def test_search_tags_handles_missing_tags_key_in_index(self):
        action = self._new_action()
        add_res = action.add({
            "target_name": "cache",
            "item": "missing-tags-index",
            "tags": "alpha,beta",
        })
        self.assertEqual(add_res["return"], 0)

        cache_index = action.get_index().indices["cache"]
        self.assertEqual(len(cache_index), 1)
        cache_index[0].pop("tags", None)

        res = action.search({"target_name": "cache", "tags": "alpha"})

        self.assertEqual(res["return"], 0)
        self.assertEqual(len(res["list"]), 0)


if __name__ == "__main__":
    unittest.main()