import json
import os
import subprocess
import sys
import tempfile
import unittest

from mlc.action import (
    default_mlc_root,
    environment_key,
    resolve_cache_path,
    resolve_repos_path,
)


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class RootResolutionTest(unittest.TestCase):
    """The two roots are configured independently, so they must resolve
    independently.

    MLC_CACHE moves the cache and nothing else; MLC_REPOS moves the repo root
    and nothing else. These tests exist because the coupling they forbid was
    the previous behaviour, and it is the kind of thing a well meaning
    "restore back-compat" patch reintroduces without noticing.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.previous_mlc_repos = os.environ.get("MLC_REPOS")
        self.previous_mlc_cache = os.environ.get("MLC_CACHE")
        self.addCleanup(self._restore_env)
        os.environ.pop("MLC_REPOS", None)
        os.environ.pop("MLC_CACHE", None)

        self.repos_dir = os.path.join(self.temp_dir.name, "repos")
        self.cache_dir = os.path.join(self.temp_dir.name, "cache")
        self.default_root = os.path.join(default_mlc_root(), "repos")

    def _restore_env(self):
        if self.previous_mlc_repos is None:
            os.environ.pop("MLC_REPOS", None)
        else:
            os.environ["MLC_REPOS"] = self.previous_mlc_repos
        if self.previous_mlc_cache is None:
            os.environ.pop("MLC_CACHE", None)
        else:
            os.environ["MLC_CACHE"] = self.previous_mlc_cache

    def test_neither_set(self):
        self.assertEqual(resolve_cache_path(), self.default_root)
        self.assertEqual(resolve_repos_path(None), self.default_root)

    def test_repos_only_does_not_move_the_cache(self):
        os.environ["MLC_REPOS"] = self.repos_dir

        self.assertEqual(resolve_repos_path(None), self.repos_dir)
        self.assertEqual(resolve_cache_path(), self.default_root)

    def test_cache_only_does_not_move_the_repo_root(self):
        os.environ["MLC_CACHE"] = self.cache_dir

        self.assertEqual(resolve_cache_path(), self.cache_dir)
        self.assertEqual(resolve_repos_path(None), self.default_root)

    def test_both_set_are_honoured_separately(self):
        os.environ["MLC_REPOS"] = self.repos_dir
        os.environ["MLC_CACHE"] = self.cache_dir

        self.assertEqual(resolve_repos_path(None), self.repos_dir)
        self.assertEqual(resolve_cache_path(), self.cache_dir)

    def test_cache_root_ignores_the_package_repo_root(self):
        """The per-environment repo root must never reach the cache root.

        If it did, installing mlc-scripts into a new environment would
        relocate every cached dataset and the next run would re-download it.
        """
        package_repo_path = os.path.join(
            self.temp_dir.name, "site-packages", "mlc_scripts")

        expected_repos = os.path.join(
            default_mlc_root(), "envs",
            environment_key(os.path.dirname(package_repo_path)))
        self.assertEqual(
            resolve_repos_path(package_repo_path), expected_repos)
        self.assertEqual(resolve_cache_path(), self.default_root)

    def test_values_are_expanded_and_absolute(self):
        os.environ["MLC_CACHE"] = "~/some-cache"
        os.environ["MLC_REPOS"] = "~/some-repos"

        self.assertEqual(
            resolve_cache_path(),
            os.path.join(os.path.expanduser("~"), "some-cache"))
        self.assertEqual(
            resolve_repos_path(None),
            os.path.join(os.path.expanduser("~"), "some-repos"))

    def test_blank_values_are_treated_as_unset(self):
        os.environ["MLC_CACHE"] = "   "
        os.environ["MLC_REPOS"] = ""

        self.assertEqual(resolve_cache_path(), self.default_root)
        self.assertEqual(resolve_repos_path(None), self.default_root)


CHILD = r'''
import json, logging, os, sys
sys.path.insert(0, os.environ["MLCFLOW_REPO"])
from mlc.action import Action
from mlc.repo_action import RepoAction

warnings = []


class Collect(logging.Handler):
    def emit(self, record):
        if record.levelno >= logging.WARNING:
            warnings.append(record.getMessage())


logging.getLogger("mlc").addHandler(Collect())

action = Action()
out = {
    "repos_path": action.repos_path,
    "cache_path": action.cache_path,
    "local_cache_path": action.local_cache_path,
    "warnings": warnings,
}

if os.environ.get("ADD_CACHE_ITEM"):
    action.parent = None
    res = action.add({"target_name": "cache",
                      "item": os.environ["ADD_CACHE_ITEM"],
                      "tags": "get,rootres,fixture"})
    out["add_return"] = res["return"]

if os.environ.get("SEARCH_CACHE"):
    action.parent = action
    res = action.access({"action": "search", "target": "cache",
                         "tags": "get,rootres,fixture"})
    out["search_return"] = res["return"]
    out["search_paths"] = [item.path for item in res.get("list", [])]

if os.environ.get("LIST_REPO"):
    repo_action = RepoAction(action)
    repo_action.parent = action
    repo_action.list({})

print("@@JSON@@" + json.dumps(out))
'''


class ConstructedRootsTest(unittest.TestCase):
    """End-to-end checks on the roots an Action actually settles on.

    Separate from RootResolutionTest because the interesting behaviour is not
    in the resolver functions: the constructor writes repos.json and then
    _ensure_local_registered() can override the resolved cache root from the
    registry. Both mechanisms guarded here regressed once while the
    pure-function tests above stayed green.

    Runs in a child process with HOME redirected, so default_mlc_root()
    resolves into a scratch directory and the developer's real ~/MLC is never
    read or written.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def _run(self, home, **env_extra):
        env = dict(os.environ)
        for key in ("MLC_REPOS", "MLC_CACHE", "ADD_CACHE_ITEM",
                    "SEARCH_CACHE", "LIST_REPO"):
            env.pop(key, None)
        env["HOME"] = home
        env["MLCFLOW_REPO"] = REPO_ROOT
        env.update(env_extra)

        # cwd inside the scratch dir: Action() writes .mlc-log.txt into it.
        cwd = os.path.join(self.temp_dir.name, "cwd")
        os.makedirs(cwd, exist_ok=True)
        proc = subprocess.run([sys.executable, "-c", CHILD], env=env, cwd=cwd,
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0,
                         f"child failed:\n{proc.stdout}\n{proc.stderr}")
        payload = next(line for line in proc.stdout.splitlines()
                       if line.startswith("@@JSON@@"))
        return json.loads(payload[len("@@JSON@@"):]), proc.stdout

    def _mkdirs(self, *names):
        made = []
        for name in names:
            path = os.path.join(self.temp_dir.name, name)
            os.makedirs(path, exist_ok=True)
            made.append(path)
        return made

    @staticmethod
    def _warned(result):
        return [w for w in result["warnings"]
                if "MLC_REPOS is set but MLC_CACHE" in w]

    def test_fresh_root_with_repos_only_keeps_cache_at_the_default(self):
        home, repos = self._mkdirs("home_fresh", "repos_fresh")

        result, stdout = self._run(home, MLC_REPOS=repos, LIST_REPO="1")

        self.assertEqual(os.path.realpath(result["repos_path"]),
                         os.path.realpath(repos))
        self.assertEqual(os.path.realpath(result["cache_path"]),
                         os.path.realpath(os.path.join(home, "MLC", "repos")))
        # Fires once, not zero times: repos.json is written with the candidate
        # already in it before _ensure_local_registered() runs, so a condition
        # keyed on "nothing registered yet" would never trigger here.
        self.assertEqual(len(self._warned(result)), 1, result["warnings"])
        self.assertIn("(set by MLC_REPOS)", stdout)
        self.assertIn("(default)", stdout)

    def test_single_root_upgrade_keeps_its_existing_cache(self):
        """A pre-1.4 layout under $MLC_REPOS must not be relocated.

        resolve_cache_path() no longer looks at MLC_REPOS, so this rests
        entirely on _ensure_local_registered() keeping the registered 'local'.
        """
        home, legacy = self._mkdirs("home_upgrade", "legacy")

        # Build the old single-root layout using the real code paths.
        before, _ = self._run(home, MLC_REPOS=legacy, MLC_CACHE=legacy,
                              ADD_CACHE_ITEM="legacy-entry")
        self.assertEqual(before.get("add_return"), 0)

        after, stdout = self._run(home, MLC_REPOS=legacy, SEARCH_CACHE="1",
                                  LIST_REPO="1")

        self.assertEqual(os.path.realpath(after["local_cache_path"]),
                         os.path.realpath(os.path.join(legacy, "local", "cache")))
        self.assertEqual(after.get("search_return"), 0)
        self.assertEqual(len(after.get("search_paths", [])), 1,
                         after.get("search_paths"))
        self.assertFalse(
            os.path.exists(os.path.join(home, "MLC", "repos", "local")),
            "a stray local repo was created under the default root")
        self.assertEqual(self._warned(after), [],
                         "nothing moved, so the warning must stay quiet")
        self.assertIn("from the registered local repo", stdout)

    def test_no_vars_reports_both_roots_as_default(self):
        """Guards a realpath/abspath mismatch in _cache_path_origin().

        cache_path arrives symlink-resolved while default_mlc_root() does a
        bare expanduser, so comparing abspaths reported an untouched default
        as a relocated cache on any HOME that traverses a symlink.
        """
        home, = self._mkdirs("home_plain")

        result, stdout = self._run(home, LIST_REPO="1")

        default = os.path.realpath(os.path.join(home, "MLC", "repos"))
        self.assertEqual(os.path.realpath(result["repos_path"]), default)
        self.assertEqual(os.path.realpath(result["cache_path"]), default)
        self.assertEqual(stdout.count("(default)"), 2, stdout)
        self.assertEqual(self._warned(result), [])

    def test_cache_var_wins_and_is_reported_as_such(self):
        home, repos, cache = self._mkdirs(
            "home_both", "repos_both", "cache_both")

        result, stdout = self._run(home, MLC_REPOS=repos, MLC_CACHE=cache,
                                   LIST_REPO="1")

        self.assertEqual(os.path.realpath(result["repos_path"]),
                         os.path.realpath(repos))
        self.assertEqual(os.path.realpath(result["cache_path"]),
                         os.path.realpath(cache))
        self.assertIn("(set by MLC_CACHE)", stdout)
        self.assertEqual(self._warned(result), [])


if __name__ == "__main__":
    unittest.main()
