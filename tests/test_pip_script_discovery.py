import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import mlc.action as _mlc_action
from mlc.action import (
    Action,
    discover_pip_script_repos,
    SCRIPT_PACKAGE_ENTRY_POINT_GROUP,
)


class _FakeDist:
    def __init__(self, name):
        self.name = name


class _FakeModule:
    def __init__(self, content_dir):
        self.__file__ = os.path.join(content_dir, "__init__.py")


class _FakeEntryPoint:
    """Stand-in for importlib.metadata.EntryPoint."""

    def __init__(self, name, dist_name, content_dir, load_error=None):
        self.name = name
        self.dist = _FakeDist(dist_name) if dist_name is not None else None
        self._content_dir = content_dir
        self._load_error = load_error
        self.load_call_count = 0

    def load(self):
        self.load_call_count += 1
        if self._load_error:
            raise self._load_error
        return _FakeModule(self._content_dir)


def _write_script(content_dir, alias, uid, tags=None, deps=None):
    script_dir = os.path.join(content_dir, "script", alias)
    os.makedirs(script_dir, exist_ok=True)
    meta = {
        "alias": alias,
        "uid": uid,
        "automation_alias": "script",
        "automation_uid": "5b4e0237da074764",
        "tags": tags or [alias],
    }
    if deps:
        meta["deps"] = deps
    import yaml
    with open(os.path.join(script_dir, "meta.yaml"), "w") as f:
        yaml.safe_dump(meta, f)
    with open(os.path.join(script_dir, "customize.py"), "w") as f:
        f.write("def preprocess(i):\n    return {'return': 0}\n")
    return script_dir


class PipScriptDiscoveryTest(unittest.TestCase):

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

        self.content_dir = os.path.join(self.temp_dir.name, "content_pkg")
        os.makedirs(self.content_dir, exist_ok=True)

    def _restore_env(self):
        if self.previous_mlc_repos is None:
            os.environ.pop("MLC_REPOS", None)
        else:
            os.environ["MLC_REPOS"] = self.previous_mlc_repos

    def _new_action(self):
        a = Action()
        a.parent = None
        return a

    def _patch_entry_points(self, entry_points):
        return patch.object(
            _mlc_action.importlib_metadata, "entry_points",
            return_value=entry_points)

    # ---- 2.1 no-op safety ------------------------------------------------

    def test_no_entry_points_is_complete_noop(self):
        with self._patch_entry_points([]):
            repos = discover_pip_script_repos(self.repos_path)
        self.assertEqual(repos, [])
        self.assertFalse(os.path.exists(
            os.path.join(self.repos_path, "package_repos_cache.json")))

    def test_entry_points_enumeration_failure_does_not_crash(self):
        with patch.object(_mlc_action.importlib_metadata, "entry_points",
                           side_effect=RuntimeError("boom")):
            repos = discover_pip_script_repos(self.repos_path)
        self.assertEqual(repos, [])

    # ---- 1.1/1.2 basic discovery ------------------------------------------

    def test_basic_discovery_adds_repo_and_makes_script_searchable(self):
        _write_script(self.content_dir, "detect-widget", "a" * 16)
        ep = _FakeEntryPoint("mlperf-automations", "mlc-scripts", self.content_dir)

        with self._patch_entry_points([ep]):
            action = self._new_action()

        pip_repos = [r for r in action.repos if r.meta.get("source") == "pip"]
        self.assertEqual(len(pip_repos), 1)
        self.assertEqual(pip_repos[0].meta["alias"], "mlc-scripts")
        self.assertEqual(ep.load_call_count, 1)

        res = action.search(
            {"target_name": "script", "tags": "detect-widget"})
        self.assertEqual(res["return"], 0)
        self.assertEqual(len(res["list"]), 1)
        self.assertTrue(res["list"][0].path.startswith(self.content_dir))

    # ---- 3.1 caching: second run skips .load() -----------------------------

    def test_cache_skips_reload_on_second_run_with_no_changes(self):
        _write_script(self.content_dir, "detect-widget", "a" * 16)
        ep1 = _FakeEntryPoint("mlperf-automations", "mlc-scripts", self.content_dir)
        with self._patch_entry_points([ep1]):
            discover_pip_script_repos(self.repos_path)
        self.assertEqual(ep1.load_call_count, 1)

        ep2 = _FakeEntryPoint("mlperf-automations", "mlc-scripts", self.content_dir)
        with self._patch_entry_points([ep2]):
            repos = discover_pip_script_repos(self.repos_path)

        self.assertEqual(ep2.load_call_count, 0)
        self.assertEqual(len(repos), 1)
        self.assertEqual(repos[0].meta["alias"], "mlc-scripts")

    def test_cache_file_written_only_when_something_changes(self):
        cache_file = os.path.join(self.repos_path, "package_repos_cache.json")
        _write_script(self.content_dir, "detect-widget", "a" * 16)
        ep1 = _FakeEntryPoint("mlperf-automations", "mlc-scripts", self.content_dir)
        with self._patch_entry_points([ep1]):
            discover_pip_script_repos(self.repos_path)
        self.assertTrue(os.path.exists(cache_file))
        mtime_after_first = os.path.getmtime(cache_file)

        ep2 = _FakeEntryPoint("mlperf-automations", "mlc-scripts", self.content_dir)
        with self._patch_entry_points([ep2]):
            discover_pip_script_repos(self.repos_path)
        self.assertEqual(os.path.getmtime(cache_file), mtime_after_first)

    def test_corrupted_cache_file_falls_back_gracefully(self):
        os.makedirs(self.repos_path, exist_ok=True)
        cache_file = os.path.join(self.repos_path, "package_repos_cache.json")
        with open(cache_file, "w") as f:
            f.write("{not valid json")

        _write_script(self.content_dir, "detect-widget", "a" * 16)
        ep = _FakeEntryPoint("mlperf-automations", "mlc-scripts", self.content_dir)
        with self._patch_entry_points([ep]):
            repos = discover_pip_script_repos(self.repos_path)

        self.assertEqual(len(repos), 1)
        self.assertEqual(ep.load_call_count, 1)

    # ---- 4.1 uninstall -> disappears ---------------------------------------

    def test_uninstalled_package_disappears_on_next_discovery(self):
        _write_script(self.content_dir, "detect-widget", "a" * 16)
        ep = _FakeEntryPoint("mlperf-automations", "mlc-scripts", self.content_dir)
        with self._patch_entry_points([ep]):
            repos = discover_pip_script_repos(self.repos_path)
        self.assertEqual(len(repos), 1)

        with self._patch_entry_points([]):
            repos = discover_pip_script_repos(self.repos_path)
        self.assertEqual(repos, [])

    def test_uninstalled_package_scripts_removed_from_index(self):
        _write_script(self.content_dir, "detect-widget", "a" * 16)
        ep = _FakeEntryPoint("mlperf-automations", "mlc-scripts", self.content_dir)
        with self._patch_entry_points([ep]):
            action = self._new_action()
        res = action.search({"target_name": "script", "tags": "detect-widget"})
        self.assertEqual(len(res["list"]), 1)

        with self._patch_entry_points([]):
            action2 = self._new_action()
        res2 = action2.search({"target_name": "script", "tags": "detect-widget"})
        self.assertEqual(len(res2["list"]), 0)

    # ---- 5.1 fork disambiguation (core design point) -----------------------

    def test_fork_with_same_entry_point_name_different_distribution_coexist(self):
        official_dir = os.path.join(self.temp_dir.name, "official_pkg")
        fork_dir = os.path.join(self.temp_dir.name, "fork_pkg")
        _write_script(official_dir, "detect-widget", "a" * 16)
        _write_script(fork_dir, "new-fork-script", "b" * 16)

        # Same self-chosen entry-point name on purpose - the whole point is
        # that this must NOT matter.
        ep_official = _FakeEntryPoint(
            "mlperf-automations", "mlc-scripts", official_dir)
        ep_fork = _FakeEntryPoint(
            "mlperf-automations", "anandhu-mlc-scripts-fork", fork_dir)

        from mlc.repo_action import RepoAction
        with patch.object(RepoAction, "conflicting_repo") as mock_conflict:
            with self._patch_entry_points([ep_official, ep_fork]):
                action = self._new_action()
        mock_conflict.assert_not_called()

        pip_aliases = sorted(
            r.meta["alias"] for r in action.repos if r.meta.get("source") == "pip")
        self.assertEqual(pip_aliases, ["anandhu-mlc-scripts-fork", "mlc-scripts"])

        res_official = action.search(
            {"target_name": "script", "tags": "detect-widget"})
        res_fork = action.search(
            {"target_name": "script", "tags": "new-fork-script"})
        self.assertEqual(len(res_official["list"]), 1)
        self.assertEqual(len(res_fork["list"]), 1)

    # ---- 8. cross-repo dependency resolution (both directions) ------------

    def test_script_in_pip_repo_resolvable_as_dep_of_git_repo_script(self):
        _write_script(self.content_dir, "get-widget", "a" * 16)
        ep = _FakeEntryPoint("mlperf-automations", "mlc-scripts", self.content_dir)

        with self._patch_entry_points([ep]):
            action = self._new_action()

        git_repo_dir = os.path.join(self.temp_dir.name, "git_repo")
        os.makedirs(git_repo_dir, exist_ok=True)
        with open(os.path.join(git_repo_dir, "meta.yaml"), "w") as f:
            import yaml
            yaml.safe_dump({"alias": "git-repo", "uid": "c" * 16}, f)
        _write_script(
            git_repo_dir, "app-uses-widget", "d" * 16,
            deps=[{"tags": "get-widget"}])

        with open(os.path.join(self.repos_path, "repos.json"), "r+") as f:
            import json
            paths = json.load(f)
            paths.append(git_repo_dir)
            f.seek(0)
            json.dump(paths, f)
            f.truncate()

        with self._patch_entry_points([ep]):
            action2 = self._new_action()

        dep_lookup = action2.search(
            {"target_name": "script", "tags": "get-widget"})
        self.assertEqual(len(dep_lookup["list"]), 1)
        self.assertTrue(dep_lookup["list"][0].path.startswith(self.content_dir))

    # ---- 9.1 broken package doesn't take down discovery for others --------

    def test_broken_entry_point_is_skipped_others_still_discovered(self):
        _write_script(self.content_dir, "detect-widget", "a" * 16)
        good_ep = _FakeEntryPoint("mlperf-automations", "mlc-scripts", self.content_dir)
        broken_ep = _FakeEntryPoint(
            "broken-pkg", "broken-dist", "/nonexistent",
            load_error=ImportError("simulated broken package"))

        with self._patch_entry_points([broken_ep, good_ep]):
            repos = discover_pip_script_repos(self.repos_path)

        self.assertEqual(len(repos), 1)
        self.assertEqual(repos[0].meta["alias"], "mlc-scripts")

    def test_entry_point_resolving_to_missing_directory_is_skipped(self):
        ep = _FakeEntryPoint("mlperf-automations", "mlc-scripts", "/nonexistent/path")
        with self._patch_entry_points([ep]):
            repos = discover_pip_script_repos(self.repos_path)
        self.assertEqual(repos, [])

    # ---- 10.1/10.2 mutation safety ------------------------------------------

    def test_add_script_refused_for_pip_sourced_repo(self):
        _write_script(self.content_dir, "detect-widget", "a" * 16)
        ep = _FakeEntryPoint("mlperf-automations", "mlc-scripts", self.content_dir)
        with self._patch_entry_points([ep]):
            action = self._new_action()

        res = action.add({
            "item_repo": "mlc-scripts",
            "item": "new-script-1",
            "target_name": "script",
        })
        self.assertEqual(res["return"], 1)
        self.assertIn("pip package", res["error"])
        self.assertFalse(
            os.path.exists(os.path.join(self.content_dir, "script", "new-script-1")))

    def test_rm_repo_refused_for_pip_sourced_repo(self):
        _write_script(self.content_dir, "detect-widget", "a" * 16)
        ep = _FakeEntryPoint("mlperf-automations", "mlc-scripts", self.content_dir)
        with self._patch_entry_points([ep]):
            action = self._new_action()

        res = action.access(
            {"action": "rm", "target": "repo", "repo": "mlc-scripts", "f": True})
        self.assertEqual(res["return"], 1)
        self.assertIn("pip uninstall", res["error"])
        self.assertTrue(os.path.isdir(self.content_dir))

    def test_cp_script_into_pip_sourced_repo_referenced_by_alias_is_refused(self):
        # Regression test: the pip repo's on-disk directory basename
        # ("content_pkg", a tempdir name) never matches its alias
        # ("mlc-scripts", the distribution name) - cp()'s target-repo lookup
        # used to match by basename only and would crash with a NameError
        # instead of returning a clean refusal for exactly this mismatch.
        _write_script(self.content_dir, "detect-widget", "a" * 16)
        ep = _FakeEntryPoint("mlperf-automations", "mlc-scripts", self.content_dir)
        with self._patch_entry_points([ep]):
            action = self._new_action()

        res = action.cp({
            "target": "script",
            "src": "detect-widget",
            "dest": "mlc-scripts:should-not-be-created",
        })
        self.assertEqual(res["return"], 1)
        self.assertIn("pip package", res["error"])
        self.assertFalse(os.path.exists(
            os.path.join(self.content_dir, "script", "should-not-be-created")))


if __name__ == "__main__":
    unittest.main()
