"""mlc must not delete anything inside a pip-installed mlc-scripts.

_sync_package_repo() registers that directory as an ordinary repo, so it shows
up in find(), in the index and in every search result - including the ones that
feed `mlc rm`. pip owns the tree: a delete there corrupts the install with no
record pip can see, and comes back on the next --force-reinstall.

Everything runs in a child process with HOME redirected into a scratch
directory, so the developer's real ~/MLC is never read or written, and
find_package_repo() is patched *before* Action() is constructed because both
roots are resolved in the constructor.

The pairs matter. Refusing the packaged path is only correct if removing an
ordinary repo, a pulled checkout that shares the packaged copy's alias *and*
uid, and a local script all still work - an unconditional refusal would pass
half these tests.
"""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Shared by the packaged fixture and the "pulled checkout" fixture: a pull
# displaces the packaged copy precisely because the uid matches, and the guard
# has to key on the path anyway.
SHARED_UID = "0123456789abcdef"
SHARED_ALIAS = "mlc-scripts-fixture"

# Real automation uid for scripts, copied from an mlperf-automations meta.yaml.
SCRIPT_AUTOMATION_UID = "5b4e0237da074764"

# WarningCode.PACKAGE_MANAGED_TARGET. Written out rather than imported: the
# tests deliberately reach the code only through the child process, so a typo
# in the enum cannot be masked by importing the same constant under test.
PACKAGE_MANAGED_TARGET_CODE = 1007

CHILD = r'''
import hashlib, json, logging, os, sys
sys.path.insert(0, os.environ["MLCFLOW_REPO"])
import yaml

# The refusal returns 0, so the warning record and the warnings payload are the
# only evidence it happened - collect the records before anything logs.
warnings = []


class Collect(logging.Handler):
    def emit(self, record):
        if record.levelno >= logging.WARNING:
            warnings.append(record.getMessage())


logging.getLogger("mlc").addHandler(Collect())

import mlc.action

# Before Action(): both roots are resolved in the constructor, so setting
# action.package_repo_path afterwards would be too late to produce the
# per-environment layout a real packaged install has.
_fake = os.environ["FAKE_PACKAGE_REPO"]
mlc.action.find_package_repo = lambda: (_fake, "9.9.9")

from mlc.action import Action

SHARED_UID = os.environ["SHARED_UID"]
SHARED_ALIAS = os.environ["SHARED_ALIAS"]
AUTOMATION_UID = os.environ["SCRIPT_AUTOMATION_UID"]


def write_repo(path, alias, uid):
    os.makedirs(os.path.join(path, "script"), exist_ok=True)
    with open(os.path.join(path, "meta.yaml"), "w") as f:
        yaml.safe_dump({"alias": alias, "name": alias, "uid": uid}, f)
    return path


def write_script(repo_path, name, uid, tags):
    script_dir = os.path.join(repo_path, "script", name)
    os.makedirs(script_dir, exist_ok=True)
    with open(os.path.join(script_dir, "meta.yaml"), "w") as f:
        yaml.safe_dump({"alias": name, "uid": uid,
                        "automation_alias": "script",
                        "automation_uid": AUTOMATION_UID,
                        "tags": tags}, f)
    return script_dir


def digest(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


# The packaged tree, written before Action() so the first index build sees it.
# meta.yaml matters: without it _sync_package_repo() refuses to register the
# package and the guard would have nothing to find.
write_repo(_fake, SHARED_ALIAS, SHARED_UID)
pkg_script = write_script(_fake, "probe-packaged", "aaaaaaaaaaaaaaa1",
                          ["probe", "fixture"])

action = Action()
action.parent = action

# A script in the local repo, for the cases that must still delete.
local_script = None
if os.environ.get("LOCAL_SCRIPT"):
    local_script = write_script(action.local_repo_path,
                                os.environ["LOCAL_SCRIPT"],
                                "bbbbbbbbbbbbbbb2", ["probe", "fixture"])

# A second registered repo. EXTRA_UNDER_ROOT places it where `mlc pull repo`
# would - directly under the repo root, which is the only shape rm_repo()
# deletes rather than merely unregisters - and the root is a hash of the
# site-packages path, so only the child can build that path. EXTRA_REPO takes
# an absolute path for the cases that need one somewhere else.
extra = os.environ.get("EXTRA_REPO")
if os.environ.get("EXTRA_UNDER_ROOT"):
    extra = os.path.join(action.repos_path, os.environ["EXTRA_UNDER_ROOT"])
if extra:
    write_repo(extra,
               os.environ.get("EXTRA_ALIAS", SHARED_ALIAS),
               os.environ.get("EXTRA_UID", SHARED_UID))

repos_json = os.path.join(action.repos_path, "repos.json")
with open(repos_json) as f:
    entries = json.load(f)

if extra and extra not in entries:
    entries.append(extra)

# An explicit pull unregisters the packaged copy on a uid clash
# (register_repo -> conflicting_repo). Reproduce that so find() sees one
# candidate, which is what makes the alias unambiguous in the real flow.
if os.environ.get("UNREGISTER_PACKAGE"):
    entries = [e for e in entries if os.path.abspath(e) != os.path.abspath(_fake)]

with open(repos_json, "w") as f:
    json.dump(entries, f, indent=2)
action.repos = action.load_repos_and_meta()
action._index = None

# Materialise the index so "the index was not touched" is a real assertion
# rather than a comparison of two missing files.
action.get_index()
index_json = os.path.join(action.repos_path, "index_script.json")

before = {"repos_json": digest(repos_json), "index_json": digest(index_json)}

force = bool(os.environ.get("FORCE"))
if os.environ.get("RM_REPO"):
    res = action.access({"action": "rm", "target": "repo",
                         "repo": os.environ["RM_REPO"], "f": force})
elif os.environ.get("RM_SCRIPT"):
    res = action.access({"action": "rm", "target": "script",
                         "item": os.environ["RM_SCRIPT"], "f": force})
else:
    res = action.access({"action": "rm", "target": "script",
                         "tags": os.environ["RM_TAGS"], "f": force})

out = {
    "return": res["return"],
    "error": res.get("error", ""),
    "warning_codes": [w.get("code") for w in res.get("warnings", [])],
    "warning_descriptions": [w.get("description", "")
                             for w in res.get("warnings", [])],
    "logged_warnings": warnings,
    "repos_path": action.repos_path,
    "package_repo_path": action.package_repo_path,
    "package_dir_exists": os.path.isdir(_fake),
    "package_meta_exists": os.path.isfile(os.path.join(_fake, "meta.yaml")),
    "packaged_script_exists": os.path.isdir(pkg_script),
    "local_script_exists": os.path.isdir(local_script) if local_script else None,
    "extra": extra,
    "extra_exists": os.path.isdir(extra) if extra else None,
    "repos_json_unchanged": digest(repos_json) == before["repos_json"],
    "index_json_unchanged": digest(index_json) == before["index_json"],
    "index_json_existed": before["index_json"] is not None,
    "registered": json.load(open(repos_json)),
}
print("@@JSON@@" + json.dumps(out))
'''


class PackagedRepoGuardTest(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.home = os.path.join(self.temp_dir.name, "home")
        # A realistic shape: the guard's os.sep boundary is only meaningful if
        # the package sits beside siblings sharing its name prefix.
        self.site_packages = os.path.join(
            self.temp_dir.name, "venv", "lib", "python3.12", "site-packages")
        self.package = os.path.join(self.site_packages, "mlc_scripts")
        for path in (self.home, self.package):
            os.makedirs(path, exist_ok=True)

    def _run(self, **env_extra):
        env = dict(os.environ)
        for key in ("MLC_REPOS", "MLC_CACHE", "RM_REPO", "RM_SCRIPT",
                    "RM_TAGS", "FORCE", "EXTRA_REPO", "EXTRA_UNDER_ROOT",
                    "EXTRA_ALIAS", "EXTRA_UID", "LOCAL_SCRIPT",
                    "UNREGISTER_PACKAGE"):
            env.pop(key, None)

        env["HOME"] = self.home
        env["MLCFLOW_REPO"] = REPO_ROOT
        env["FAKE_PACKAGE_REPO"] = self.package
        env["SHARED_UID"] = SHARED_UID
        env["SHARED_ALIAS"] = SHARED_ALIAS
        env["SCRIPT_AUTOMATION_UID"] = SCRIPT_AUTOMATION_UID
        env.update({k: str(v) for k, v in env_extra.items()})

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

    def _assert_refused(self, result):
        # Success on purpose: the request was not malformed, it just has
        # nothing to do. Which is exactly why the assertions below matter -
        # with a 0 exit code, the warning is the only thing that tells a
        # caller apart from a real removal.
        self.assertEqual(result["return"], 0,
                         f"the refusal must not fail the command: {result}")
        self.assertEqual(result["warning_codes"],
                         [PACKAGE_MANAGED_TARGET_CODE],
                         f"expected exactly one 1007 warning, got {result}")

        notice = result["warning_descriptions"][0]
        # Each clause carries its own weight: what it is, that nothing
        # happened, and how to actually achieve the intent.
        self.assertIn(self.package, notice)
        self.assertIn("managed by pip", notice)
        self.assertIn("has NOT been deleted", notice)
        self.assertIn("pip uninstall mlc-scripts", notice)
        self.assertIn("mlc pull repo", notice)

        # Returned *and* logged: a CLI user never inspects the result dict.
        self.assertIn(notice, result["logged_warnings"])

    def _assert_not_refused(self, result):
        """The removal went ahead.

        Needed as its own assertion now that a refusal also returns 0 - without
        checking for the absence of the 1007 warning, every "still removable"
        test below would pass on a guard that refused everything.
        """
        self.assertEqual(result["return"], 0, result["error"])
        self.assertNotIn(PACKAGE_MANAGED_TARGET_CODE, result["warning_codes"],
                         f"the guard fired on a target it should ignore: "
                         f"{result['warning_descriptions']}")

    # ------------------------------------------------------------ repo target

    def test_removing_the_packaged_repo_is_refused(self):
        result, _ = self._run(RM_REPO=SHARED_ALIAS)

        self._assert_refused(result)
        self.assertTrue(result["package_dir_exists"])
        self.assertTrue(result["package_meta_exists"])
        self.assertTrue(result["packaged_script_exists"])
        # Nothing unregistered and nothing de-indexed. The old code stripped
        # the index and unregistered the repo before rm_repo() declined to
        # delete the folder, so success was reported for a no-op.
        self.assertTrue(result["repos_json_unchanged"], result["registered"])
        self.assertTrue(result["index_json_existed"],
                        "the index never materialised, so the next assertion "
                        "would compare two missing files")
        self.assertTrue(result["index_json_unchanged"])
        self.assertIn(self.package, result["registered"])

    def test_force_does_not_override_the_refusal(self):
        result, _ = self._run(RM_REPO=SHARED_ALIAS, FORCE="1")

        self._assert_refused(result)
        self.assertTrue(result["package_dir_exists"])
        self.assertTrue(result["repos_json_unchanged"])

    def test_the_packaged_repo_is_refused_by_absolute_path(self):
        # The guard sits after both branches that resolve repo_path, so a path
        # typed straight at site-packages is covered too.
        result, _ = self._run(RM_REPO=self.package)

        self._assert_refused(result)
        self.assertTrue(result["package_dir_exists"])

    def test_a_pulled_checkout_sharing_alias_and_uid_is_still_removed(self):
        # The decisive case for matching on path rather than identity: a pull
        # produces a repo with the packaged copy's alias *and* uid, and
        # removing it must keep working.
        result, _ = self._run(RM_REPO=SHARED_ALIAS,
                              EXTRA_UNDER_ROOT="clone-fixture",
                              UNREGISTER_PACKAGE="1", FORCE="1")

        self._assert_not_refused(result)
        self.assertFalse(result["extra_exists"],
                         "the checkout should have been deleted")
        self.assertTrue(result["package_dir_exists"],
                        "the packaged copy was never the target")
        self.assertNotIn(result["extra"], result["registered"])

    def test_a_sibling_directory_sharing_the_name_prefix_is_not_guarded(self):
        # mlc_scripts_extra starts with the same characters as the package
        # directory. Without the os.sep boundary a plain startswith would
        # refuse it.
        sibling = os.path.join(self.site_packages, "mlc_scripts_extra")
        result, _ = self._run(RM_REPO="sibling-fixture", EXTRA_REPO=sibling,
                              EXTRA_ALIAS="sibling-fixture",
                              EXTRA_UID="fedcba9876543210", FORCE="1")

        # It sits outside the repo root, so rm_repo() unregisters rather than
        # deleting - the point is only that the guard stayed out of the way.
        self._assert_not_refused(result)
        self.assertNotIn(sibling, result["registered"])

    # ---------------------------------------------------------- script target

    def test_removing_a_packaged_script_is_refused(self):
        result, _ = self._run(RM_SCRIPT="probe-packaged", FORCE="1")

        self._assert_refused(result)
        self.assertTrue(result["packaged_script_exists"],
                        "a script was deleted out of site-packages")

    def test_a_local_script_is_still_removed(self):
        result, _ = self._run(RM_SCRIPT="probe-local", LOCAL_SCRIPT="probe-local",
                              FORCE="1")

        self._assert_not_refused(result)
        self.assertFalse(result["local_script_exists"])
        self.assertTrue(result["packaged_script_exists"])

    def test_a_tags_query_spanning_both_removes_neither(self):
        # The delete loop rmtree's as it iterates, so the guard runs over the
        # whole result set first. Without that, the local script would already
        # be gone by the time the packaged one was reached.
        result, _ = self._run(RM_TAGS="probe,fixture",
                              LOCAL_SCRIPT="probe-local", FORCE="1")

        self._assert_refused(result)
        self.assertTrue(result["packaged_script_exists"])
        self.assertTrue(result["local_script_exists"],
                        "the local script was deleted before the refusal - the "
                        "guard is running inside the delete loop")


if __name__ == "__main__":
    unittest.main()
