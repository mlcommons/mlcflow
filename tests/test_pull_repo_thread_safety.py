import json
import os
import subprocess
import tempfile
import threading
import unittest
import yaml
from unittest.mock import patch, MagicMock
from filelock import FileLock

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
                # _git_repo_state's probe. --show-toplevel echoes the repo
                # root, which the caller compares against repo_path.
                target = cmd[cmd.index('-C') + 1]
                if os.path.isdir(os.path.join(target, '.git')):
                    return completed(cmd, stdout=target + "\n")
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
            msg=(f"git clone was called {len(clone_call_count)} times; "
                 "expected exactly 1")
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
                # Only a directory carrying our HEAD marker is "healthy";
                # anything else is definitively not a repository, so the
                # caller is allowed to remove it.
                if os.path.exists(os.path.join(target, '.git', 'HEAD_OK')):
                    return subprocess.CompletedProcess(
                        cmd, 0, target + "\n", "")
                return subprocess.CompletedProcess(
                    cmd, 128, "",
                    "fatal: not a git repository (or any of the parent "
                    "directories): .git\n")
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

    def test_repo_path_is_absent_while_the_clone_is_running(self):
        """The clone must land somewhere else and be renamed into place.

        Asserting only on the aftermath is not enough: cloning straight into
        repo_path with rollback on failure leaves the same end state, but a
        process killed mid-clone (no rollback runs) still poisons the path.
        The invariant that actually matters is that repo_path does not exist
        *while* the clone is in flight.
        """
        repo_url = "https://github.com/example/test-repo.git"
        repo_path = os.path.join(self.repos_path, "example@test-repo")
        observed_during_clone = {}

        clone_calls = []
        base_fake = self._fake_git(clone_calls)

        def fake(cmd, *args, **kwargs):
            if (isinstance(cmd, (list, tuple)) and cmd
                    and cmd[0] == 'git' and 'clone' in cmd):
                observed_during_clone['destination'] = cmd[-1]
                observed_during_clone['repo_path_exists'] = os.path.lexists(
                    repo_path)
            result = base_fake(cmd, *args, **kwargs)
            if isinstance(cmd, (list, tuple)) and cmd and 'clone' in cmd:
                open(os.path.join(cmd[-1], '.git', 'HEAD_OK'), 'w').close()
            return result

        ra = self._make_repo_action()
        with patch('mlc.repo_action.subprocess.run', side_effect=fake):
            result = ra.pull_repo(repo_url)

        self.assertEqual(result.get('return'), 0, msg=str(result))
        self.assertNotEqual(
            observed_during_clone.get('destination'), repo_path,
            msg="clone wrote directly into repo_path instead of a temp path")
        self.assertFalse(
            observed_during_clone.get('repo_path_exists', True),
            msg="repo_path existed while the clone was still running; an "
                "abrupt kill would leave a half-repo behind")
        self.assertTrue(os.path.isdir(repo_path),
                        msg="clone was never renamed into place")

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


class GitRepoStateTest(unittest.TestCase):
    """_git_repo_state must never answer "junk" when it simply cannot tell --
    callers delete on that answer."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def _git(self, *args, cwd=None):
        return subprocess.run(['git'] + list(args), cwd=cwd,
                              capture_output=True, text=True, check=True)

    def test_real_git_classification(self):
        """Exercised against real git rather than a fake, since the whole
        point is matching git's actual behaviour."""
        from mlc.repo_action import RepoAction

        base = self.temp_dir.name

        valid = os.path.join(base, 'valid')
        os.makedirs(valid)
        self._git('init', '-q', cwd=valid)
        self._git('commit', '-q', '--allow-empty', '-m', 'x', cwd=valid)

        # A freshly cloned *empty* repo has an unborn HEAD but is perfectly
        # usable -- `rev-parse HEAD` would wrongly reject it.
        empty = os.path.join(base, 'empty')
        os.makedirs(empty)
        self._git('init', '-q', cwd=empty)

        half = os.path.join(base, 'half', '.git')
        os.makedirs(half)

        plain = os.path.join(base, 'plain')
        os.makedirs(plain)

        # git -C searches upwards, so this answers for `valid` unless the
        # reported top level is compared against the path asked about.
        nested = os.path.join(valid, 'nested')
        os.makedirs(nested)

        dangling = os.path.join(base, 'dangling')
        os.symlink(os.path.join(base, 'nowhere'), dangling)

        a_file = os.path.join(base, 'a-file')
        with open(a_file, 'w') as f:
            f.write('x')

        cases = [
            (valid, RepoAction.GIT_STATE_VALID),
            (empty, RepoAction.GIT_STATE_VALID),
            (os.path.dirname(half), RepoAction.GIT_STATE_INVALID),
            (plain, RepoAction.GIT_STATE_INVALID),
            (nested, RepoAction.GIT_STATE_INVALID),
            (dangling, RepoAction.GIT_STATE_INVALID),
            (a_file, RepoAction.GIT_STATE_INVALID),
        ]
        for path, expected in cases:
            with self.subTest(path=os.path.basename(path)):
                self.assertEqual(RepoAction._git_repo_state(path), expected)

    def test_unrunnable_git_is_unknown_not_invalid(self):
        """If git cannot be executed we must not conclude "this is junk"."""
        from mlc.repo_action import RepoAction

        path = os.path.join(self.temp_dir.name, 'repo')
        os.makedirs(path)
        with patch('mlc.repo_action.subprocess.run',
                   side_effect=OSError(2, 'No such file or directory: git')):
            self.assertEqual(RepoAction._git_repo_state(path),
                             RepoAction.GIT_STATE_UNKNOWN)

    def test_refused_git_is_unknown_not_invalid(self):
        """git refusing (e.g. dubious ownership on a shared MLC_REPOS) exits
        non-zero but is not a statement that the path is not a repo."""
        from mlc.repo_action import RepoAction

        path = os.path.join(self.temp_dir.name, 'repo')
        os.makedirs(path)
        refusal = subprocess.CompletedProcess(
            [], 128, "",
            "fatal: detected dubious ownership in repository at '/x'\n")
        with patch('mlc.repo_action.subprocess.run', return_value=refusal):
            self.assertEqual(RepoAction._git_repo_state(path),
                             RepoAction.GIT_STATE_UNKNOWN)


class PullRepoDestructiveGuardTest(_RepoActionTestBase):
    """pull_repo must not delete a checkout it could not classify."""

    def test_unknown_state_preserves_the_checkout(self):
        repo_path = os.path.join(self.repos_path, "example@test-repo")
        os.makedirs(repo_path)
        precious = os.path.join(repo_path, "UNCOMMITTED_WORK.txt")
        with open(precious, 'w') as f:
            f.write("do not lose me")

        ra = self._make_repo_action()
        with patch('mlc.repo_action.subprocess.run',
                   side_effect=OSError(2, "No such file or directory: 'git'")):
            result = ra.pull_repo("https://github.com/example/test-repo.git")

        self.assertNotEqual(result.get('return'), 0,
                            msg="an unclassifiable checkout must be an error")
        self.assertTrue(
            os.path.exists(precious),
            msg="pull_repo deleted a checkout it could not classify")


class PullRepoTimeoutSemanticsTest(_RepoActionTestBase):
    """Timing out must not be reported as success when work was skipped."""

    def _hold_lock_and_pull(self, registered=False, **pull_kwargs):
        repo_path = os.path.join(self.repos_path, "example@test-repo")
        # A valid-looking checkout is already in place.
        os.makedirs(os.path.join(repo_path, '.git'), exist_ok=True)

        if registered:
            # Register it so the "nothing left to do" shortcut is gated only
            # by whether a specific revision was requested.
            with open(self.repos_file) as f:
                entries = json.load(f)
            with open(self.repos_file, 'w') as f:
                json.dump(entries + [repo_path], f, indent=2)

        def fake_run(cmd, *a, **kw):
            if (isinstance(cmd, (list, tuple)) and cmd
                    and cmd[0] == 'git' and 'rev-parse' in cmd):
                target = cmd[cmd.index('-C') + 1]
                return subprocess.CompletedProcess(cmd, 0, target + "\n", "")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        os.environ["MLC_REPO_LOCK_TIMEOUT"] = "1"
        self.addCleanup(os.environ.pop, "MLC_REPO_LOCK_TIMEOUT", None)

        ra = self._make_repo_action()
        holder = FileLock(repo_path + ".lock", timeout=30)
        holder.acquire()
        try:
            with patch('mlc.repo_action.subprocess.run', side_effect=fake_run):
                return ra.pull_repo(
                    "https://github.com/example/test-repo.git", **pull_kwargs)
        finally:
            holder.release()

    def test_timeout_with_requested_tag_is_an_error(self):
        """The repo is present AND registered, so only the revision request
        stands between this and a false success. _is_valid_git_repo says "a
        checkout exists", not "it is at the tag you asked for" -- reporting
        success here would silently run the wrong revision."""
        result = self._hold_lock_and_pull(registered=True, tag="v2")
        self.assertNotEqual(
            result.get('return'), 0,
            msg="timing out while a specific tag was requested must not "
                "report success")

    def test_timeout_with_requested_branch_is_an_error(self):
        result = self._hold_lock_and_pull(
            registered=True, branch="some-branch")
        self.assertNotEqual(result.get('return'), 0)

    def test_timeout_with_requested_checkout_is_an_error(self):
        result = self._hold_lock_and_pull(registered=True, checkout="abc1234")
        self.assertNotEqual(result.get('return'), 0)

    def test_timeout_on_unregistered_repo_is_an_error(self):
        """Even with no revision requested, the repo still has to be
        registered in repos.json for there to be nothing left to do."""
        result = self._hold_lock_and_pull(registered=False)
        self.assertNotEqual(
            result.get('return'), 0,
            msg="repo was never registered, so this was not a no-op")

    def test_timeout_on_registered_repo_with_no_revision_is_a_noop(self):
        """The one case where reporting success is legitimate."""
        result = self._hold_lock_and_pull(registered=True)
        self.assertEqual(
            result.get('return'), 0,
            msg="another process left a valid registered checkout and no "
                "revision was requested; there was genuinely nothing to do")


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
