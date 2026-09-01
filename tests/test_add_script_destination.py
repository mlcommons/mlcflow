"""Where `mlc add script <name>` puts the new script, and when cp warns.

`cp` defaults the destination to the repo the *template* came from. Templates
normally live in an installed mlc-scripts, so that default would author into
site-packages: wiped by the next upgrade, impossible on a read-only install.
ScriptAction.add() therefore rewrites a bare name to `local:<name>`
unconditionally - the destination does not depend on where the template was
found, which is what makes `mlc add script foo` predictable.

An explicit `<repo>:` prefix is the documented way to aim somewhere else, and it
is honoured even when it names the packaged repo - `cp` only warns there,
because unlike `mlc rm` it is not destroying anything the user did not ask to
write. Those two halves are why the redirect and the warning are tested
together.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# Deliberately not "template,generic": those tags also match the real
# template-script in an installed mlc-scripts or a pulled mlperf-automations,
# and a second match makes cp() prompt interactively, which would hang here.
TEMPLATE_TAGS = "fixture-template,generic"

CONTENT_ALIAS = "fixture-content"

CHILD = r'''
import json, logging, os, sys
sys.path.insert(0, os.environ["MLCFLOW_REPO"])
import yaml
from mlc.action import Action
from mlc.script_action import ScriptAction

messages = []


class Collect(logging.Handler):
    def emit(self, record):
        messages.append(record.getMessage())


collector = logging.getLogger("mlc")
collector.addHandler(Collect())
# setup_logging() skips its body - including its setLevel(INFO) - when a handler
# is already present, so the level has to be set here or INFO records are
# filtered out at the root default of WARNING and never reach Collect.
collector.setLevel(logging.INFO)

# A content repo holding one template. Written before Action() so the first
# index build sees it.
content = os.environ["CONTENT_REPO"]
template_dir = os.path.join(content, "script", "fixture-template-script")
os.makedirs(template_dir, exist_ok=True)
with open(os.path.join(content, "meta.yaml"), "w") as f:
    yaml.safe_dump({"alias": os.environ["CONTENT_ALIAS"],
                    "uid": "0123456789abcdef"}, f)
with open(os.path.join(template_dir, "meta.yaml"), "w") as f:
    yaml.safe_dump({"alias": "fixture-template-script",
                    "uid": "fedcba9876543210",
                    "automation_alias": "script",
                    "automation_uid": "5b4e0237da074764",
                    "tags": os.environ["TEMPLATE_TAGS"].split(",")}, f)

action = Action()

# Register it the way repos.json records repos, then reload and drop the
# cached index so the template is searchable.
repos_json = os.path.join(action.repos_path, "repos.json")
with open(repos_json) as f:
    entries = json.load(f)
if content not in entries:
    entries.append(content)
    with open(repos_json, "w") as f:
        json.dump(entries, f, indent=2)
action.repos = action.load_repos_and_meta()
action._index = None

# find_package_repo() reads importlib.metadata, so a real pip install cannot be
# faked here - but it does not need to be. package_repo_path is a plain
# attribute, and pointing it at the fixture is exactly the state a packaged
# install produces: the template resolves out of a directory pip owns.
if os.environ.get("AS_PACKAGE"):
    action.package_repo_path = content

new_script = os.environ["NEW_SCRIPT"]
script_action = ScriptAction(action)
script_action.parent = action
res = script_action.add({"item": new_script,
                         "template_tags": os.environ["TEMPLATE_TAGS"],
                         "tags": "probe,fixture"})

# The bare name the script is created under, once any "<repo>:" prefix is off.
leaf = new_script.split(":")[-1]

out = {
    "return": res["return"],
    "error": res.get("error", ""),
    "local_repo_path": action.local_repo_path,
    "content_repo_path": content,
    "in_local": os.path.isdir(
        os.path.join(action.local_repo_path, "script", leaf)),
    "in_content": os.path.isdir(os.path.join(content, "script", leaf)),
    "messages": messages,
}
print("@@JSON@@" + json.dumps(out))
'''


class AddScriptDestinationTest(unittest.TestCase):
    """Both halves are needed and neither is sufficient.

    The packaged case alone also passes under a redirect that never fires, and
    the ordinary case alone also passes under one that always fires - only the
    pair pins "always local, regardless of the template's origin".
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def _run(self, new_script, as_package):
        env = dict(os.environ)
        for key in ("MLC_REPOS", "MLC_CACHE", "AS_PACKAGE"):
            env.pop(key, None)

        home = os.path.join(self.temp_dir.name, "home")
        content = os.path.join(self.temp_dir.name, "content")
        # cwd inside the scratch dir: Action() writes .mlc-log.txt into it.
        cwd = os.path.join(self.temp_dir.name, "cwd")
        for path in (home, content, cwd):
            os.makedirs(path, exist_ok=True)

        env["HOME"] = home
        env["MLCFLOW_REPO"] = REPO_ROOT
        env["CONTENT_REPO"] = content
        env["CONTENT_ALIAS"] = CONTENT_ALIAS
        env["TEMPLATE_TAGS"] = TEMPLATE_TAGS
        env["NEW_SCRIPT"] = new_script
        if as_package:
            env["AS_PACKAGE"] = "1"

        proc = subprocess.run([sys.executable, "-c", CHILD], env=env, cwd=cwd,
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0,
                         f"child failed:\n{proc.stdout}\n{proc.stderr}")
        payload = next(line for line in proc.stdout.splitlines()
                       if line.startswith("@@JSON@@"))
        result = json.loads(payload[len("@@JSON@@"):])
        self.assertEqual(result["return"], 0, result["error"])
        return result, content

    @staticmethod
    def _packaged_warnings(result):
        return [m for m in result["messages"]
                if "belongs to the installed mlc-scripts" in m]

    # ------------------------------------------- the bare-name redirect

    def test_a_bare_name_authors_into_local_when_the_template_is_packaged(
            self):
        result, content = self._run("probe-packaged", as_package=True)

        self.assertTrue(result["in_local"],
                        f"not in {result['local_repo_path']}/script")
        self.assertFalse(
            result["in_content"],
            "the new script was written into the repo pip owns, where the "
            "next upgrade deletes it")
        # cp never sees the packaged path, so its warning must stay quiet -
        # otherwise the redirect happened *and* the user was told off for
        # something they did not do.
        self.assertEqual(self._packaged_warnings(result), [],
                         result["messages"])

    def test_a_bare_name_authors_into_local_from_an_ordinary_repo_too(self):
        # The redirect is unconditional by design: `mlc add script foo` should
        # land in the same place whether or not mlc-scripts happens to be
        # installed. Aiming elsewhere is what the "<repo>:" prefix is for.
        result, content = self._run("probe-ordinary", as_package=False)

        self.assertTrue(result["in_local"],
                        "a bare name must author into local regardless of "
                        "where the template came from")
        self.assertFalse(result["in_content"])
        self.assertEqual(self._packaged_warnings(result), [])

    # ------------------------------------------------- the explicit prefix

    def test_an_explicit_repo_prefix_overrides_the_redirect(self):
        result, content = self._run(f"{CONTENT_ALIAS}:probe-explicit",
                                    as_package=False)

        self.assertTrue(result["in_content"],
                        "an explicit destination was ignored, so there is no "
                        "way to author outside local")
        self.assertFalse(result["in_local"])

    def test_an_explicit_packaged_destination_warns_but_still_writes(self):
        # The asymmetry worth pinning: `mlc rm` refuses on the packaged tree,
        # cp only warns. Nothing is being destroyed, and the user named the
        # destination explicitly - so it writes, and says what will happen to
        # it.
        result, content = self._run(f"{CONTENT_ALIAS}:probe-into-package",
                                    as_package=True)

        self.assertTrue(result["in_content"],
                        "an explicit destination must be honoured even when it "
                        "is the packaged repo")
        warnings = self._packaged_warnings(result)
        self.assertEqual(len(warnings), 1, result["messages"])
        self.assertIn(content, warnings[0])
        self.assertIn("lost on the next upgrade", warnings[0])
        self.assertIn("local:", warnings[0])


if __name__ == "__main__":
    unittest.main()
