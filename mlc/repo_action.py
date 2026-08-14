from .action import Action
import contextlib
import os
import subprocess
import tempfile
import threading
import re
import shlex
import yaml
import json
import shutil
from . import utils
from .logger import logger
from urllib.parse import urlparse
from .repo import Repo
from .index import Index
from filelock import FileLock, Timeout

# How long to wait for another process's per-repo lock before giving up.
# A cold clone of a large repo on a throttled link can run well past five
# minutes, so the default is generous and can be raised further.
REPO_LOCK_TIMEOUT_ENV = "MLC_REPO_LOCK_TIMEOUT"
DEFAULT_REPO_LOCK_TIMEOUT = 1800


# Per-repo lock paths currently held by this thread. register_repo() can
# recurse back into pull_repo() for a dependency while the parent's lock is
# still held, so without this a repo that (transitively) depends on itself
# would block against its own lock for the full timeout.
#
# This does NOT rescue two *threads* pulling repos with crossed dependencies
# (A deps B, B deps A): that is a genuine lock-order inversion between two
# per-repo locks and still resolves only by timing out. It surfaces as a
# Timeout error rather than silently, which is why the Timeout handler in
# pull_repo must not report success indiscriminately.
_held_repo_locks = threading.local()


def _repo_locks_held_by_this_thread():
    held = getattr(_held_repo_locks, "paths", None)
    if held is None:
        held = set()
        _held_repo_locks.paths = held
    return held


class RepoLockPermissionError(Exception):
    """Raised only when the per-repo lock file itself cannot be created."""


@contextlib.contextmanager
def _repo_lock(repo_lock_file, timeout):
    """Acquire a per-repo lock, tolerating same-thread re-entry."""
    held = _repo_locks_held_by_this_thread()
    if repo_lock_file in held:
        # Already ours further up the call stack (dependency recursion).
        yield
        return
    try:
        lock = FileLock(repo_lock_file, timeout=timeout)
        lock.acquire()
    except PermissionError as e:
        # Narrow: only failures creating the lock file. Catching
        # PermissionError around the whole pull would mislabel an EACCES
        # from git, rmtree or reading meta.yaml as a lock problem.
        raise RepoLockPermissionError(str(e)) from e
    held.add(repo_lock_file)
    try:
        yield
    finally:
        held.discard(repo_lock_file)
        lock.release()


def _atomic_write_json(file_path, data):
    """Write JSON so a concurrent reader never observes a partial file.

    open(path, 'w') truncates and json.dump rewrites incrementally, so a
    reader landing in that window sees a truncated file and raises
    JSONDecodeError. Action.load_repos_and_meta() and Action.load_repos()
    both read repos.json with a bare json.load and no lock, so the writer's
    lock alone does not protect them. Writing to a sibling temp file and
    os.replace()-ing it -- atomic on POSIX and Windows -- makes those
    lock-free readers safe without having to change them.

    If this process dies mid-write, os.replace never runs: the original file
    is left intact and only the temp file is orphaned.
    """
    directory = os.path.dirname(file_path) or '.'
    # A unique temp name rather than a fixed "<file>.tmp": callers happen to
    # hold a lock today, but a helper named "atomic write" should not depend
    # on that to avoid two writers trampling the same scratch file.
    fd, tmp_path = tempfile.mkstemp(
        dir=directory, prefix=os.path.basename(file_path) + '.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(data, f, indent=2)
        # os.replace installs a new inode, so mode/ownership would otherwise
        # be whatever mkstemp chose (0600) rather than the file's own -- on a
        # shared MLC_REPOS that would silently drop group access.
        try:
            shutil.copymode(file_path, tmp_path)
        except OSError:
            pass
        os.replace(tmp_path, file_path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def _get_repo_lock_timeout():
    """Seconds to wait for a per-repo lock, overridable via the environment."""
    raw = os.environ.get(REPO_LOCK_TIMEOUT_ENV, "")
    if not raw:
        return DEFAULT_REPO_LOCK_TIMEOUT
    try:
        timeout = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            f"Ignoring invalid {REPO_LOCK_TIMEOUT_ENV}={raw!r}; "
            f"using {DEFAULT_REPO_LOCK_TIMEOUT}s.")
        return DEFAULT_REPO_LOCK_TIMEOUT
    if timeout <= 0:
        logger.warning(
            f"Ignoring non-positive {REPO_LOCK_TIMEOUT_ENV}={raw!r}; "
            f"using {DEFAULT_REPO_LOCK_TIMEOUT}s.")
        return DEFAULT_REPO_LOCK_TIMEOUT
    return timeout


class RepoAction(Action):
    """
    ####################################################################################################################
    Repo Action
    ####################################################################################################################

    Currently, the following actions are supported for Repos:
    1. add
    2. find
    3. pull
    4. list
    5. remove(rm)

    Repositories in MLCFlow can be identified using any of the following methods:

    Using MLC repo folder name format: <repoowner@reponame> (e.g.,mlcommons@mlperf-automations)
    Using alias: <repo_alias> (e.g., mlcommons@mlperf-automations)
    Using UID: <repo_uid> (e.g., 9cf241afa6074c89)
    Using both alias and UID: <repo_alias>,<repo_uid> (e.g., mlcommons@mlperf-automations,9cf241afa6074c89)
    Using URL: <repo_url> (e.g., https://github.com/mlcommons/mlperf-automations)

    Note:

    - repo uid and repo alias for a particular MLC repository can be found inside the meta.yml file.

    """

    # These phrases come from git's current stderr output and may vary by
    # version or locale, so keep the matching logic narrowly scoped.
    GIT_MISSING_BRANCH_PHRASE = "did not match any file(s) known to git"
    GIT_FAST_FORWARD_FAILURE_PHRASE = "not possible to fast-forward"

    def __init__(self, parent=None):
        # super().__init__(parent)
        self.parent = parent
        self.__dict__.update(vars(parent))

    def _build_pull_command(self, repo_path, branch=None, clone_depth=None,
                            fast_forward_only=False):
        pull_command = ['git', '-C', repo_path, 'pull']
        if fast_forward_only:
            pull_command.append('--ff-only')
        if clone_depth is not None:
            if self._is_shallow_repo(repo_path):
                pull_command.extend(['--depth', str(clone_depth)])
            else:
                logger.warning(
                    f"--depth/--shallow ignored for pull on non-shallow repo {repo_path}. "
                    "Re-clone with --shallow to create a shallow copy."
                )
        # Preserve the historical existing-repo behavior of a plain
        # `git pull` by default. The branch argument is only forwarded to
        # `git pull` when the internal strict path explicitly opts into
        # fast-forward-only updates.
        if branch and fast_forward_only:
            pull_command.extend(['origin', branch])
        return pull_command

    def _checkout_pull_branch(self, repo_path, branch):
        """Ensure *branch* is checked out locally before a strict pull.

        First tries to checkout an existing local branch. If that fails, fetches
        the branch from origin and creates a new tracking branch. Raises
        RuntimeError with contextual guidance when the branch cannot be prepared.

        Args:
            repo_path: Local repository path.
            branch: Branch name to prepare before pulling.

        Raises:
            RuntimeError: If the branch cannot be fetched or checked out.
        """
        try:
            subprocess.run(
                ['git', '-C', repo_path, 'checkout', branch],
                capture_output=True,
                text=True,
                check=True)
        except subprocess.CalledProcessError as checkout_error:
            checkout_error_text = self._subprocess_error_message(
                checkout_error)
            lowered_checkout_error = checkout_error_text.lower()
            # Git uses the same exit code for many checkout failures, so we
            # only fall back to fetch+track when stderr includes both
            # "pathspec" and Git's usual missing-ref phrase
            # "did not match any file(s) known to git".
            missing_local_branch = (
                "pathspec" in lowered_checkout_error
                and self.GIT_MISSING_BRANCH_PHRASE in lowered_checkout_error
            )
            if not missing_local_branch:
                raise RuntimeError(
                    f"Cannot switch to branch '{branch}' in {repo_path}: "
                    f"{checkout_error_text}"
                ) from checkout_error
            try:
                subprocess.run(
                    ['git', '-C', repo_path, 'fetch', 'origin', branch],
                    capture_output=True,
                    text=True,
                    check=True)
            except subprocess.CalledProcessError as fetch_error:
                raise RuntimeError(
                    f"Failed to fetch branch '{branch}' in {repo_path}: "
                    f"{self._subprocess_error_message(fetch_error)}. "
                    "Ensure the branch exists on origin and that the repository is reachable."
                ) from fetch_error

            try:
                subprocess.run(
                    ['git', '-C', repo_path, 'checkout', '-b',
                        branch, '--track', f'origin/{branch}'],
                    capture_output=True,
                    text=True,
                    check=True)
            except subprocess.CalledProcessError as tracking_error:
                raise RuntimeError(
                    f"Initial checkout of '{branch}' failed in {repo_path}. "
                    "After fetching from origin, creating a tracking branch also failed. "
                    f"Initial error: {checkout_error_text}. "
                    f"Tracking branch error: "
                    f"{self._subprocess_error_message(tracking_error)}. "
                    "Check that the branch name is correct and that your local checkout can track origin."
                ) from tracking_error

    @staticmethod
    def _format_stash_restore_guidance(repo_path):
        return (
            f"Local changes remain in stash. Please run `git -C {repo_path} stash apply` "
            "after resolving pull issues."
        )

    def _format_pull_error(self, repo_path, error_message, stash_created=False,
                           force=False, failure_phase="git pull"):
        """Format a pull failure message.

        Args:
            repo_path: Repository path being updated.
            error_message: Original stderr/stdout-derived git failure text.
            stash_created: Whether local changes were stashed for a force pull.
            force: Whether the failure happened on a force-pull path.
            failure_phase: Phase label such as ``git pull`` or
                ``branch checkout``.

        Returns:
            A user-facing error string with optional recovery guidance.
        """
        prefix = "Force pull failed" if force else "Pull failed"
        if failure_phase:
            prefix = f"{prefix} during {failure_phase}"

        resolution = ""
        lowered_error = error_message.lower()
        # Git reports ff-only failures via stderr text instead of a distinct
        # exit code, so use this case-insensitive substring from the standard
        # "Not possible to fast-forward, aborting." message to add guidance.
        if self.GIT_FAST_FORWARD_FAILURE_PHRASE in lowered_error:
            resolution = (
                " Check whether the local and remote branches have diverged "
                "and reconcile them manually before retrying."
            )

        if stash_created:
            return (
                f"{prefix} for {repo_path}. "
                f"{self._format_stash_restore_guidance(repo_path)} "
                f"Details: {error_message}{resolution}"
            )

        return f"{prefix} for {repo_path}: {error_message}{resolution}"

    @staticmethod
    def _subprocess_error_message(error):
        """Return stderr, then stdout, then str(error), whichever is populated first."""
        return (error.stderr or error.stdout or str(error)).strip()

    @staticmethod
    def _validate_extra_git_args(extra_args):
        disallowed_pattern = re.compile(r"[\r\n]")
        for arg in extra_args:
            if disallowed_pattern.search(arg):
                return (
                    "--extra_git_args may not include carriage returns or newlines."
                )
        return None

    # Return values of _git_repo_state().
    GIT_STATE_VALID = "valid"        # a git checkout rooted exactly here
    GIT_STATE_INVALID = "invalid"    # definitely not a checkout; safe to remove
    GIT_STATE_UNKNOWN = "unknown"    # git could not answer; DO NOT remove

    # git's phrasing when a path is genuinely not a repository. Anything else
    # on a non-zero exit (dubious ownership, EACCES, ...) is "unknown".
    GIT_NOT_A_REPO_PHRASE = "not a git repository"

    @classmethod
    def _git_repo_state(cls, repo_path):
        """Classify repo_path as a git checkout, without ever guessing.

        `git status` cannot be used: on the directory left by an interrupted
        clone it exits 0 with empty stdout ("clean"), and on a non-git
        directory it exits 128 with empty stdout -- indistinguishable.

        `rev-parse --show-toplevel` is used rather than `rev-parse HEAD` for
        two reasons:
          * a freshly cloned *empty* repo has an unborn HEAD, so `rev-parse
            HEAD` fails on a perfectly good checkout;
          * `git -C` searches upwards, so a plain directory nested inside
            another checkout answers for the *enclosing* repo. Comparing the
            reported top level against repo_path rejects that.

        The INVALID/UNKNOWN split matters because callers delete on INVALID.
        A git that cannot be executed, or that refuses (e.g. "detected
        dubious ownership" on a shared MLC_REPOS), must never be read as
        "this is junk, remove it".
        """
        if os.path.islink(repo_path) or not os.path.isdir(repo_path):
            # A symlink, a plain file, or nothing at all: not a checkout, and
            # not something to hand to git.
            return (cls.GIT_STATE_INVALID if os.path.lexists(repo_path)
                    else cls.GIT_STATE_INVALID)
        try:
            result = subprocess.run(
                ['git', '-C', repo_path, 'rev-parse', '--show-toplevel'],
                capture_output=True, text=True)
        except (OSError, subprocess.SubprocessError) as e:
            logger.warning(
                f"Could not run git to inspect {repo_path}: {e}. "
                "Leaving the directory untouched.")
            return cls.GIT_STATE_UNKNOWN

        if result.returncode == 0:
            toplevel = (result.stdout or "").strip()
            if not toplevel:
                return cls.GIT_STATE_UNKNOWN
            try:
                same = os.path.samefile(toplevel, repo_path)
            except OSError:
                same = (os.path.realpath(toplevel)
                        == os.path.realpath(repo_path))
            # A non-repo directory sitting inside another checkout reports the
            # enclosing repo here; that is not a checkout *at* repo_path.
            return cls.GIT_STATE_VALID if same else cls.GIT_STATE_INVALID

        stderr = (result.stderr or "").lower()
        if cls.GIT_NOT_A_REPO_PHRASE in stderr:
            return cls.GIT_STATE_INVALID
        logger.warning(
            f"git could not classify {repo_path} "
            f"(exit {result.returncode}): {(result.stderr or '').strip()}. "
            "Leaving the directory untouched.")
        return cls.GIT_STATE_UNKNOWN

    @classmethod
    def _is_valid_git_repo(cls, repo_path):
        """True only when repo_path is a git checkout rooted exactly there."""
        return cls._git_repo_state(repo_path) == cls.GIT_STATE_VALID

    @staticmethod
    def _remove_broken_checkout(path):
        """Remove a path that is known not to be a usable checkout.

        Handles the non-directory cases too: a stale symlink or a plain file
        sitting where the repo should be would make rmtree raise
        NotADirectoryError.
        """
        try:
            if os.path.islink(path) or os.path.isfile(path):
                os.remove(path)
            else:
                shutil.rmtree(path)
        except OSError as e:
            logger.warning(f"Failed to remove {path}: {e}")

    def add(self, run_args):
        """
    ####################################################################################################################
    Target: Repo
    Action: Add
    ####################################################################################################################

    The `add` action is used to create a new MLC repository and register it in MLCFlow.
    The newly created repo folder will be stored inside the `repos` folder within the parent MLC directory.

    Example Command:

    mlc add repo mlcommons@script-automations

    Example Output:

      anandhu@anandhu-VivoBook-ASUSLaptop-X515UA-M515UA:~$ mlc add repo mlcommons@script-automations
      [2025-02-19 16:34:37,570 main.py:1085 INFO] - New repo path: /home/anandhu/MLC/repos/mlcommons@script-automations
      [2025-02-19 16:34:37,573 main.py:1126 INFO] - Added new repo path: /home/anandhu/MLC/repos/mlcommons@script-automations
      [2025-02-19 16:34:37,573 main.py:1130 INFO] - Updated repos.json at /home/anandhu/MLC/repos/repos.json

    Note:
      - repo_uid is not supported in the add action for repo target, as the UID is assigned automatically when the repository
        is created.

        """
        if not run_args['repo']:
            logger.error("The repository to be added is not specified")
            return {"return": 1,
                    "error": "The repository to be added is not specified"}

        i_repo_path = run_args['repo']  # can be a path, forder_name or URL
        repo_folder_name = os.path.basename(i_repo_path.rstrip('/'))

        repo_path = os.path.join(self.repos_path, repo_folder_name)

        r = self.find(run_args)

        if r['return'] == 0 and len(r['list']) > 0:
            return {'return': 1,
                    "error": f"""Repo already exists at {r['list'][0]}"""}

        for repo in self.repos:
            if repo.path == i_repo_path:
                return {'return': 1,
                        "error": f"""Repo already exists at {repo.path}"""}

        if not os.path.exists(i_repo_path):
            # check if its an URL
            if utils.is_valid_url(i_repo_path):
                parsed = urlparse(i_repo_path)
                if parsed.hostname == "github.com":
                    res = self.github_url_to_user_repo_format(i_repo_path)
                    if res['return'] > 0:
                        return res
                    repo_folder_name = res['value']
                    repo_path = os.path.join(self.repos_path, repo_folder_name)

            os.makedirs(repo_path)
        else:
            repo_path = os.path.abspath(i_repo_path)

        # check if it has MLC meta
        meta_file = os.path.join(repo_path, "meta.yaml")
        if not os.path.exists(meta_file):
            meta = {}
            meta['uid'] = utils.get_new_uid()['uid']
            meta['alias'] = repo_folder_name
            meta['git'] = True
            utils.save_yaml(meta_file, meta)
        else:
            meta = utils.read_yaml(meta_file)

        self.register_repo(repo_path, meta, run_args.get('ignore_on_conflict'))

        return {'return': 0}

    def conflicting_repo(self, repo_meta):
        for repo_object in self.repos:
            if repo_object.meta.get('uid', '') == '':
                return {
                    "return": 1, "error": f"UID is not present in file 'meta.yaml' in the repo path {repo_object.path}"}
            if repo_meta["uid"] == repo_object.meta.get('uid', ''):
                if repo_meta.get('path', '') == repo_object.path:
                    return {"return": 1,
                            "error": f"Same repo is already registered"}
                else:
                    return {"return": 1, "error": f"Conflicting with repo in the path {repo_object.path}",
                            "conflicting_path": repo_object.path}
        return {"return": 0}

    def register_repo(self, repo_path, repo_meta, ignore_on_conflict=False):

        # Check UID conflicts
        is_conflict = self.conflicting_repo(repo_meta)
        if is_conflict['return'] > 0:
            if "UID not present" in is_conflict['error']:
                logger.warning(
                    f"UID not found in meta.yaml at {repo_path}. Repo can not be registered in MLC repos. Skipping...")
                return {"return": 0}
            elif "already registered" in is_conflict["error"]:  # at same path
                # logger.warning(is_conflict["error"])
                logger.debug("No changes made to repos.json.")
                return {"return": 0}
            else:
                logger.warning(
                    f"The repo to be registered has conflict with the repo already in the path: {is_conflict['conflicting_path']}")
                if ignore_on_conflict:
                    logger.warning(
                        f"Ignoring register as ignore_on_conflict is set")
                    return {"return": 0, 'conflict': True}

                self.unregister_repo(is_conflict['conflicting_path'])
                logger.warning(
                    f"{is_conflict['conflicting_path']} is unregistered.")

        if repo_meta.get('deps'):
            for dep in repo_meta['deps']:
                self.pull_repo(
                    dep['url'],
                    branch=dep.get('branch'),
                    checkout=dep.get('checkout'),
                    ignore_on_conflict=dep.get(
                        'is_alias_okay',
                        True))

        # Get the path to the repos.json file in $HOME/MLC
        repos_file_path = os.path.join(self.repos_path, 'repos.json')

        try:
            # LOCK ORDERING: repos.json.lock is the *inner* lock -- pull_repo
            # already holds <repo_path>.lock when it calls this. Never acquire
            # a per-repo lock while holding this one, or the two orders will
            # deadlock until their timeouts expire.
            with FileLock(_repos_lock_file(repos_file_path), timeout=60):
                with open(repos_file_path, 'r') as f:
                    repos_list = json.load(f)

                if repo_path not in repos_list:
                    repos_list.append(repo_path)
                    logger.info(f"Added new repo path: {repo_path}")

                _atomic_write_json(repos_file_path, repos_list)
                logger.info(f"Updated repos.json at {repos_file_path}")
        except Timeout:
            return {
                'return': 1,
                'error': (
                    "Could not acquire lock for repos.json after 60 seconds. "
                    "Another mlc process may be modifying repos.json. "
                    "Try again once the other operation completes."
                )
            }

        # Deliberately outside the lock. load_repos_and_meta() calls rm_repo()
        # for entries whose path has vanished (mlc/action.py), and rm_repo ->
        # unregister_repo takes this same repos.json lock on a fresh FileLock
        # instance. filelock is only reentrant per instance, so re-entering it
        # here would block the process against itself for the full 60s timeout
        # on every pull whose repos.json holds one stale entry.
        #
        # The window this leaves is that a concurrent writer may have replaced
        # repos.json before the reload, so the lookup below can miss the repo
        # just registered. Falling back to the meta already in hand closes
        # that without widening the lock.
        self.repos = self.load_repos_and_meta()
        repo_obj = next(
            (r for r in self.repos if r.path == repo_path),
            None
        )
        if repo_obj is None:
            repo_obj = Repo(path=repo_path, meta=repo_meta)

        if repo_obj:
            index = Action.get_index(self)
            index.add_repo(repo_obj)
            logger.debug("Index file has been updated")

        return {'return': 0}

    def unregister_repo(self, repo_path):
        repos_file_path = os.path.join(self.repos_path, 'repos.json')

        return unregister_repo(repo_path, repos_file_path)

    def find(self, run_args):
        """
    ####################################################################################################################
    Target: Repo
    Action: Find
    ####################################################################################################################

    find action retrieves the path of a specific repository registered in MLCFlow.

    Example Command:

    mlc find repo mlcommons@script-automations

    Example Output:

      anandhu@anandhu-VivoBook-ASUSLaptop-X515UA-M515UA:~$ mlc find repo mlcommons@mlperf-automations
      [2025-02-19 15:32:18,352 main.py:1737 INFO] - Item path: /home/anandhu/MLC/repos/mlcommons@mlperf-automations

        """
        # Get repos_list using the existing method
        repos_list = self.load_repos_and_meta()
        if (run_args.get('item', run_args.get('artifact'))):
            repo = run_args.get('item', run_args.get('artifact'))
        else:
            repo = run_args.get(
                'repo', run_args.get(
                    'item', run_args.get('artifact')))

        # Check if repo is None or empty
        if not repo:
            return {"return": 1, "error": "Please enter a Repo Alias, Repo UID, or Repo URL in one of the following formats:\n"
                    "- <repo_owner>@<repos_name>\n"
                    "- <repo_url>\n"
                    "- <repo_uid>\n"
                    "- <repo_alias>\n"
                    "- <repo_alias>,<repo_uid>"}

        # Handle the different repo input formats
        repo_name = None
        repo_uid = None

        # Check if the repo is in the format of a repo UID (alphanumeric
        # string)
        if utils.is_uid(repo):
            repo_uid = repo
        if "," in repo:
            repo_split = repo.split(",")
            repo_name = repo_split[0]
            if len(repo_split) > 1:
                repo_uid = repo_split[1]
        elif "@" in repo:
            repo_name = repo
        else:
            # Check for valid github.com URL using urlparse
            try:
                parsed = urlparse(repo)
            except Exception:
                parsed = None
            if parsed and parsed.scheme in (
                    "http", "https") and parsed.hostname == "github.com":
                result = self.github_url_to_user_repo_format(repo)
                if result["return"] == 0:
                    repo_name = result["value"]
                else:
                    return result
            else:
                repo_name = repo

        # Check if repo_name exists in repos.json
        matched_repo_path = None
        for repo_obj in repos_list:
            if repo_name and repo_name == os.path.basename(repo_obj.path):
                matched_repo_path = repo_obj
                break

        # Search through self.repos for matching repos
        lst = []
        for i in self.repos:
            if repo_uid and i.meta['uid'] == repo_uid:
                lst.append(i)
            elif repo_name == i.meta['alias']:
                lst.append(i)

        # After loop, check if any match was found
        if not lst and not matched_repo_path:
            # Determine error message based on input
            if utils.is_uid(repo):
                return {
                    "return": 1, "error": f"No repository with UID: '{repo_uid}' was found"}
            elif "," in repo and not matched_repo_path:
                return {
                    "return": 1, "error": f"No repository with alias: '{repo_name}' and UID: '{repo_uid}' was found"}
            else:
                return {
                    "return": 1, "error": f"No repository with alias: '{repo_name}' was found"}

        # Append the matched repo path
        if (len(lst) == 0 and matched_repo_path):
            lst.append(matched_repo_path)

        return {'return': 0, 'list': lst}

    def github_url_to_user_repo_format(self, url):
        # """
        # Converts a GitHub repo URL to user@repo_name format.

        # :param url: str, GitHub repository URL (e.g., https://github.com/user/repo_name.git)
        # :return: str, formatted as user@repo_name
        # """
        # Regex to match GitHub URLs
        pattern = r"(?:https?://)?(?:www\.)?github\.com/([^/]+)/([^/.]+)(?:\.git)?"

        match = re.match(pattern, url)
        if match:
            user, repo_name = match.groups()
            return {"return": 0, "value": f"{user}@{repo_name}"}
        else:
            return {"return": 0, "value": os.path.basename(
                url).replace(".git", "")}

    def _is_shallow_repo(self, repo_path):
        """Return True if the git repository at *repo_path* is a shallow clone."""
        try:
            result = subprocess.run(
                ['git', '-C', repo_path, 'rev-parse', '--is-shallow-repository'],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0 and result.stdout.strip() == 'true'
        except (subprocess.SubprocessError, FileNotFoundError, OSError):
            return False

    def pull_repo(self, repo_url, branch=None, checkout=None, tag=None,
                  pat=None, ssh=None, ignore_on_conflict=False, repo_path=None, force=False,
                  shallow=False, depth=None, extra_git_args=None, fast_forward_only=False):

        repo_lock_timeout = _get_repo_lock_timeout()

        # Determine the checkout path from environment or default
        repo_base_path = self.repos_path  # either the value will be from 'MLC_REPOS'
        # Ensure the directory exists
        os.makedirs(repo_base_path, exist_ok=True)

        # Handle user@repo format (convert to standard GitHub URL)
        if re.match(r'^[\w-]+@[\w-]+$', repo_url):
            user, repo = repo_url.split('@')
            repo_url = f"https://github.com/{user}/{repo}.git"

        # support pat and ssh
        if pat or ssh:
            tmp_param = {}
            url_type = "pat" if pat else "ssh"
            if pat:
                tmp_param["token"] = pat
            res = utils.modify_git_url(url_type, repo_url, tmp_param)
            if res["return"] > 0:
                return res
            else:
                repo_url = res["url"]

        # Extract the repo name from URL
        repo_name = repo_url.split('/')[-1].replace('.git', '')
        res = self.github_url_to_user_repo_format(repo_url)
        if res["return"] > 0:
            return res
        else:
            repo_download_name = res["value"]
            if not repo_path:
                repo_path = os.path.join(repo_base_path, repo_download_name)

        try:
            # Compute depth argument: --shallow implies depth=1; explicit
            # --depth=N takes precedence
            clone_depth = None
            if depth is not None:
                try:
                    clone_depth = int(depth)
                except (TypeError, ValueError):
                    return {
                        "return": 1, "error": f"Invalid value for --depth: {depth}. Must be a positive integer."}
                if clone_depth < 1:
                    return {
                        "return": 1, "error": f"Invalid value for --depth: {clone_depth}. Must be a positive integer."}
            elif shallow:
                clone_depth = 1

            # Parse extra_git_args into a list
            extra_args = []
            if extra_git_args:
                if isinstance(extra_git_args, list):
                    if not all(isinstance(arg, str) for arg in extra_git_args):
                        return {
                            "return": 1,
                            "error": "--extra_git_args list entries must all be strings."
                        }
                    extra_args = extra_git_args
                elif isinstance(extra_git_args, str):
                    extra_args = shlex.split(extra_git_args)
                else:
                    return {
                        "return": 1,
                        "error": "--extra_git_args must be provided as a string or list of strings."
                    }
                extra_git_args_error = self._validate_extra_git_args(
                    extra_args)
                if extra_git_args_error:
                    return {"return": 1, "error": extra_git_args_error}

            # Lock file sits next to the repo directory; left on disk but
            # harmless.
            #
            # LOCK ORDERING: the per-repo lock is always acquired *before*
            # repos.json.lock -- register_repo() is called from inside this
            # block and takes that second lock. Any new code path that needs
            # both must acquire them in this same order, or the two will
            # deadlock until their timeouts expire.
            repo_lock_file = repo_path + ".lock"
            with _repo_lock(repo_lock_file, repo_lock_timeout):
                # A directory left behind by an interrupted clone is not a
                # usable repo: it has a .git with an origin but no HEAD, and
                # every later pull fails against it. Such a directory is
                # removed and cloned afresh.
                #
                # Only GIT_STATE_INVALID is removed. If git could not be run
                # or refused to answer we do NOT delete: that path would
                # destroy a healthy checkout -- including uncommitted work --
                # over a missing git binary or a "dubious ownership" refusal
                # on a shared MLC_REPOS.
                if os.path.lexists(repo_path):
                    repo_state = self._git_repo_state(repo_path)
                    if repo_state == self.GIT_STATE_UNKNOWN:
                        return {
                            'return': 1,
                            'error': (
                                f"Could not determine whether {repo_path} is a "
                                "valid git checkout; refusing to touch it. See "
                                "the warning above for what git reported."
                            )
                        }
                    if repo_state == self.GIT_STATE_INVALID:
                        logger.warning(
                            f"{repo_path} exists but is not a usable git "
                            "checkout (likely a previously interrupted "
                            "clone). Removing it and cloning again.")
                        self._remove_broken_checkout(repo_path)
                        # ignore_errors would hide a failed removal and drop us
                        # into the "already exists -> pull" branch below, which
                        # is exactly the broken state being cleaned up.
                        if os.path.lexists(repo_path):
                            return {
                                'return': 1,
                                'error': (
                                    f"Could not remove the unusable checkout at "
                                    f"{repo_path}. Remove it manually and retry."
                                )
                            }

                # If the directory doesn't exist, clone it
                if not os.path.lexists(repo_path):
                    logger.info(
                        f"Cloning repository {repo_url} to {repo_path}...")

                    # Clone into a sibling temp path and rename into place, so
                    # repo_path is only ever absent or complete. Without this,
                    # a clone killed part-way (SIGKILL/OOM/dropped link) leaves
                    # a half-repo that the existence check above would have to
                    # clean up on the *next* run.
                    tmp_clone_path = repo_path + ".tmp-clone"
                    shutil.rmtree(tmp_clone_path, ignore_errors=True)

                    # Build clone command
                    clone_command = ['git', 'clone']
                    if branch:
                        clone_command += ['--branch', branch]
                    if clone_depth is not None:
                        clone_command += ['--depth', str(clone_depth)]
                    clone_command += extra_args
                    clone_command += [repo_url, tmp_clone_path]

                    try:
                        subprocess.run(clone_command, check=True)
                        os.rename(tmp_clone_path, repo_path)
                    except BaseException:
                        # BaseException so KeyboardInterrupt also cleans up.
                        shutil.rmtree(tmp_clone_path, ignore_errors=True)
                        raise

                else:
                    logger.info(
                        f"Repository {repo_name} already exists at {repo_path}. Checking for local changes...")

                    # Check for local changes
                    status_command = [
                        'git',
                        '-C',
                        repo_path,
                        'status',
                        '--porcelain',
                        '--untracked-files=no']
                    local_changes = subprocess.run(
                        status_command, capture_output=True, text=True)

                    if local_changes.stdout.strip():
                        if not force:
                            logger.warning(
                                "There are local changes in the repository. Please commit or stash them before checking out.")
                            print(local_changes.stdout.strip())
                            return {
                                "return": 0, "warning": f"Local changes detected in the already existing repository: {repo_path}, skipping the pull"}

                        logger.warning(
                            "Local changes detected. Running force pull with temporary git stash.")
                        stash_created = False
                        try:
                            stash_before = subprocess.run(
                                ['git', '-C', repo_path, 'stash', 'list'],
                                capture_output=True,
                                text=True,
                                check=True
                            )
                            stash_res = subprocess.run(
                                ['git', '-C', repo_path, 'stash', 'push',
                                    '-m', 'mlc pull repo --force'],
                                capture_output=True,
                                text=True,
                                check=True
                            )
                            stash_after = subprocess.run(
                                ['git', '-C', repo_path, 'stash', 'list'],
                                capture_output=True,
                                text=True,
                                check=True
                            )
                            stash_created = len(stash_after.stdout.splitlines()
                                                ) > len(stash_before.stdout.splitlines())
                        except subprocess.CalledProcessError as e:
                            stash_error = (
                                e.stderr or e.stdout or str(e)).strip()
                            return {
                                "return": 1,
                                "error": f"Force pull failed while stashing local changes in {repo_path}: {stash_error}"
                            }

                        logger.info(
                            "Pulling latest changes...")
                        try:
                            if fast_forward_only and branch:
                                self._checkout_pull_branch(repo_path, branch)
                            subprocess.run(
                                self._build_pull_command(
                                    repo_path, branch, clone_depth, fast_forward_only),
                                capture_output=True,
                                text=True,
                                check=True)
                        except RuntimeError as e:
                            return {
                                "return": 1,
                                "error": self._format_pull_error(
                                    repo_path,
                                    str(e),
                                    stash_created=stash_created,
                                    force=True,
                                    failure_phase="branch checkout")
                            }
                        except subprocess.CalledProcessError as e:
                            pull_error = self._subprocess_error_message(e)
                            return {
                                "return": 1,
                                "error": self._format_pull_error(
                                    repo_path,
                                    pull_error,
                                    stash_created=stash_created,
                                    force=True)
                            }
                        logger.info("Repository successfully pulled.")

                        if stash_created:
                            try:
                                subprocess.run(
                                    ['git', '-C', repo_path, 'stash', 'apply'],
                                    capture_output=True,
                                    text=True,
                                    check=True)
                                subprocess.run(
                                    ['git', '-C', repo_path, 'stash', 'drop'],
                                    capture_output=True,
                                    text=True,
                                    check=True)
                                logger.info(
                                    "Local changes restored successfully after force pull.")
                            except subprocess.CalledProcessError as apply_error:
                                apply_error_msg = (
                                    apply_error.stderr or apply_error.stdout or str(apply_error)).strip()
                                try:
                                    subprocess.run(
                                        ['git', '-C', repo_path,
                                            'reset', '--hard', 'HEAD'],
                                        capture_output=True,
                                        text=True,
                                        check=True)
                                except subprocess.CalledProcessError as reset_exception:
                                    reset_error_msg = (
                                        reset_exception.stderr or reset_exception.stdout or str(reset_exception)).strip()
                                    return {
                                        "return": 1,
                                        "error": f"Stash apply conflicted and automatic rollback failed for {repo_path}: {reset_error_msg}. Original stash apply error: {apply_error_msg}"
                                    }
                                logger.warning(
                                    f"Stash apply reported conflicts after pull. Reverted partial stash apply. "
                                    f"Please resolve manually with `git -C {repo_path} stash apply`.")
                                return {
                                    "return": 0,
                                    "warning": f"Force pull succeeded for {repo_path}, but stash apply had conflicts. Partial apply was reverted. Please apply the stash manually."
                                }
                    else:
                        logger.info(
                            "No local changes detected. Pulling latest changes...")
                        try:
                            if fast_forward_only and branch:
                                self._checkout_pull_branch(repo_path, branch)
                            subprocess.run(
                                self._build_pull_command(
                                    repo_path, branch, clone_depth, fast_forward_only),
                                capture_output=True,
                                text=True,
                                check=True)
                        except RuntimeError as e:
                            return {
                                "return": 1,
                                "error": self._format_pull_error(
                                    repo_path, str(e), failure_phase="branch checkout")
                            }
                        except subprocess.CalledProcessError as e:
                            pull_error = self._subprocess_error_message(e)
                            return {
                                "return": 1,
                                "error": self._format_pull_error(
                                    repo_path, pull_error)
                            }
                        logger.info("Repository successfully pulled.")

                if tag:
                    checkout = "tags/" + tag

                # Checkout to a specific branch or commit if --checkout is
                # provided
                if checkout or tag:
                    logger.info(
                        f"Checking out to {checkout} in {repo_path}...")
                    subprocess.run(
                        ['git', '-C', repo_path, 'checkout', checkout], check=True)

                # if not tag:
                #    subprocess.run(['git', '-C', repo_path, 'pull'], check=True)
                #    logger.info("Repository successfully pulled.")

                logger.info("Registering the repo in repos.json")

                # check the meta file to obtain uids
                meta_file_path = os.path.join(repo_path, 'meta.yaml')
                if not os.path.exists(meta_file_path):
                    logger.warning(
                        f"meta.yaml not found in {repo_path}. Repo pulled but not registered in MLC repos. Skipping...")
                    return {"return": 0}

                try:
                    with open(meta_file_path, 'r') as meta_file:
                        meta_data = yaml.safe_load(meta_file)
                        meta_data["path"] = repo_path
                except yaml.YAMLError as e:
                    logger.error(f"Error loading YAML configuration: {e}")
                    return {"return": 1,
                            "error": f"Syntax error in {meta_file_path}: {e}"}

                r = self.register_repo(
                    repo_path, meta_data, ignore_on_conflict)
                if r['return'] > 0:
                    return r

                return {"return": 0}

        except RuntimeError as e:
            return {'return': 1, 'error': str(e)}
        except subprocess.CalledProcessError as e:
            return {'return': 1, 'error': f"Git command failed: {e}"}
        except Timeout:
            # A timeout can mean the holder simply finished a slow cold clone
            # for us. Reporting success on that basis is only safe when this
            # call had nothing version-specific to do -- _is_valid_git_repo
            # answers "some checkout exists here", not "it is at the revision
            # you asked for". Claiming success while the tree sits at the
            # wrong tag would silently run the wrong code, which is far worse
            # than a spurious error.
            version_specific = any((branch, checkout, tag, force))
            already_registered = repo_path in (self.load_repos() or [])
            if (not version_specific and already_registered
                    and self._is_valid_git_repo(repo_path)):
                logger.info(
                    f"Lock for {repo_path} was held by another mlc process, "
                    "which left a valid registered checkout in place and no "
                    "specific revision was requested. Nothing to do.")
                return {'return': 0}
            return {
                'return': 1,
                'error': (
                    f"Could not acquire lock for {repo_path} after "
                    f"{repo_lock_timeout} seconds. Another mlc process may "
                    "still be cloning or pulling this repo. Try again once it "
                    f"completes, or raise the timeout via "
                    f"{REPO_LOCK_TIMEOUT_ENV}."
                )
            }
        except RepoLockPermissionError as e:
            # Creating <repo_path>.lock needs write permission on the repos
            # directory itself, not just on the repo. On a shared MLC_REPOS
            # this is the usual cause, and the generic handler below would
            # only surface a bare "[Errno 13]".
            return {
                'return': 1,
                'error': (
                    f"Permission denied creating the lock file for "
                    f"{repo_path}: {e}. This requires write access to "
                    f"{self.repos_path}; check the permissions on that "
                    "directory if MLC_REPOS is shared between users."
                )
            }
        except Exception as e:
            return {'return': 1,
                    'error': f"Error pulling repository: {str(e)}"}

    def pull(self, run_args):
        """
    ####################################################################################################################
    Target: Repo
    Action: Pull
    ####################################################################################################################

    The `pull` action clones an MLC repository and registers it in MLC.

    If the repository already exists locally in the MLC repos directory, it fetches the latest changes only if there are no
    uncommited modifications(excluding untracked files/folders). The `pull` action could be also used to checkout
    to a particular branch, commit or release tag using flags --checkout and --tag.

    Example Command:

    mlc pull repo mlcommons@script-automations


    - `--checkout <commit_sha>`: Checks out a specific commit after cloning (applicable when the repository exists locally).
    - `--branch <branch_name>`: Checks out a specific branch while cloning a new repository. When strict fast-forward-only pulls are requested for an existing checkout, it also selects the local branch to switch to before pulling `origin/<branch>`.
    - `--tag <release_tag>`: Checks out a particular release tag.
    - `--pat <access_token>` or `--ssh`: Clones a private repository using a personal access token or SSH.
    - `--force`: For existing repositories with local tracked changes, stashes changes before pull and reapplies them after pull.
    - `--shallow`: Perform a shallow clone with `--depth=1` (fastest for a fresh copy without history). For existing repos, only applied if the repo is already shallow; otherwise ignored with a warning.
    - `--depth=N`: Perform a shallow clone/pull with the specified history depth (e.g. `--depth=5`). For existing repos, `--depth` is only applied when the repository is already a shallow clone; passing `--depth` to a full-history clone would corrupt it and is therefore ignored with a warning.
    - `--extra_git_args=<args>`: Pass additional arguments to the `git clone` command (e.g. `--extra_git_args="--filter=blob:none"`). Only applies when cloning a new repository; not used for pull on existing repos. Accepts only trusted input — arguments are passed directly to git without further validation.

    Example Output:

      anandhu@anandhu-VivoBook-ASUSLaptop-X515UA-M515UA:~$ mlc pull repo mlcommons@mlperf-automations
      [2025-02-19 16:46:27,208 main.py:1260 INFO] - Cloning repository https://github.com/mlcommons/mlperf-automations.git
      to /home/anandhu/MLC/repos/mlcommons@mlperf-automations...
      Cloning into '/home/anandhu/MLC/repos/mlcommons@mlperf-automations'...
      remote: Enumerating objects: 77610, done.
      remote: Counting objects: 100% (2199/2199), done.
      remote: Compressing objects: 100% (1103/1103), done.
      remote: Total 77610 (delta 1616), reused 1109 (delta 1095), pack-reused 75411 (from 2)
      Receiving objects: 100% (77610/77610), 18.36 MiB | 672.00 KiB/s, done.
      Resolving deltas: 100% (53818/53818), done.
      [2025-02-19 16:46:57,604 main.py:1288 INFO] - Repository successfully pulled.
      [2025-02-19 16:46:57,605 main.py:1289 INFO] - Registering the repo in repos.json
      [2025-02-19 16:46:57,605 main.py:1126 INFO] - Added new repo path: /home/anandhu/MLC/repos/mlcommons@mlperf-automations
      [2025-02-19 16:46:57,606 main.py:1130 INFO] - Updated repos.json at /home/anandhu/MLC/repos/repos.json

    Note:
        - repo_uid and repo_alias are not supported in the pull action for the repo target.
        - Only one of --checkout, --branch, or --tag should be specified at a time.

        """
        repo_url = run_args.get('repo', run_args.get('url', 'repo'))
        if not repo_url or repo_url == "repo":
            for repo_object in self.repos:
                if os.path.exists(os.path.join(repo_object.path, ".git")) and os.access(
                        repo_object.path, os.W_OK):
                    repo_folder_name = os.path.basename(repo_object.path)
                    res = self.pull_repo(
                        repo_folder_name, repo_path=repo_object.path, force=run_args.get(
                            'force'),
                        shallow=run_args.get('shallow', False),
                        depth=run_args.get('depth'),
                        extra_git_args=run_args.get('extra_git_args'),
                        fast_forward_only=run_args.get('fast_forward_only', False))
                    if res['return'] > 0:
                        return res
        else:
            branch = run_args.get('branch')
            checkout = run_args.get('checkout')
            tag = run_args.get('tag')

            pat = run_args.get('pat')
            ssh = run_args.get('ssh')
            force = run_args.get('force')
            ignore_on_conflict = run_args.get('ignore_on_conflict')
            shallow = run_args.get('shallow', False)
            depth = run_args.get('depth')
            extra_git_args = run_args.get('extra_git_args')
            fast_forward_only = run_args.get('fast_forward_only', False)

            if sum(bool(var) for var in [branch, checkout, tag]) > 1:
                return {
                    "return": 1, "error": "Only one among the three flags(branch, checkout and tag) could be specified"}

            res = self.pull_repo(
                repo_url,
                branch,
                checkout,
                tag,
                pat,
                ssh,
                ignore_on_conflict=ignore_on_conflict,
                force=force,
                shallow=shallow,
                depth=depth,
                extra_git_args=extra_git_args,
                fast_forward_only=fast_forward_only)
            if res['return'] > 0:
                return res

        return {'return': 0}

    def show(self, run_args):
        return self.list(run_args)

    def list(self, run_args):
        """
    ####################################################################################################################
    Target: Repo/Repos
    Action: List/Show
    ####################################################################################################################

    The `list` action displays all registered MLC repositories along with their aliases and paths.

    Example Command:

    mlc list repo

    Example Output:

      anandhu@anandhu-VivoBook-ASUSLaptop-X515UA-M515UA:~$ mlc list repo
      [2025-02-19 16:56:31,847 main.py:1349 INFO] - Listing all repositories.

      Repositories:
      -------------
      - Alias: local
        Path:  /home/anandhu/MLC/repos/local

      - Alias: mlcommons@mlperf-automations
        Path:  /home/anandhu/MLC/repos/mlcommons@mlperf-automations
      -------------
      [2025-02-19 16:56:31,850 main.py:1356 INFO] - Repository listing ended

        """
        logger.info("Listing all repositories.")
        print("\nRepositories:")
        print("-------------")
        for repo_object in self.repos:
            print(f"- Alias: {repo_object.meta.get('alias', 'Unknown')}")
            print(f"  Path:  {repo_object.path}\n")
        print("-------------")
        logger.info("Repository listing ended")
        return {"return": 0}

    def rm(self, run_args):
        """
    ####################################################################################################################
    Target: Repo
    Action: rm
    ####################################################################################################################

    The `rm` action removes a specified repository from MLCFlow, deleting the repository folder, its index entries,
    and its registration.
    If there are any modified local changes, the user will be prompted for confirmation unless the `-f` flag is used
    for force removal.

    Example Command:

    mlc rm repo mlcommons@mlperf-automations

    Example Output:

      anandhu@anandhu-VivoBook-ASUSLaptop-X515UA-M515UA:~$ mlc rm repo mlcommons@mlperf-automations
      [2025-02-19 17:01:59,483 main.py:1360 INFO] - rm command has been called for repo. This would delete the repo folder and unregister the repo from repos.json
      [2025-02-19 17:01:59,521 main.py:1380 INFO] - No local changes detected. Removing repo...
      [2025-02-19 17:01:59,581 main.py:1384 INFO] - Repo mlcommons@mlperf-automations residing in path /home/anandhu/MLC/repos/mlcommons@mlperf-automations has been successfully removed
      [2025-02-19 17:01:59,581 main.py:1385 INFO] - Checking whether the repo was registered in repos.json
      [2025-02-19 17:01:59,581 main.py:1134 INFO] - Unregistering the repo in path /home/anandhu/MLC/repos/mlcommons@mlperf-automations
      [2025-02-19 17:01:59,581 main.py:1144 INFO] - Path: /home/anandhu/MLC/repos/mlcommons@mlperf-automations has been removed.

        """
        if not run_args['repo']:
            logger.error("The repository to be removed is not specified")
            return {"return": 1,
                    "error": "The repository to be removed is not specified"}

        r = self.find(run_args)

        if r['return'] == 0:

            list_repos = r['list']
            if len(list_repos) > 1:
                return {
                    "return": 1, "error": "Please select a unique repo by repo alias or repo UID to remove"}

            repo = list_repos[0]
            repo_path = repo.path

        else:
            repo = run_args['repo']
            if os.path.exists(repo):
                repo_path = repo
            elif os.path.isdir(os.path.join(self.repos_path, repo)):
                repo_path = os.path.join(self.repos_path, repo)
            else:
                return r

        repos_file_path = os.path.join(self.repos_path, 'repos.json')

        force_remove = True if run_args.get('f') else False
        index = Action.get_index(self)
        index.remove_repo_from_index(repo_path)

        return rm_repo(repo_path, repos_file_path, force_remove)


def _repos_lock_file(repos_file_path):
    """Return the lock file path for a repos.json file."""
    return repos_file_path + ".lock"


def rm_repo(repo_path, repos_file_path, force_remove):
    """Remove a repo directory and unregister it.

    Takes the same per-repo lock pull_repo uses. Without it, `mlc rm repo X`
    running against a concurrent `mlc pull repo X` would delete the tree while
    the pull is mid-clone or mid-rename -- the pull's lock only excluded other
    pullers.

    LOCK ORDERING: per-repo lock first, then repos.json.lock (taken by
    unregister_repo below). Same order as pull_repo.
    """
    try:
        with _repo_lock(repo_path + ".lock", _get_repo_lock_timeout()):
            return _rm_repo_locked(repo_path, repos_file_path, force_remove)
    except Timeout:
        return {
            'return': 1,
            'error': (
                f"Could not acquire lock for {repo_path} before removing it. "
                "Another mlc process may be cloning or pulling this repo."
            )
        }
    except RepoLockPermissionError as e:
        return {
            'return': 1,
            'error': (
                f"Permission denied creating the lock file for {repo_path}: "
                f"{e}. This requires write access to the repos directory."
            )
        }


def _rm_repo_locked(repo_path, repos_file_path, force_remove):
    repo_name = os.path.basename(repo_path)
    mlc_repos_path = os.path.abspath(os.path.dirname(repos_file_path))
    repo_parent_path = os.path.abspath(os.path.dirname(repo_path))

    if os.path.isdir(repo_path) and os.path.samefile(
            mlc_repos_path, repo_parent_path):
        # Check for local changes
        status_command = [
            'git',
            '-C',
            repo_path,
            'status',
            '--porcelain',
            '--untracked-files=no']
        local_changes = subprocess.run(
            status_command, capture_output=True, text=True)

        if local_changes.stdout:
            logger.warning(
                "Local changes detected in repository. Changes are listed below:")
            print(local_changes.stdout)
            confirm_remove = True if force_remove or (
                input("Continue to remove repo?").lower()) in [
                "yes", "y"] else False
        else:
            logger.info("No local changes detected. Removing repo...")
            confirm_remove = True
        if confirm_remove:
            if force_remove:
                logger.info("Force remove is set.")
            try:
                shutil.rmtree(repo_path)
                logger.info(
                    f"Repo {repo_name} residing in path {repo_path} has been successfully removed")
            except FileNotFoundError:
                logger.warning(
                    f"{repo_path} was already removed by another process.")
            logger.info(
                "Checking whether the repo was registered in repos.json")
            unregister_repo(repo_path, repos_file_path)
        else:
            logger.info("rm repo ooperation cancelled by user!")

    else:
        logger.warning(
            f"Repo {repo_name} was not found in the repo folder. repos.json will be checked for external paths. If any, that will be removed.")
        unregister_repo(repo_path, repos_file_path)

    return {"return": 0}


def unregister_repo(repo_path, repos_file_path):
    logger.info(f"Unregistering the repo in path {repo_path}")

    try:
        # LOCK ORDERING: repos.json.lock is the *inner* lock -- callers such as
        # pull_repo may already hold <repo_path>.lock. Never acquire a per-repo
        # lock while holding this one, or the two orders will deadlock until
        # their timeouts expire.
        with FileLock(_repos_lock_file(repos_file_path), timeout=60):
            with open(repos_file_path, 'r') as f:
                repos_list = json.load(f)

            if repo_path in repos_list:
                repos_list.remove(repo_path)
                _atomic_write_json(repos_file_path, repos_list)
                logger.info(f"Path: {repo_path} has been removed.")
            else:
                logger.info(
                    f"Path: {repo_path} not found in {repos_file_path}. Nothing to be unregistered!")
    except Timeout:
        return {
            'return': 1,
            'error': (
                "Could not acquire lock for repos.json after 60 seconds. "
                "Another mlc process may be modifying repos.json. "
                "Try again once the other operation completes."
            )
        }

    return {'return': 0}
