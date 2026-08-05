import json
import os
import subprocess
import sys
import tempfile
import unittest

from mlc.action import Action


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WORKERS = 3
REPOS_PER_WORKER = 12

# Registers REPOS_PER_WORKER distinct repos in a tight loop. Run concurrently,
# these interleave their repos.json read-modify-write; without a lock the
# slower writer overwrites the other's entry with a list that never contained
# it (lost update), or a reader catches the file mid-write (JSONDecodeError).
WORKER_SCRIPT = """
import os, sys
from mlc.action import Action
from mlc.repo_action import RepoAction

repos_path, wid, count = sys.argv[1], sys.argv[2], int(sys.argv[3])
action = Action()
action.parent = None

for j in range(count):
    tag = "w%s_r%d" % (wid, j)
    repo_path = os.path.join(repos_path, tag)
    uid = ("%016x" % (abs(hash(tag)) % (16 ** 16)))
    RepoAction(action).register_repo(
        repo_path, {"alias": tag, "uid": uid, "path": repo_path})
"""


class ReposJsonConcurrencyTest(unittest.TestCase):
    """Concurrent `mlc pull repo` runs must not drop each other's entries."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.previous_cwd = os.getcwd()
        self.addCleanup(os.chdir, self.previous_cwd)
        os.chdir(self.temp_dir.name)

        self.repos_path = os.path.join(self.temp_dir.name, "repos")
        self.previous_mlc_repos = os.environ.get("MLC_REPOS")
        self.addCleanup(self._restore_env)
        os.environ["MLC_REPOS"] = self.repos_path

        # Creates repos.json seeded with the local repo.
        Action()

    def _restore_env(self):
        if self.previous_mlc_repos is None:
            os.environ.pop("MLC_REPOS", None)
        else:
            os.environ["MLC_REPOS"] = self.previous_mlc_repos

    def _seed_repo(self, tag):
        repo_path = os.path.join(self.repos_path, tag)
        os.makedirs(repo_path, exist_ok=True)
        uid = "%016x" % (abs(hash(tag)) % (16 ** 16))
        with open(os.path.join(repo_path, "meta.yaml"), "w") as f:
            f.write(f"alias: {tag}\nuid: {uid}\n")
        return tag

    def _env(self):
        env = os.environ.copy()
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = REPO_ROOT if not existing_pythonpath else REPO_ROOT + \
            os.pathsep + existing_pythonpath
        return env

    def test_concurrent_register_repo_keeps_every_entry(self):
        expected = set()
        for wid in range(WORKERS):
            for j in range(REPOS_PER_WORKER):
                expected.add(self._seed_repo(f"w{wid}_r{j}"))

        processes = [
            subprocess.Popen(
                [sys.executable, "-c", WORKER_SCRIPT, self.repos_path,
                 str(wid), str(REPOS_PER_WORKER)],
                env=self._env(),
                cwd=self.temp_dir.name,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True)
            for wid in range(WORKERS)
        ]

        for process in processes:
            stdout, stderr = process.communicate(timeout=300)
            self.assertEqual(
                process.returncode, 0,
                f"worker failed:\nstdout:\n{stdout}\nstderr:\n{stderr}")

        with open(os.path.join(self.repos_path, "repos.json")) as f:
            registered = {os.path.basename(path) for path in json.load(f)}

        self.assertEqual(
            expected - registered, set(),
            "entries were lost from repos.json by a concurrent writer")


if __name__ == "__main__":
    unittest.main()
