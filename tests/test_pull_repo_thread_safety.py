import json
import os
import subprocess
import tempfile
import threading
import unittest
import yaml
from unittest.mock import patch, MagicMock

from mlc.repo_action import unregister_repo, RepoAction
from mlc.action import Action
from mlc import utils


class _RepoActionTestBase(unittest.TestCase):
    """Shared MLC temp-environment setup. Deliberately holds no tests itself,
    so subclassing it does not re-run another class's cases."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        self.previous_mlc_repos = os.environ.get("MLC_REPOS")
        self.addCleanup(self._restore_env)
        os.environ["MLC_REPOS"] = os.path.join(self.temp_dir.name, "repos")

        # Bootstrap a minimal MLC environment (creates repos.json, local
        # meta.yaml)
        action = Action()
        action.parent = None
        self.repos_path = action.repos_path
        self.repos_file = os.path.join(self.repos_path, "repos.json")

    def _restore_env(self):
        if self.previous_mlc_repos is None:
            os.environ.pop("MLC_REPOS", None)
        else:
            os.environ["MLC_REPOS"] = self.previous_mlc_repos

    def _make_repo_action(self):
        action = Action()
        action.parent = None
        return RepoAction(parent=action)

    def _make_fake_repo_dir(self, name):
        """Create a temp directory with a minimal meta.yaml that register_repo accepts."""
        repo_dir = os.path.join(self.temp_dir.name, name)
        os.makedirs(repo_dir, exist_ok=True)
        uid = utils.get_new_uid()['uid']
        meta = {'uid': uid, 'alias': name}
        with open(os.path.join(repo_dir, 'meta.yaml'), 'w') as f:
            yaml.dump(meta, f)
        return repo_dir, meta


class RegisterRepoThreadSafetyTest(_RepoActionTestBase):
    """
    Verifies that concurrent calls to register_repo / unregister_repo do not
    corrupt repos.json (no entries lost, no duplicates).
    """

    def test_concurrent_register_repo_no_data_loss(self):
        """
        N threads each call RepoAction.register_repo with a unique repo path;
        all N must appear in repos.json at the end with no duplicates.
        """
        n_threads = 10
        fake_repos = [self._make_fake_repo_dir(
            f"fake-repo-register-{i}") for i in range(n_threads)]
        errors = []

        def register(repo_path, meta):
            try:
                ra = self._make_repo_action()
                ra.register_repo(repo_path, meta)
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(target=register, args=(path, meta))
            for path, meta in fake_repos
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], msg=f"Threads raised errors: {errors}")

        with open(self.repos_file, "r") as f:
            final_list = json.load(f)

        for path, _ in fake_repos:
            self.assertIn(
                path,
                final_list,
                msg=f"{path} missing from repos.json")

        # No duplicates
        self.assertEqual(len(final_list), len(set(final_list)),
                         msg="repos.json contains duplicate entries")

    def test_concurrent_unregister_repo_no_data_loss(self):
        """
        Pre-populate repos.json with N paths; N threads each unregister one
        unique path; all fake paths must be gone afterwards with no duplicates.
        """
        n_threads = 10
        fake_paths = [
            f"/tmp/fake-repo-unregister-{i}" for i in range(n_threads)]

        # Seed repos.json with all fake paths
        with open(self.repos_file, "r") as f:
            existing = json.load(f)
        with open(self.repos_file, "w") as f:
            json.dump(existing + fake_paths, f, indent=2)

        errors = []

        def unregister(path):
            try:
                unregister_repo(path, self.repos_file)
            except Exception as exc:
                errors.append(exc)

        threads = [
            threading.Thread(
                target=unregister, args=(
                    p,)) for p in fake_paths]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], msg=f"Threads raised errors: {errors}")

        with open(self.repos_file, "r") as f:
            final_list = json.load(f)

        for path in fake_paths:
            self.assertNotIn(path, final_list,
                             msg=f"{path} was not removed from repos.json")

        # No duplicates
        self.assertEqual(len(final_list), len(set(final_list)),
                         msg="repos.json contains duplicate entries")

    def test_concurrent_pull_repo_clone_called_once(self):
        """
        N threads all call pull_repo for the same absent repo URL simultaneously;
        git clone must be invoked exactly once (the per-repo FileLock prevents
        duplicate clones).
        """
        n_threads = 5
        repo_url = "https://github.com/example/test-repo.git"
        repo_path = os.path.join(self.repos_path, "example@test-repo")
        clone_call_count = []
        count_lock = threading.Lock()
        errors = []
        results = []
        results_lock = threading.Lock()
        # Release all threads at once so they genuinely contend for the lock.
        start_together = threading.Barrier(n_threads, timeout=60)

        original_subprocess_run = subprocess.run

        def completed(cmd, returncode=0, stdout="", stderr=""):
            return subprocess.CompletedProcess(cmd, returncode, stdout, stderr)

        def fake_subprocess_run(cmd, *args, **kwargs):
            """Model the git calls pull_repo makes, against a fake checkout.

            The clone must create whatever destination it was handed -- that is
            now a '.tmp-clone' sibling that pull_repo renames into place, not
            repo_path itself -- so the destination is read from the command.
            """
            if not (isinstance(cmd, (list, tuple))
                    and cmd and cmd[0] == 'git'):
                return original_subprocess_run(cmd, *args, **kwargs)

            if 'clone' in cmd:
                with count_lock:
                    clone_call_count.append(1)
                destination = cmd[-1]
                os.makedirs(destination, exist_ok=True)
                # .git marks it as a checkout for the rev-parse probe below.
                os.makedirs(os.path.join(destination, '.git'), exist_ok=True)
                meta = {
                    'uid': utils.get_new_uid()['uid'],
                    'alias': 'example@test-repo'}
                with open(os.path.join(destination, 'meta.yaml'), 'w') as f:
                    yaml.dump(meta, f)
                return completed(cmd)

            if 'rev-parse' in cmd:
                # _is_valid_git_repo's probe: healthy only once .git exists.
                target = cmd[cmd.index('-C') + 1]
                if os.path.isdir(os.path.join(target, '.git')):
                    return completed(cmd, stdout="0" * 40 + "\n")
                return completed(
                    cmd, returncode=128,
                    stderr="fatal: not a git repository\n")

            # status reports a clean tree; pull/checkout succeed silently.
            return completed(cmd)

        def do_pull():
            try:
                ra = self._make_repo_action()
                start_together.wait()
                result = ra.pull_repo(repo_url)
                with results_lock:
                    results.append(result)
            except Exception as exc:
                errors.append(exc)

        # Patch once, in the main thread. Patching inside each thread would let
        # the first thread to finish restore the real subprocess.run while the
        # others are still inside pull_repo, which would shell out to real git.
        with patch('mlc.repo_action.subprocess.run',
                   side_effect=fake_subprocess_run):
            threads = [threading.Thread(target=do_pull)
                       for _ in range(n_threads)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual(errors, [], msg=f"Threads raised errors: {errors}")
        # pull_repo returns error dicts rather than raising, so an empty
        # `errors` list on its own would not tell us the calls succeeded.
        self.assertEqual(len(results), n_threads,
                         msg=f"Expected {n_threads} results, got {results}")
        failed = [r for r in results if r.get('return', 1) != 0]
        self.assertEqual(
            failed, [], msg=f"pull_repo returned errors: {failed}")

        self.assertEqual(
            len(clone_call_count), 1,
            msg=f"git clone was called {
                len(clone_call_count)} times; expected exactly 1"
        )
        self.assertTrue(
            os.path.isdir(repo_path),
            msg=f"{repo_path} should exist after the clone was renamed into place")
        self.assertFalse(
            os.path.exists(repo_path + ".tmp-clone"),
            msg="temporary clone directory should not survive a successful pull")


class PullRepoPartialCloneTest(_RepoActionTestBase):
    """Recovery from clones that died part-way through.

    The lock gives mutual exclusion but not atomicity: a clone killed by
    SIGKILL/OOM/a dropped link leaves a directory with a .git but no HEAD,
    which every later pull would otherwise treat as a healthy checkout.
    """

    def _fake_git(self, clone_calls, fail_clone=False):
        original_subprocess_run = subprocess.run

        def fake(cmd, *args, **kwargs):
            if not (isinstance(cmd, (list, tuple))
                    and cmd and cmd[0] == 'git'):
                return original_subprocess_run(cmd, *args, **kwargs)
            if 'clone' in cmd:
                clone_calls.append(cmd)
                if fail_clone:
                    # Model an abrupt death: the destination is left behind
                    # half-written rather than cleaned up by git.
                    os.makedirs(os.path.join(cmd[-1], '.git'), exist_ok=True)
                    raise subprocess.CalledProcessError(128, cmd)
                os.makedirs(os.path.join(cmd[-1], '.git'), exist_ok=True)
                with open(os.path.join(cmd[-1], 'meta.yaml'), 'w') as f:
                    yaml.dump(
                        {'uid': utils.get_new_uid()['uid'],
                         'alias': 'example@test-repo'}, f)
                return subprocess.CompletedProcess(cmd, 0, "", "")
            if 'rev-parse' in cmd:
                target = cmd[cmd.index('-C') + 1]
                # Only a directory carrying our HEAD marker is "healthy".
                if os.path.exists(os.path.join(target, '.git', 'HEAD_OK')):
                    return subprocess.CompletedProcess(
                        cmd, 0, "0" * 40 + "\n", "")
                return subprocess.CompletedProcess(cmd, 128, "", "fatal\n")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        return fake

    def test_interrupted_clone_is_discarded_and_recloned(self):
        """A leftover half-clone must be removed and cloned again, not pulled."""
        repo_url = "https://github.com/example/test-repo.git"
        repo_path = os.path.join(self.repos_path, "example@test-repo")

        # The wreckage an interrupted clone leaves: a .git, but no HEAD.
        os.makedirs(os.path.join(repo_path, '.git'), exist_ok=True)
        poison_marker = os.path.join(repo_path, 'left-over-from-interruption')
        with open(poison_marker, 'w') as f:
            f.write('x')

        clone_calls = []
        fake = self._fake_git(clone_calls)

        def healthy_clone(cmd, *args, **kwargs):
            result = fake(cmd, *args, **kwargs)
            if 'clone' in cmd:
                open(os.path.join(cmd[-1], '.git', 'HEAD_OK'), 'w').close()
            return result

        ra = self._make_repo_action()
        with patch('mlc.repo_action.subprocess.run',
                   side_effect=healthy_clone):
            result = ra.pull_repo(repo_url)

        self.assertEqual(result.get('return'), 0, msg=str(result))
        self.assertEqual(len(clone_calls), 1,
                         msg="the broken checkout should have been re-cloned")
        self.assertFalse(
            os.path.exists(poison_marker),
            msg="leftovers from the interrupted clone were not removed")

    def test_failed_clone_leaves_no_partial_directory(self):
        """A clone that dies must leave repo_path absent, not half-populated."""
        repo_url = "https://github.com/example/test-repo.git"
        repo_path = os.path.join(self.repos_path, "example@test-repo")

        clone_calls = []
        ra = self._make_repo_action()
        with patch('mlc.repo_action.subprocess.run',
                   side_effect=self._fake_git(clone_calls, fail_clone=True)):
            result = ra.pull_repo(repo_url)

        self.assertNotEqual(result.get('return'), 0,
                            msg="a failed clone must report failure")
        self.assertFalse(
            os.path.exists(repo_path),
            msg=f"{repo_path} must not exist after a failed clone")
        self.assertFalse(
            os.path.exists(repo_path + ".tmp-clone"),
            msg="the temporary clone directory must be cleaned up")


class ReposJsonAtomicWriteTest(_RepoActionTestBase):
    """repos.json must never be observable in a truncated state.

    Action.load_repos_and_meta() and Action.load_repos() read it with a bare
    json.load and no lock, so the writer's lock alone does not protect them.
    """

    def test_reader_never_observes_a_truncated_file(self):
        from mlc import repo_action as repo_action_module

        with open(self.repos_file) as f:
            original = json.load(f)
        observed = []
        real_dump = repo_action_module.json.dump

        def dump_then_peek(data, fp, *args, **kwargs):
            real_dump(data, fp, *args, **kwargs)
            fp.flush()
            # Mid-write: a concurrent reader hitting repos.json right now must
            # still see the previous complete file, not a truncated one.
            with open(self.repos_file) as reader:
                observed.append(json.load(reader))

        with patch.object(repo_action_module.json, 'dump', dump_then_peek):
            repo_action_module._atomic_write_json(
                self.repos_file, original + ["/tmp/atomic-write-probe"])

        self.assertEqual(
            observed, [original],
            msg="a reader saw something other than the previous complete file")
        with open(self.repos_file) as f:
            self.assertIn("/tmp/atomic-write-probe", json.load(f))

    def test_failed_write_leaves_original_intact(self):
        from mlc import repo_action as repo_action_module

        with open(self.repos_file) as f:
            original = json.load(f)

        # A set is not JSON-serialisable, so json.dump raises part-way.
        with self.assertRaises(TypeError):
            repo_action_module._atomic_write_json(
                self.repos_file, original + [{"unserialisable"}])

        with open(self.repos_file) as f:
            self.assertEqual(json.load(f), original)
        self.assertFalse(os.path.exists(self.repos_file + ".tmp"),
                         msg="temp file left behind after a failed write")


class RepoLockTimeoutTest(unittest.TestCase):
    """The per-repo lock timeout must be overridable for slow cold clones."""

    def setUp(self):
        self.previous = os.environ.get("MLC_REPO_LOCK_TIMEOUT")
        self.addCleanup(self._restore)

    def _restore(self):
        if self.previous is None:
            os.environ.pop("MLC_REPO_LOCK_TIMEOUT", None)
        else:
            os.environ["MLC_REPO_LOCK_TIMEOUT"] = self.previous

    def test_default_and_override(self):
        from mlc.repo_action import (
            _get_repo_lock_timeout, DEFAULT_REPO_LOCK_TIMEOUT)

        os.environ.pop("MLC_REPO_LOCK_TIMEOUT", None)
        self.assertEqual(_get_repo_lock_timeout(), DEFAULT_REPO_LOCK_TIMEOUT)

        os.environ["MLC_REPO_LOCK_TIMEOUT"] = "7200"
        self.assertEqual(_get_repo_lock_timeout(), 7200)

    def test_invalid_values_fall_back_to_default(self):
        from mlc.repo_action import (
            _get_repo_lock_timeout, DEFAULT_REPO_LOCK_TIMEOUT)

        for bad in ("not-a-number", "-5", "0", ""):
            os.environ["MLC_REPO_LOCK_TIMEOUT"] = bad
            self.assertEqual(
                _get_repo_lock_timeout(), DEFAULT_REPO_LOCK_TIMEOUT,
                msg=f"{bad!r} should have fallen back to the default")


if __name__ == "__main__":
    unittest.main()
