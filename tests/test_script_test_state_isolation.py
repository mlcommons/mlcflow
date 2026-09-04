"""Each variation of a `mlc test script` run must start from a clean state.

`ScriptAutomation.run` falls back to the instance attributes (`env`,
`add_deps_recursive`, ...) whenever the caller does not pass the matching key,
so the `test` action - which loops over `tests.run_inputs[*].variations_list`
on a single automation instance - used to carry the first variation into the
next one. In mlperf-automations that showed up as
`download-and-extract,_r2-downloader,_rclone` and a "Multiple variation tags
selected for the variation group" failure on the second variation.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEP_META = """\
alias: state-isolation-dep
uid: a1b2c3d4e5f60001
automation_alias: script
automation_uid: 5b4e0237da074764
tags:
- state-isolation
- dep
variations:
  a:
    group: tool
    env:
      STATE_ISOLATION_TOOL: a
  b:
    group: tool
    default: true
    env:
      STATE_ISOLATION_TOOL: b
"""

MAIN_META = """\
alias: state-isolation-main
uid: a1b2c3d4e5f60002
automation_alias: script
automation_uid: 5b4e0237da074764
tags:
- state-isolation
- main
deps:
- tags: state-isolation,dep
  names:
  - d1
variations:
  a:
    group: tool
    add_deps_recursive:
      d1:
        tags: _a
  b:
    group: tool
    default: true
    add_deps_recursive:
      d1:
        tags: _b
tests:
  run_inputs:
  - variations_list:
    - a
    - b
"""

CUSTOMIZE = textwrap.dedent(
    """\
    def preprocess(i):
        return {'return': 0}


    def postprocess(i):
        return {'return': 0}
    """
)


class ScriptTestStateIsolationTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.previous_cwd = os.getcwd()
        self.addCleanup(os.chdir, self.previous_cwd)

        self.content_repo = os.path.join(self.temp_dir.name, "content-repo")
        self._write_content_repo()

        self.mlc_repos = os.path.join(self.temp_dir.name, "repos")
        os.makedirs(self.mlc_repos, exist_ok=True)
        os.chdir(self.temp_dir.name)

        self._run_cli(["pull", "repo", self.content_repo], check=True)

    def _write_content_repo(self):
        script_dir = os.path.join(self.content_repo, "script")
        for name, meta in (("state-isolation-dep", DEP_META),
                           ("state-isolation-main", MAIN_META)):
            path = os.path.join(script_dir, name)
            os.makedirs(path)
            with open(os.path.join(path, "meta.yaml"), "w") as f:
                f.write(meta)
            with open(os.path.join(path, "customize.py"), "w") as f:
                f.write(CUSTOMIZE)

        with open(os.path.join(self.content_repo, "meta.yaml"), "w") as f:
            f.write("alias: local@state-isolation-repo\n"
                    "uid: a1b2c3d4e5f60000\n"
                    "git: true\n"
                    "version: 0.0.1\n")

        # `mlc pull repo <path>` clones, so the source has to be a git repo.
        git = shutil.which("git")
        if git is None:
            self.skipTest("git is required to register a local MLC repo")
        for args in (["init", "-q", "."],
                     ["add", "-A"],
                     ["-c", "user.email=test@example.com",
                      "-c", "user.name=test",
                      "commit", "-q", "-m", "init"]):
            subprocess.run([git] + args, cwd=self.content_repo, check=True,
                           capture_output=True)

    def _run_cli(self, args, check=False):
        env = os.environ.copy()
        env["MLC_REPOS"] = self.mlc_repos
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = REPO_ROOT if not existing_pythonpath else REPO_ROOT + \
            os.pathsep + existing_pythonpath
        result = subprocess.run(
            [sys.executable, "-m", "mlc.main"] + args,
            cwd=self.temp_dir.name,
            env=env,
            capture_output=True,
            text=True,
            check=False
        )
        if check:
            self.assertEqual(result.returncode, 0,
                             msg=result.stdout + result.stderr)
        return result

    def test_variations_do_not_leak_into_the_next_test_run(self):
        result = self._run_cli(
            ["test", "script", "a1b2c3d4e5f60002", "--quiet"])
        output = result.stdout + result.stderr

        self.assertNotIn("Multiple variation tags selected", output)
        # Second variation must resolve its dep with `_b` only, not `_b,_a`.
        self.assertIn("mlcr state-isolation,dep,_a", output)
        self.assertIn("mlcr state-isolation,dep,_b\n", output)
        for leaked in ("state-isolation,dep,_a,_b",
                       "state-isolation,dep,_b,_a"):
            self.assertNotIn(leaked, output)
        self.assertEqual(result.returncode, 0, msg=output)


if __name__ == "__main__":
    unittest.main()
