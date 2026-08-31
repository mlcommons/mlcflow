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
    """Two independent explicit tiers over one shared automatic tier.

    MLC_CACHE moves the cache and nothing else; MLC_REPOS moves the repo root
    and nothing else; neither resolver reads the other's variable. Below the
    explicit tier both roots default to the same per-environment directory,
    keyed on the site-packages path of an installed mlc-scripts.

    What these tests forbid is therefore not "the two roots ever agreeing" -
    on a plain packaged install they are the same directory - but the env vars
    reading each other. That coupling was the pre-1.4 behaviour and is the kind
    of thing a well meaning "restore back-compat" patch reintroduces without
    noticing.
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

    def _package(self, venv="venv"):
        """A plausible installed-package path under a scratch site-packages."""
        return os.path.join(
            self.temp_dir.name, venv, "site-packages", "mlc_scripts")

    def _env_root(self, package_repo_path):
        return os.path.join(
            default_mlc_root(), "envs",
            environment_key(os.path.dirname(package_repo_path)))

    # --- no package installed: every one of these is unchanged behaviour ---

    def test_neither_set(self):
        self.assertEqual(resolve_cache_path(None), self.default_root)
        self.assertEqual(resolve_repos_path(None), self.default_root)

    def test_repos_only_does_not_move_the_cache(self):
        os.environ["MLC_REPOS"] = self.repos_dir

        self.assertEqual(resolve_repos_path(None), self.repos_dir)
        self.assertEqual(resolve_cache_path(None), self.default_root)

    def test_cache_only_does_not_move_the_repo_root(self):
        os.environ["MLC_CACHE"] = self.cache_dir

        self.assertEqual(resolve_cache_path(None), self.cache_dir)
        self.assertEqual(resolve_repos_path(None), self.default_root)

    def test_both_set_are_honoured_separately(self):
        os.environ["MLC_REPOS"] = self.repos_dir
        os.environ["MLC_CACHE"] = self.cache_dir

        self.assertEqual(resolve_repos_path(None), self.repos_dir)
        self.assertEqual(resolve_cache_path(None), self.cache_dir)

    def test_values_are_expanded_and_absolute(self):
        os.environ["MLC_CACHE"] = "~/some-cache"
        os.environ["MLC_REPOS"] = "~/some-repos"

        self.assertEqual(
            resolve_cache_path(None),
            os.path.join(os.path.expanduser("~"), "some-cache"))
        self.assertEqual(
            resolve_repos_path(None),
            os.path.join(os.path.expanduser("~"), "some-repos"))

    def test_blank_values_are_treated_as_unset(self):
        os.environ["MLC_CACHE"] = "   "
        os.environ["MLC_REPOS"] = ""

        self.assertEqual(resolve_cache_path(None), self.default_root)
        self.assertEqual(resolve_repos_path(None), self.default_root)

    # --- package installed: the cache root follows it too ---

    def test_cache_root_follows_the_package_repo_root(self):
        """A packaged install moves *both* roots, to the same directory.

        The cache follows the environment for the same reason the repo root
        does: script content is already per environment, while cache matching
        is keyed only on tags and an optional meta.yaml 'version'. Two
        environments on different mlc-scripts versions sharing one cache
        therefore reuse each other's entries whenever an author forgot to bump
        'version' - a stale hit with no error.

        The cost, accepted deliberately, is that a fresh environment
        re-downloads its datasets. MLC_CACHE is the opt-out.
        """
        package_repo_path = self._package()
        expected = self._env_root(package_repo_path)

        self.assertEqual(resolve_cache_path(package_repo_path), expected)
        self.assertEqual(resolve_repos_path(package_repo_path), expected)
        # Stated once, because the whole design is "these two agree".
        self.assertEqual(resolve_cache_path(package_repo_path),
                         resolve_repos_path(package_repo_path))
        # The guard against a well meaning revert to the shared cache.
        self.assertNotEqual(
            resolve_cache_path(package_repo_path), self.default_root)

    def test_repos_var_does_not_pull_the_cache_along(self):
        """MLC_REPOS set, MLC_CACHE unset, package installed.

        resolve_cache_path() must not read MLC_REPOS in either its explicit or
        its resolved form, so the cache stays on its own chain and lands in the
        per-environment root.
        """
        package_repo_path = self._package()
        os.environ["MLC_REPOS"] = self.repos_dir

        self.assertEqual(resolve_repos_path(package_repo_path), self.repos_dir)
        self.assertEqual(resolve_cache_path(package_repo_path),
                         self._env_root(package_repo_path))

    def test_explicit_cache_beats_the_package(self):
        package_repo_path = self._package()
        os.environ["MLC_CACHE"] = self.cache_dir

        self.assertEqual(resolve_cache_path(package_repo_path), self.cache_dir)
        self.assertEqual(resolve_repos_path(package_repo_path),
                         self._env_root(package_repo_path))

    def test_both_explicit_beat_the_package(self):
        package_repo_path = self._package()
        os.environ["MLC_REPOS"] = self.repos_dir
        os.environ["MLC_CACHE"] = self.cache_dir

        self.assertEqual(resolve_repos_path(package_repo_path), self.repos_dir)
        self.assertEqual(resolve_cache_path(package_repo_path), self.cache_dir)

    def test_blank_cache_falls_through_to_the_env_root(self):
        """A blank MLC_CACHE must reach the package tier, not the shared root."""
        package_repo_path = self._package()
        os.environ["MLC_CACHE"] = "   "

        self.assertEqual(resolve_cache_path(package_repo_path),
                         self._env_root(package_repo_path))

    def test_two_environments_hash_differently(self):
        a = self._package("venvA")
        b = self._package("venvB")

        self.assertNotEqual(resolve_cache_path(a), resolve_cache_path(b))
        self.assertEqual(resolve_cache_path(a), resolve_repos_path(a))
        self.assertEqual(resolve_cache_path(b), resolve_repos_path(b))

    def test_the_key_is_the_site_packages_dir_not_the_package_dir(self):
        """Two packages in one venv must share a root.

        Keyed on the site-packages directory, so anything installed beside
        mlc_scripts resolves to the same environment.
        """
        package_repo_path = self._package()

        self.assertTrue(resolve_cache_path(package_repo_path).endswith(
            environment_key(os.path.dirname(package_repo_path))))
        self.assertFalse(resolve_cache_path(package_repo_path).endswith(
            environment_key(package_repo_path)))

    def test_a_trailing_slash_does_not_split_the_roots(self):
        """abspath must be applied before dirname, on both sides.

        os.path.dirname keeps the last component of a trailing-slash path, so
        reversing the two would hash the package dir on one side and
        site-packages on the other - two roots, one of them with no repos.json.
        """
        package_repo_path = self._package() + os.sep

        self.assertEqual(resolve_cache_path(package_repo_path),
                         resolve_repos_path(package_repo_path))
        self.assertEqual(resolve_cache_path(package_repo_path),
                         self._env_root(self._package()))

    def test_a_relative_package_path_is_resolved_once(self):
        previous = os.getcwd()
        self.addCleanup(os.chdir, previous)
        os.makedirs(self._package(), exist_ok=True)
        os.chdir(self.temp_dir.name)

        relative = os.path.join("venv", "site-packages", "mlc_scripts")

        self.assertEqual(resolve_cache_path(relative),
                         resolve_repos_path(relative))

    def test_the_package_argument_is_mandatory(self):
        """No default value, deliberately.

        A default would let a partial revert of the resolution order in
        Action.__init__ silently restore the shared cache for everyone. Without
        one it is a TypeError at the call site.
        """
        with self.assertRaises(TypeError):
            resolve_cache_path()


CHILD = r'''
import json, logging, os, sys
sys.path.insert(0, os.environ["MLCFLOW_REPO"])
import mlc.action

# find_package_repo() reads importlib.metadata, so a real install cannot be
# faked - and the value has to be in place *before* Action() runs, because both
# roots are resolved in the constructor. Patching the module global is the only
# hook that early; setting action.package_repo_path afterwards, as
# test_add_script_destination.py does for a different purpose, is two lines too
# late to affect resolution.
_fake = os.environ.get("FAKE_PACKAGE_REPO")
if _fake:
    _ver = os.environ.get("FAKE_PACKAGE_VERSION", "9.9.9")
    mlc.action.find_package_repo = lambda: (_fake, _ver)

from mlc.action import Action
from mlc.repo_action import RepoAction

warnings = []


class Collect(logging.Handler):
    def emit(self, record):
        if record.levelno >= logging.WARNING:
            warnings.append(record.getMessage())


logging.getLogger("mlc").addHandler(Collect())

action = Action()

_envs_dir = os.path.join(os.path.expanduser("~"), "MLC", "envs")
_shared = os.path.join(os.path.expanduser("~"), "MLC", "repos")
out = {
    "repos_path": action.repos_path,
    "cache_path": action.cache_path,
    "local_cache_path": action.local_cache_path,
    "local_repo_path": action.local_repo_path,
    "package_repo_path": action.package_repo_path,
    "cache_path_from_registry": action.cache_path_from_registry,
    "env_dirs": sorted(os.listdir(_envs_dir)) if os.path.isdir(_envs_dir) else [],
    "shared_root_exists": os.path.exists(_shared),
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


class RootsHarness:
    """Shared subprocess harness for the two end-to-end classes.

    Deliberately not a TestCase: it carries no tests, and inheriting from one
    would make unittest collect and run this class as well.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def _run(self, home, **env_extra):
        env = dict(os.environ)
        for key in ("MLC_REPOS", "MLC_CACHE", "ADD_CACHE_ITEM",
                    "SEARCH_CACHE", "LIST_REPO", "FAKE_PACKAGE_REPO",
                    "FAKE_PACKAGE_VERSION"):
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

    @staticmethod
    def _orphan_notices(result):
        return [w for w in result["warnings"]
                if "still holds cached entries" in w]

    def _fake_package(self, venv):
        """A package tree find_package_repo() would accept.

        meta.yaml matters: without it _sync_package_repo() emits its own
        warning, which would muddy every warnings assertion here.
        """
        pkg = os.path.join(
            self.temp_dir.name, venv, "site-packages", "mlc_scripts")
        os.makedirs(os.path.join(pkg, "script"), exist_ok=True)
        with open(os.path.join(pkg, "meta.yaml"), "w") as f:
            json.dump({"alias": "mlc-scripts-fixture",
                       "name": "mlc-scripts test fixture",
                       "uid": "0123456789abcdef"}, f)
        return pkg


class ConstructedRootsTest(RootsHarness, unittest.TestCase):
    """End-to-end checks on the roots an Action actually settles on.

    Separate from RootResolutionTest because the interesting behaviour is not
    in the resolver functions: the constructor writes repos.json and then
    _ensure_local_registered() can override the resolved cache root from the
    registry. Both mechanisms guarded here regressed once while the
    pure-function tests above stayed green.

    Runs in a child process with HOME redirected, so default_mlc_root()
    resolves into a scratch directory and the developer's real ~/MLC is never
    read or written.

    Every test in this class runs with *no* package installed - mlc-scripts is
    not a dependency of this repo, so find_package_repo() returns (None, None)
    here and in CI. The packaged tier is covered by PackagedEnvRootsTest
    below, which fakes it; do not assume these tests reach it.
    """

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


class PackagedEnvRootsTest(RootsHarness, unittest.TestCase):
    """End-to-end behaviour when mlc-scripts is installed.

    mlc-scripts is not a dependency of this repo, so find_package_repo()
    returns (None, None) in every other test here and the packaged tier of both
    resolvers would otherwise have no end-to-end coverage at all. These tests
    fake it by patching the module global in the child, before Action() runs.
    """

    def _cache_entries(self, home, env_hash=None):
        base = os.path.join(home, "MLC", "envs")
        if env_hash is None:
            env_hash = os.listdir(base)[0]
        return os.path.join(base, env_hash, "local", "cache")

    def test_a_packaged_environment_gets_its_own_cache_root(self):
        """The headline change: both roots land in the same per-env directory.

        shared_root_exists is the assertion that matters - a packaged install
        must no longer create ~/MLC/repos at all. Before this change the cache
        default put a local repo there on the very first command.
        """
        home, = self._mkdirs("home_pkg")
        pkg = self._fake_package("venvA")

        result, stdout = self._run(home, FAKE_PACKAGE_REPO=pkg, LIST_REPO="1")

        expected = os.path.join(
            home, "MLC", "envs",
            environment_key(os.path.dirname(pkg)))
        self.assertEqual(os.path.realpath(result["cache_path"]),
                         os.path.realpath(expected))
        self.assertEqual(os.path.realpath(result["repos_path"]),
                         os.path.realpath(expected))
        self.assertTrue(result["local_cache_path"].endswith(
            os.path.join("local", "cache")), result["local_cache_path"])
        self.assertTrue(os.path.isdir(result["local_cache_path"]))
        self.assertFalse(result["shared_root_exists"],
                         "a packaged install must not create ~/MLC/repos")
        self.assertFalse(result["cache_path_from_registry"])
        self.assertEqual(self._warned(result), [])
        # Both roots report the package as their origin.
        self.assertEqual(
            stdout.count("(auto: mlc-scripts 9.9.9 at"), 2, stdout)
        self.assertEqual(stdout.count("(default)"), 0, stdout)

    def test_two_environments_do_not_share_a_cache(self):
        """The whole point of the change, stated as a cache miss."""
        home, = self._mkdirs("home_two")
        pkg_a = self._fake_package("venvA")
        pkg_b = self._fake_package("venvB")

        added, _ = self._run(home, FAKE_PACKAGE_REPO=pkg_a,
                             ADD_CACHE_ITEM="entry-a")
        self.assertEqual(added.get("add_return"), 0)

        in_b, _ = self._run(home, FAKE_PACKAGE_REPO=pkg_b, SEARCH_CACHE="1")
        self.assertEqual(in_b.get("search_return"), 0)
        self.assertEqual(in_b.get("search_paths"), [],
                         "environment B must not see environment A's cache")

        in_a, _ = self._run(home, FAKE_PACKAGE_REPO=pkg_a, SEARCH_CACHE="1")
        self.assertEqual(len(in_a.get("search_paths", [])), 1,
                         in_a.get("search_paths"))

        self.assertNotEqual(added["cache_path"], in_b["cache_path"])
        self.assertEqual(len(in_b["env_dirs"]), 2, in_b["env_dirs"])

    def test_the_same_environment_reuses_its_cache_across_runs(self):
        """Isolation must not have cost us reuse within one environment."""
        home, = self._mkdirs("home_reuse")
        pkg = self._fake_package("venvA")

        added, _ = self._run(home, FAKE_PACKAGE_REPO=pkg,
                             ADD_CACHE_ITEM="entry-reuse")
        self.assertEqual(added.get("add_return"), 0)

        repos_json = os.path.join(added["repos_path"], "repos.json")
        before = os.stat(repos_json).st_mtime_ns

        found, _ = self._run(home, FAKE_PACKAGE_REPO=pkg, SEARCH_CACHE="1")

        self.assertEqual(len(found.get("search_paths", [])), 1,
                         found.get("search_paths"))
        self.assertEqual(found["cache_path"], added["cache_path"])
        # A second run must not rewrite the registry it already agrees with.
        self.assertEqual(os.stat(repos_json).st_mtime_ns, before)

    def test_cache_var_overrides_the_per_environment_root(self):
        home, cache = self._mkdirs("home_override", "cache_override")
        pkg = self._fake_package("venvA")

        result, stdout = self._run(home, FAKE_PACKAGE_REPO=pkg,
                                   MLC_CACHE=cache, LIST_REPO="1")

        self.assertEqual(os.path.realpath(result["cache_path"]),
                         os.path.realpath(cache))
        self.assertEqual(
            os.path.realpath(result["repos_path"]),
            os.path.realpath(os.path.join(
                home, "MLC", "envs", environment_key(os.path.dirname(pkg)))))
        # The env root must not have grown a local repo it does not own.
        self.assertFalse(os.path.exists(
            os.path.join(result["repos_path"], "local")))
        self.assertIn("(set by MLC_CACHE)", stdout)
        self.assertIn("(auto: mlc-scripts", stdout)

    def test_the_registry_still_beats_the_per_environment_root(self):
        """Pre-1.4 back-compat must survive the new tier.

        The sibling of test_single_root_upgrade_keeps_its_existing_cache, and
        the reason this change is not a break for MLC_REPOS users.
        """
        home, legacy = self._mkdirs("home_registry", "legacy_registry")
        pkg = self._fake_package("venvA")

        before, _ = self._run(home, MLC_REPOS=legacy, MLC_CACHE=legacy,
                              ADD_CACHE_ITEM="legacy-entry")
        self.assertEqual(before.get("add_return"), 0)

        after, stdout = self._run(home, MLC_REPOS=legacy,
                                  FAKE_PACKAGE_REPO=pkg,
                                  SEARCH_CACHE="1", LIST_REPO="1")

        self.assertEqual(os.path.realpath(after["local_cache_path"]),
                         os.path.realpath(
                             os.path.join(legacy, "local", "cache")))
        self.assertEqual(len(after.get("search_paths", [])), 1,
                         after.get("search_paths"))
        self.assertTrue(after["cache_path_from_registry"])
        self.assertIn("from the registered local repo", stdout)
        # The per-environment root must not even have been created.
        self.assertEqual(after["env_dirs"], [], after["env_dirs"])

    def test_repos_var_with_a_package_reports_the_split(self):
        home, repos = self._mkdirs("home_split", "repos_split")
        pkg = self._fake_package("venvA")

        result, _ = self._run(home, MLC_REPOS=repos, FAKE_PACKAGE_REPO=pkg)

        self.assertEqual(os.path.realpath(result["repos_path"]),
                         os.path.realpath(repos))
        self.assertEqual(
            os.path.realpath(result["cache_path"]),
            os.path.realpath(os.path.join(
                home, "MLC", "envs", environment_key(os.path.dirname(pkg)))))
        warned = self._warned(result)
        self.assertEqual(len(warned), 1, result["warnings"])
        # The message has to name where the cache actually went - a hashed
        # directory the user never chose is the whole reason to say anything.
        self.assertIn(result["cache_path"], warned[0])

    def test_an_orphaned_shared_cache_is_reported_once_and_left_alone(self):
        """The migration case, which every current mlc-scripts user hits.

        Until the cache root became per environment, installing mlc-scripts
        left the cache in ~/MLC/repos - so that directory exists, populated,
        for essentially all of them.
        """
        home, = self._mkdirs("home_orphan")
        pkg = self._fake_package("venvA")

        # Build the populated shared cache through the real code path, with no
        # package installed - exactly how it got there before this change.
        shared = os.path.join(home, "MLC", "repos")
        seeded, _ = self._run(home, MLC_REPOS=shared, MLC_CACHE=shared,
                              ADD_CACHE_ITEM="legacy-entry")
        self.assertEqual(seeded.get("add_return"), 0)

        legacy_cache = os.path.join(shared, "local", "cache")
        fingerprint = self._tree_fingerprint(legacy_cache)

        first, _ = self._run(home, FAKE_PACKAGE_REPO=pkg, LIST_REPO="1")

        notices = self._orphan_notices(first)
        self.assertEqual(len(notices), 1, first["warnings"])
        self.assertIn(legacy_cache, notices[0])
        self.assertIn(first["cache_path"], notices[0])
        self.assertIn(f"MLC_CACHE={shared}", notices[0])

        # Non-destructive: contents and mtimes untouched.
        self.assertEqual(self._tree_fingerprint(legacy_cache), fingerprint)

        # Said once. A read-only command must not repeat it.
        second, _ = self._run(home, FAKE_PACKAGE_REPO=pkg, LIST_REPO="1")
        self.assertEqual(self._orphan_notices(second), [], second["warnings"])
        self.assertEqual(self._tree_fingerprint(legacy_cache), fingerprint)

    def test_no_orphan_notice_when_the_shared_cache_is_empty(self):
        home, = self._mkdirs("home_quiet")
        pkg = self._fake_package("venvA")

        result, _ = self._run(home, FAKE_PACKAGE_REPO=pkg)

        self.assertEqual(self._orphan_notices(result), [], result["warnings"])

    def test_no_orphan_notice_when_the_cache_var_is_set(self):
        """An explicit choice needs no advice."""
        home, cache = self._mkdirs("home_explicit", "cache_explicit")
        pkg = self._fake_package("venvA")

        shared = os.path.join(home, "MLC", "repos")
        self._run(home, MLC_REPOS=shared, MLC_CACHE=shared,
                  ADD_CACHE_ITEM="legacy-entry")

        result, _ = self._run(home, FAKE_PACKAGE_REPO=pkg, MLC_CACHE=cache)

        self.assertEqual(self._orphan_notices(result), [], result["warnings"])

    @staticmethod
    def _tree_fingerprint(path):
        """Every file's relative path, size and mtime under path."""
        seen = []
        for root, _dirs, files in os.walk(path):
            for name in sorted(files):
                full = os.path.join(root, name)
                st = os.stat(full)
                seen.append((os.path.relpath(full, path),
                             st.st_size, st.st_mtime_ns))
        return sorted(seen)


if __name__ == "__main__":
    unittest.main()
