import json
import os
import subprocess
import sys
import tempfile
import unittest

from mlc.action import Action


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class MarkTmpCacheCliTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.previous_cwd = os.getcwd()
        self.addCleanup(os.chdir, self.previous_cwd)
        os.chdir(self.temp_dir.name)

        self.previous_mlc_repos = os.environ.get("MLC_REPOS")
        self.addCleanup(self._restore_env)
        os.environ["MLC_REPOS"] = os.path.join(self.temp_dir.name, "repos")

        action = Action()
        action.parent = None
        res = action.add({
            "target_name": "cache",
            "item": "sample-cache",
            "tags": "get,dataset,igbh"
        })
        self.assertEqual(res["return"], 0)
        self.cache_path = res["path"]

    def _restore_env(self):
        if self.previous_mlc_repos is None:
            os.environ.pop("MLC_REPOS", None)
        else:
            os.environ["MLC_REPOS"] = self.previous_mlc_repos

    def _run_cli(self):
        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = REPO_ROOT if not existing_pythonpath else REPO_ROOT + \
            os.pathsep + existing_pythonpath
        return subprocess.run(
            [sys.executable, "-m", "mlc.main", "mark-tmp",
                "cache", "--tags=get,dataset,igbh"],
            cwd=self.temp_dir.name,
            env=env,
            capture_output=True,
            text=True,
            check=False
        )

    def test_mark_tmp_adds_tmp_tag_without_duplicates(self):
        first_run = self._run_cli()
        self.assertEqual(first_run.returncode, 0, msg=first_run.stderr)

        second_run = self._run_cli()
        self.assertEqual(second_run.returncode, 0, msg=second_run.stderr)

        with open(os.path.join(self.cache_path, "meta.json"), "r") as file:
            meta = json.load(file)

        self.assertIn("tmp", meta["tags"])
        self.assertEqual(meta["tags"].count("tmp"), 1)
        self.assertTrue(os.path.isdir(self.cache_path))


if __name__ == "__main__":
    unittest.main()
