import os
import hashlib
import logging
import json
import yaml
import logging
import re
import shutil
import sys
from pathlib import Path
from contextlib import contextmanager
from filelock import FileLock, Timeout

from .logger import logger, setup_logging

from . import utils
from .index import Index
from .repo import Repo
from .item import Item
from .error_codes import WarningCode

# Distribution name of the packaged script content, and the top level
# directory it ships that directory under.
PACKAGE_REPO_DIST = "mlc-scripts"
PACKAGE_REPO_MODULE = "mlc_scripts"


class RootNotWritableError(Exception):
    """A configured repo or cache root cannot be initialised.

    Raised during Action construction, i.e. before any command runs, so the
    CLI reports it as a configuration problem rather than a crash.
    """


def default_mlc_root():
    """The ~/MLC directory everything else hangs off."""
    return os.path.join(os.path.expanduser("~"), "MLC")


def resolve_cache_path():
    """Resolve the cache root.

    1. $MLC_CACHE when set.
    2. $MLC_REPOS when *that* is set explicitly. Before the split there was
       one root, so anyone who pinned MLC_REPOS has their caches under it
       today. Relocating them silently is exactly the failure this design
       exists to avoid, so an explicit MLC_REPOS keeps its cache.
    3. ~/MLC/repos.

    Note what is deliberately absent: the automatically resolved per
    environment repo root never appears here. If it did, installing
    mlc-scripts into a fresh environment would relocate every cached dataset
    and the next benchmark would download all of it again.

    Defaulting to ~/MLC/repos also means the shared local repo is today's
    local repo, so nothing on disk has to move.
    """
    explicit = os.environ.get('MLC_CACHE', '').strip()
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))

    explicit_repos = os.environ.get('MLC_REPOS', '').strip()
    if explicit_repos:
        return os.path.abspath(os.path.expanduser(explicit_repos))

    return os.path.join(default_mlc_root(), "repos")


def find_package_repo():
    """Locate an mlc-scripts install in the *running interpreter*.

    Resolved through importlib.metadata rather than the working directory:
    scripts change directory constantly during a run (run.sh executes inside
    its cache entry), so a cwd derived answer could change mid run.

    Returns (path, version), or (None, None) when the distribution is absent
    or ships no repo root.
    """
    try:
        from importlib import metadata as importlib_metadata
    except ImportError:  # pragma: no cover - Python < 3.8
        return (None, None)

    try:
        dist = importlib_metadata.distribution(PACKAGE_REPO_DIST)
    except Exception:
        return (None, None)

    version = None
    try:
        version = dist.version
    except Exception:
        version = None

    candidates = []
    try:
        located = dist.locate_file(PACKAGE_REPO_MODULE)
        if located is not None:
            candidates.append(str(located))
    except Exception:
        pass

    # Fallback for layouts where locate_file cannot resolve the directory
    # (editable installs using a path hook, for example).
    try:
        import importlib.util
        spec = importlib.util.find_spec(PACKAGE_REPO_MODULE)
        if spec is not None:
            if spec.submodule_search_locations:
                candidates.extend(list(spec.submodule_search_locations))
            elif spec.origin:
                candidates.append(os.path.dirname(spec.origin))
    except Exception:
        pass

    for candidate in candidates:
        candidate = os.path.abspath(candidate)
        if not os.path.isdir(candidate):
            continue
        # Deliberately not requiring meta.yaml: a damaged or partially
        # upgraded install would then look like "no package installed" and
        # silently relocate the whole repo root back to ~/MLC/repos.
        # Registration checks the meta and complains; root resolution only
        # needs to know the environment has mlc-scripts in it.
        # meta.yaml OR a script/ tree. Requiring meta.yaml alone would make a
        # damaged install look like "not installed" and silently relocate the
        # repo root; accepting a bare __init__.py would match the empty
        # mlc_scripts/ stub in an editable checkout, whose content lives at
        # the checkout root instead.
        if os.path.isfile(os.path.join(candidate, "meta.yaml")) or \
                os.path.isdir(os.path.join(candidate, "script")):
            return (candidate, version)

        # Editable install: mlc_scripts/ is the stub committed to the repo
        # and the real payload sits at the checkout root beside it.
        parent = os.path.dirname(candidate)
        if os.path.isfile(os.path.join(parent, "meta.yaml")) and \
                os.path.isdir(os.path.join(parent, "script")):
            return (parent, version)

    return (None, None)


def environment_key(path):
    """Short, stable key naming the environment a repo root belongs to."""
    return hashlib.sha256(
        os.path.abspath(path).encode("utf-8")).hexdigest()[:12]


def resolve_repos_path(package_repo_path):
    """Resolve the repo root.

    1. $MLC_REPOS when set - an explicit value always wins. Note that a
       packaged mlc-scripts is still registered into that root; what gives
       you "my checkout and nothing else" is the uid rule, under which a
       checkout registered there displaces the packaged copy.
    2. ~/MLC/envs/<hash of site-packages> when mlc-scripts is installed in
       the running interpreter.
    3. ~/MLC/repos, today's default.
    """
    explicit = os.environ.get('MLC_REPOS', '').strip()
    if explicit:
        return os.path.abspath(os.path.expanduser(explicit))

    if package_repo_path:
        site_packages = os.path.dirname(os.path.abspath(package_repo_path))
        return os.path.join(
            default_mlc_root(), "envs", environment_key(site_packages))

    return os.path.join(default_mlc_root(), "repos")


# Base class for actions


class Action:
    repos_path = None
    cfg = None
    action_type = None
    logger = None
    local_repo = None
    current_repo_path = None
    repos = []  # list of Repo objects

    # Main access function to simulate a Python interface for CLI
    def access(self, options):
        """
        Access function to simulate CLI actions in Python.

        Args:
        options (dict): Dictionary containing action and relevant parameters.
        """
        from .action_factory import get_action

        # logger.info(f"options in access = {options}")

        action_name = options.get('action')
        if not action_name:
            return {'return': 1, 'error': "'action' key is required in options"}
        # logger.info(f"options = {options}")

        action_name = action_name.replace("-", "_")

        action_target = options.get('target')
        if not action_target:
            # Default to script if not provided
            action_target = options.get('automation', 'script')
        action_target_split = action_target.split(",")
        action_target = action_target_split[0]

        action = get_action(action_target,
                            self.parent if self.parent else self)

        if action and hasattr(action, action_name):
            # Find the method and call it with the options
            method = getattr(action, action_name)
            result = method(options)
            # logger.info(f"result ={result}")
            return result
        else:
            return {
                'return': 1, 'error': f"'{action_name}' action is not supported for {action_target}."}
        return {'return': 0}

    def bundled_automation_path(self, target):
        """
        Resolve <target> (e.g. "script") relative to the automation/ engine
        bundled with this mlcflow install.

        automation/ ships as a top-level package alongside mlc/, both in the
        editable checkout (mlcflow/automation) and in site-packages once
        installed, since mlc/action.py always lives one level under the
        package root that automation/ is a sibling of.

        Returns the absolute path if it exists, else None.
        """
        pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        target_folder = os.path.join(pkg_root, 'automation', target)
        return target_folder if os.path.isdir(target_folder) else None

    def find_target_folder(self, target):
        """
        Resolve the automation/<target> folder to load the engine from, in
        order:

        1. The engine bundled with mlcflow itself (bundled_automation_path())
           - this is always preferred and covers the normal case, since
           automation/ ships inside every mlcflow install.
        2. A fallback scan of registered repos for a custom/external
           'automation' folder (a dev-override escape hatch), used only if
           step 1 finds nothing - e.g. a bundled install is missing/corrupted.

        Returns the absolute path to automation/<target>, or None if neither
        source has it (the caller then auto-pulls mlperf-automations as a
        last resort - see call_script_module_function()).
        """
        bundled = self.bundled_automation_path(target)
        if bundled:
            return bundled

        # Traverse through each repo to find the first 'target' folder inside
        # an 'automation' folder
        for repo in self.repos:
            repo_path = repo.path
            if os.path.isdir(repo_path):
                automation_folder = os.path.join(repo_path, 'automation')

                if os.path.isdir(automation_folder):
                    # Check if there's a 'script' folder inside the
                    # 'automation' folder
                    target_folder = os.path.join(automation_folder, target)
                    if os.path.isdir(target_folder):
                        return target_folder
        return None

    def load_repos_and_meta(self):
        repos_list = []
        repos_file_path = os.path.join(self.repos_path, 'repos.json')

        # Read the JSON file line by line
        try:
            # Load and parse the JSON file containing the list of repository
            # paths
            with open(repos_file_path, 'r') as file:
                repo_paths = json.load(file)  # Load the JSON file into a list
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON: {e}")
            return []
        except FileNotFoundError:
            logger.error(f"Error: File {repos_file_path} not found.")
            return []
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            return []

        def is_curdir_inside_path(base_path):
            # Convert to absolute paths
            base_path = Path(base_path).resolve()
            curdir = Path.cwd().resolve()

            # Check if curdir is inside base_path
            return base_path in curdir.parents or curdir == base_path

        # Iterate through the list of repository paths
        for repo_path in repo_paths:
            if not os.path.exists(repo_path):
                logger.warning(
                    f"""Warning: {repo_path} not found. Considering it as a corrupt entry and deleting from repos.json...""")
                from .repo_action import rm_repo
                res = rm_repo(
                    repo_path,
                    os.path.join(
                        self.repos_path,
                        'repos.json'),
                    True)

                if res["return"] > 0:
                    return res
                continue

            repo_path = repo_path.strip()  # Remove any extra whitespace or newlines
            if is_curdir_inside_path(repo_path):
                self.current_repo_path = repo_path

           # Skip empty lines
            if not repo_path:
                continue

            meta_yaml_path = os.path.join(repo_path, "meta.yaml")

            # Check if meta.yaml exists
            if not os.path.isfile(meta_yaml_path):
                logger.warning(
                    f"{meta_yaml_path} not found. Could be due to accidental deletion of meta.yaml. Try to stash the changes or reclone by doing `rm repo` and `pull repo`. Skipping...")
                continue

            # Load the YAML file
            try:
                with open(meta_yaml_path, 'r') as yaml_file:
                    meta = yaml.safe_load(yaml_file)
            except yaml.YAMLError as e:
                logger.error(f"Error loading YAML in {meta_yaml_path}: {e}")
                continue

            if meta['alias'] == "local":
                self.local_repo = f"""{meta['alias']},{meta['uid']}"""
            # Create a Repo object and add it to the list
            repos_list.append(Repo(path=repo_path, meta=meta))
        return repos_list

    def load_repos(self):
        # todo: what if the repo is already found in the repos folder but not registered and we pull the same repo
        # Get the path to the repos.json file in $HOME/MLC
        repos_file_path = os.path.join(self.repos_path, 'repos.json')

        # Check if the file exists
        if not os.path.exists(repos_file_path):
            logger.error(f"Error: File not found at {repos_file_path}")
            return None

        # Load and parse the JSON file
        try:
            with open(repos_file_path, 'r') as file:
                repos = json.load(file)
                return repos
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON: {e}")
            return None
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            return None

    def get_index(self):
        if self._index is None:
            self._index = Index(self.repos_path, self.repos)
        return self._index

    def _item_from_index_entry(self, res, target_name):
        """Create an Item from an index entry and skip entries with invalid meta."""
        it = Item(res['path'], res['repo'])
        if not isinstance(it.meta, dict):
            logger.warning(
                f"Skipping {target_name} item at {it.path}: missing or invalid meta")
            return None
        return it

    def __init__(self):
        setup_logging(log_path=os.getcwd(), log_file='.mlc-log.txt')
        self.logger = logger

        # Two roots, resolved on two independent chains. The repo root may
        # vary per environment; the cache root does not vary with it.
        self.cache_path = resolve_cache_path()
        self.package_repo_path, self.package_repo_version = find_package_repo()
        self.repos_path = resolve_repos_path(self.package_repo_path)

        os.makedirs(self.repos_path, exist_ok=True)

        # The local repo always lives under the cache root, never under the
        # per environment repo root. Cache entries are *items* of this repo -
        # Action.add() resolves their destination through the registry, not
        # through a path variable - so this is what makes MLC_CACHE
        # authoritative. Experiments and scripts from `mlc add script` come
        # along, which is intended: authored work should not disappear when
        # you switch environments.
        candidate_local = str(
            Path(os.path.join(self.cache_path, 'local')).expanduser().resolve())

        repo_json_path = os.path.join(self.repos_path, "repos.json")
        if not os.path.exists(repo_json_path):
            self._create_local_repo(candidate_local)
            try:
                with open(repo_json_path, 'w') as f:
                    json.dump([candidate_local], f, indent=2)
                logger.info(
                    f"Created repos.json in {self.repos_path} and initialised with local cache folder path: {candidate_local}")
            except OSError as e:
                raise RootNotWritableError(
                    f"Could not create {repo_json_path} ({e}). "
                    f"Set MLC_REPOS to a writable directory.") from e

        self.repos = self.load_repos_and_meta()
        # logger.info(f"In Action class: {self.repos_path}")
        self._index = None

        # There must be exactly one local repo, and every path derived from
        # it must agree. Resolving it once and deriving cache_path from the
        # result is what keeps `mlc list repo`, Action.add()'s destination,
        # fix_cache_paths() and the docker/apptainer build contexts pointing
        # at the same directory.
        local_repo_path = self._ensure_local_registered(candidate_local)

        self.local_repo_path = local_repo_path
        self.cache_path = os.path.dirname(local_repo_path)
        self.local_cache_path = os.path.join(local_repo_path, "cache")
        if not os.path.exists(self.local_cache_path):
            os.makedirs(self.local_cache_path, exist_ok=True)

        self._sync_package_repo()

    def _create_local_repo(self, local_repo_path):
        """Create the local repo directory and its meta if absent."""
        if not os.path.exists(local_repo_path):
            os.makedirs(local_repo_path, exist_ok=True)

        meta_path = os.path.join(local_repo_path, "meta.yaml")
        if not os.path.isfile(meta_path):
            local_repo_meta = {
                "alias": "local",
                "name": "MLC local repository",
                "uid": utils.get_new_uid()['uid']}
            with open(meta_path, "w") as json_file:
                json.dump(local_repo_meta, json_file, indent=4)

    @contextmanager
    def _repos_json_lock(self):
        """Serialise read-modify-write on repos.json.

        Every index file is already guarded by a FileLock; repos.json was
        not, and discovery now touches it on far more runs than before.
        """
        repos_file_path = os.path.join(self.repos_path, 'repos.json')

        # Acquire explicitly rather than wrapping the yield in a try that
        # also guards the body: an OSError raised by the *caller* would then
        # be swallowed here, the generator would yield a second time, and
        # contextlib would report "generator didn't stop after throw()" -
        # erasing the real error.
        lock = FileLock(repos_file_path + ".lock", timeout=60)
        acquired = False
        try:
            lock.acquire()
            acquired = True
        except Timeout:
            logger.warning(
                f"Timeout acquiring the lock on {repos_file_path}; proceeding unlocked.")
        except OSError as e:
            # A read-only or non-writable repo root cannot host a lock file.
            # That is a legitimate deployment (a shared, admin-managed root)
            # and must not take every command down with it.
            logger.debug(
                f"Could not create the lock for {repos_file_path} ({e}); proceeding unlocked.")

        try:
            yield
        finally:
            if acquired:
                lock.release()

    def _rewrite_repos_json(self, repos_list):
        """Persist the registry for the active repo root.

        Returns True on success. A non-writable repo root is a supported
        deployment (shared, admin-managed), so failing to write is reported
        and the run continues with the registry it loaded.
        """
        repos_file_path = os.path.join(self.repos_path, 'repos.json')
        try:
            with open(repos_file_path, 'w') as f:
                json.dump(repos_list, f, indent=2)
            return True
        except OSError as e:
            logger.warning(
                f"Could not update {repos_file_path} ({e}). Continuing with the registry as it is on disk; "
                f"changes to registered repos will not persist.")
            return False

    def _ensure_local_registered(self, candidate_local):
        """Resolve the one local repo and make the registry agree.

        Returns its absolute path.

        Two invariants matter and both were violated before. First, exactly
        one repo may be aliased 'local': load_repos_and_meta() sets
        self.local_repo from the *last* match while other code took the
        first, so duplicates make Action.add()'s destination and
        local_cache_path disagree silently. Second, the answer must be stable
        within a run, since cache_path and the docker/apptainer build
        contexts are derived from it.

        Which one wins:
          - MLC_CACHE set explicitly  -> $MLC_CACHE/local, the user said so.
          - otherwise, an already registered local -> keep it, so a stray
            MLC_CACHE cannot silently re-point someone's registry.
          - nothing registered -> the candidate.
        """
        registered_locals = [repo.path for repo in self.repos
                             if repo.meta.get('alias') == 'local']

        if os.environ.get('MLC_CACHE', '').strip() or not registered_locals:
            chosen = os.path.abspath(candidate_local)
        else:
            chosen = os.path.abspath(registered_locals[0])
            if os.path.abspath(candidate_local) != chosen:
                logger.debug(
                    f"Keeping the registered local repo at {chosen}; set MLC_CACHE to move it.")

        self._create_local_repo(chosen)

        superseded = [p for p in registered_locals
                      if os.path.abspath(p) != chosen]
        if not superseded and any(
                os.path.abspath(p) == chosen for p in registered_locals):
            return chosen

        repos_file_path = os.path.join(self.repos_path, 'repos.json')
        with self._repos_json_lock():
            try:
                with open(repos_file_path, 'r') as f:
                    repos_list = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                logger.error(f"Could not read {repos_file_path}: {e}")
                return chosen

            if superseded:
                superseded_abs = {os.path.abspath(p) for p in superseded}
                repos_list = [p for p in repos_list
                              if os.path.abspath(p) not in superseded_abs]
                for path in superseded:
                    logger.info(
                        f"Local repo is now {chosen}; unregistering the previous one at {path}. "
                        f"Its contents are left on disk.")

            if not any(os.path.abspath(p) == chosen for p in repos_list):
                repos_list.insert(0, chosen)
                logger.debug(
                    f"Registered the shared local repo {chosen} in {repos_file_path}")

            self._rewrite_repos_json(repos_list)

        self.repos = self.load_repos_and_meta()
        return chosen

    def _sync_package_repo(self):
        """Register the mlc-scripts tree shipped in this environment.

        Runs at the start of every command. The package directory is an
        ordinary non-git repo, so nothing downstream needs to know where it
        came from.

        When a repo carrying the same uid is already registered it got there
        through an explicit `mlc pull repo`, and that copy wins. We only say
        so - on every run, not just at registration, because a shell variable
        is invisible six months later and a submission that cites a version
        which never ran is not.
        """
        pkg_path = getattr(self, 'package_repo_path', None)
        if not pkg_path:
            return

        meta_path = os.path.join(pkg_path, "meta.yaml")
        if not os.path.isfile(meta_path):
            logger.warning(
                f"The installed {PACKAGE_REPO_DIST} has no meta.yaml at {meta_path}, so it cannot be registered as a repo. "
                f"Reinstall it with `pip install --force-reinstall {PACKAGE_REPO_DIST}`.")
            return

        # read_yaml logs and returns None on a parse error rather than
        # raising, so distinguish the cases by what came back.
        pkg_meta = utils.read_yaml(meta_path)

        if not isinstance(pkg_meta, dict):
            logger.warning(
                f"{meta_path} is empty or not valid YAML, so the installed {PACKAGE_REPO_DIST} cannot be registered. "
                f"Reinstall it with `pip install --force-reinstall {PACKAGE_REPO_DIST}`.")
            return

        if not pkg_meta.get('uid'):
            logger.warning(
                f"{meta_path} has no uid. The installed {PACKAGE_REPO_DIST} cannot be registered.")
            return

        version = getattr(self, 'package_repo_version', None) or 'unknown'

        for repo in self.repos:
            if os.path.abspath(repo.path) == os.path.abspath(pkg_path):
                return  # already registered, nothing to announce
            if repo.meta.get('uid') == pkg_meta['uid']:
                logger.info(
                    f"Using {repo.path}, shadowing {PACKAGE_REPO_DIST} {version} at {pkg_path}")
                return

        repos_file_path = os.path.join(self.repos_path, 'repos.json')
        persisted = True
        with self._repos_json_lock():
            try:
                with open(repos_file_path, 'r') as f:
                    repos_list = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                logger.error(f"Could not read {repos_file_path}: {e}")
                return

            if pkg_path not in repos_list:
                repos_list.append(pkg_path)
                persisted = self._rewrite_repos_json(repos_list)

        if persisted:
            logger.info(
                f"Registered {PACKAGE_REPO_DIST} {version} from {pkg_path}")
            self.repos = self.load_repos_and_meta()
            return

        # The registry is not writable - a shared, admin-managed root. Use the
        # package for this run anyway rather than claiming it was registered
        # and then behaving as though no content repo exists, which would send
        # the caller off to auto-clone one.
        logger.info(
            f"Using {PACKAGE_REPO_DIST} {version} from {pkg_path} for this run; it could not be added to {repos_file_path}.")
        self.repos = self.load_repos_and_meta()
        if not any(os.path.abspath(r.path) == os.path.abspath(pkg_path)
                   for r in self.repos):
            self.repos.append(Repo(path=pkg_path, meta=pkg_meta))

    def add(self, i):
        """
        Adds a new item to the repository.

        Args:
            i (dict): Input dictionary with the following keys:
                - item_repo (tuple): Repository alias and UID (default: local repo).
                - item (str): Item alias and optional UID in "alias,uid" format.
                - tags (str): Comma-separated tags.
                - new_tags (str): Additional comma-separated tags to add.
                - yaml (bool): Whether to save metadata in YAML format. Defaults to JSON.

        Returns:
            dict: Result of the operation with 'return' code and error/message if applicable.
        """
        # Determine repository
        item_repo = i.get("item_repo")
        if not item_repo:
            item_repo = self.local_repo

        # Parse item details
        item = i.get("item")

        item_name, item_id = (None, None)
        if item:
            item_parts = item.split(",")
            item_name = item_parts[0]
            if len(item_parts) > 1:
                item_id = item_parts[1]

        # Generate a new UID if not provided
        if not item_id:
            res = utils.get_new_uid()
            if res['return'] > 0:
                return res
            item_id = res['uid']

        # Locate repository
        res = self.access(
            {
                "automation": "repo",
                "action": "find",
                "item": f"{item_repo}",
            }
        )
        if res["return"] > 0:
            return res

        if len(res["list"]) == 0:
            return {
                'return': 1, 'error': f"""The given repo {item_repo} is not registered in MLC"""}

        # Determine paths and metadata format
        repo = res["list"][0]
        repo_path = repo.path

        target_name = i.get('target_name', self.action_type)
        target_path = os.path.join(repo_path, target_name)
        if target_name in ["cache", "experiment"]:
            extra_tags_suffix = i.get('extra_tags', '').replace(",", "-")[:15]
            if extra_tags_suffix != '':
                suffix = f"_{extra_tags_suffix}"
            else:
                suffix = ''
            folder_name = f"""{i["script_alias"]}{suffix}_{item_name or item_id[:8]}""" if i.get(
                "script_alias") else item_name or item_id
        else:
            folder_name = item_name or item_id

        item_path = os.path.join(target_path, folder_name)

        if os.path.exists(item_path):
            return {"return": 1, "error": f"""Item exists at {item_path}"""}

        # Create item directory if it does not exist
        os.makedirs(item_path)

        res = self.save_new_meta(
            i,
            item_id,
            item_name,
            target_name,
            item_path,
            repo)
        if res['return'] > 0:
            return res

        return {
            "return": 0,
            "message": f"Item successfully added at {item_path}",
            "path": item_path,
            "repo": repo
        }

    def rm(self, i):
        """
        Removes an item from the repository.

        Args:
            i (dict): Input dictionary with the following keys:
                - item_repo (tuple): Repository alias and UID (default: local repo).
                - item (str): Item alias and optional UID in "alias,uid" format.
                - tags (str): Comma-separated tags.
                - yaml (bool): Whether to save metadata in YAML format. Defaults to JSON.

        Returns:
            dict: Result of the operation with 'return' code and error/message if applicable.
        """
        inp = {}

        # Parse item details
        item = i.get("item", i.get('artifact', i.get('details')))
        item_name, item_id, item_tags = (None, None, None)
        if item:
            item_parts = item.split(",")
            item_name = item_parts[0]
            if len(item_parts) > 1:
                item_id = item_parts[1]
        elif i.get('tags'):
            item_tags = i['tags']
        else:
            if i.get('target_name', self.action_type) != "cache":
                return {'return': 1, 'error': 'Item not given for rm action'}
            else:
                inp['fetch_all'] = True

        # Check force remove is set to True
        # Setting force remove to true would lead to removal of assets without
        # user prompt
        force_remove = True if i.get('f') else False

        if item_name:
            inp['alias'] = item_name
            # we dont know if the user gave the alias or the folder name, we
            # first check for alias and then the folder name
            inp['folder_name'] = item_name
            if utils.is_uid(item_name):
                inp['uid'] = item_name
        elif item_id:
            inp['uid'] = item_id
        if item_tags:
            inp['tags'] = item_tags

        target_name = i.get('target_name', self.action_type)
        inp['target_name'] = target_name
        res = self.search(inp)
        if res['return'] > 0:
            return res

        if len(res['list']) == 0:
            # Do not error out if fetch_all is used
            if inp.get("fetch_all", False) == True:
                logger.warning(
                    f"{target_name} is empty! nothing to be cleared!")
                return {"return": 0, "warnings": [
                    {"code": WarningCode.EMPTY_TARGET.code, "description": f"{target_name} is empty! nothing to be cleared!"}]}
            else:
                logger.warning(f"No {target_name} found for {inp}")
                return {'return': 0, "warnings": [
                    {"code": WarningCode.EMPTY_TARGET.code, "description": f"No {target_name} found for {inp}"}]}
        elif len(res['list']) > 1:
            logger.info(f"More than 1 {target_name} found for {inp}:")
            if not i.get('all'):
                for idx, item in enumerate(res["list"]):
                    logger.info(f"{idx}. Path: {item.path}, Meta: {item.meta}")

                if not force_remove:
                    user_choice = input(
                        "Would you like to proceed with all items? (yes/no): ").strip().lower()
                    if user_choice in ['yes', 'y']:
                        force_remove = True

        results = res['list']

        for result in results:
            item_path = result.path
            item_meta = result.meta

            if os.path.exists(item_path):
                if force_remove == True:
                    shutil.rmtree(item_path)
                else:
                    user_choice = input(
                        f"Confirm to delete {target_name} item: {item_path}? (yes/no): ").strip().lower()
                    if user_choice not in ['yes', 'y']:
                        continue
                    else:
                        shutil.rmtree(item_path)

                logger.info(
                    f"{target_name} item: {item_path} has been successfully removed")

            self.get_index().rm(item_meta, target_name, item_path)

        return {
            "return": 0,
            "message": f"Item {item_path} successfully removed",
        }

    def save_new_meta(self, i, item_id, item_name,
                      target_name, item_path, repo):
        # Prepare metadata
        item_meta = i.get('meta', {})
        item_meta.update({
            "alias": item_name,
            "uid": item_id,
        })

        # Process tags
        tags = i.get("tags", "").split(",") if i.get(
            "tags") else item_meta.get("tags", [])
        new_tags = i.get("new_tags", "").split(
            ",") if i.get("new_tags") else []

        item_meta["tags"] = list(set(tags + new_tags))  # Ensure unique tags

        # Save metadata
        meta_format = "yaml" if i.get("yaml") else "json"
        item_meta_path = os.path.join(item_path, f"meta.{meta_format}")

        if meta_format == "yaml":
            save_result = utils.save_yaml(item_meta_path, meta=item_meta)
        else:
            save_result = utils.save_json(item_meta_path, meta=item_meta)

        if save_result["return"] > 0:
            return save_result

        self.get_index().add(item_meta, target_name, item_path, repo)
        return {'return': 0}

    def update(self, i):
        """
        Update the tags of found items based on the input.

        Args:
            i (dict): Input dictionary with:
                - tags (str): Comma-separated tags to search for.
                - search_tags (str): Tags to add/update in the found items' meta.

        Returns:
            dict: Return code and message.
        """
        # Step 1: Search for items based on input tags
        target_name = i.get('target_name', i.get('target', "cache"))
        i['target_name'] = target_name
        ii = i.copy()
        quiet = ii.get('quiet', not sys.stdin.isatty())

        if i.get('search_tags'):
            ii['tags'] = ",".join(i['search_tags'])
        search_result = self.search(ii)
        if search_result['return'] > 0:
            return search_result

        found_items = search_result['list']
        if not found_items:
            res = self.add(i)
            if res['return'] > 0:
                return res
            found_items.append(Item(res['path'], res['repo']))
            # return {'return': 0, 'message': 'No items found for the given
            # tags.'}

        # Step 2: Prepare to update tags
        search_tags = i.get("search_tags", [])

        new_tags = set(search_tags)
        if len(found_items) > 1:
            if quiet:
                user_input = 'yes'
            else:
                # Step 3: Ask user for confirmation if multiple items are found
                user_input = input(
                    f"{len(found_items)} items found. Do you want to update all? (yes/no): ").strip().lower()
            if user_input not in ['yes', 'y']:
                return {'return': 0,
                        'message': 'Update operation canceled by the user.'}

        new_meta = i.get('meta')
        if new_meta.get('tags'):
            new_meta['tags'] = i.get('tags').split(",")

        # Step 4: Update tags in each found item
        for item in found_items:
            meta = {}
            # Load the current meta of the item
            item_meta_path = os.path.join(item.path, "meta.json")
            if os.path.exists(item_meta_path):
                res = utils.load_json(item_meta_path)
                if res['return'] > 0:
                    return res
                meta = res['meta']
            if i.get('replace_lists') and i.get("tags"):
                meta["tags"] = i["tags"].split(",")
            else:
                current_tags = set(meta.get("tags", []))
                updated_tags = current_tags.union(new_tags)
                meta["tags"] = list(updated_tags)
            utils.merge_dicts({"dict1": meta,
                               "dict2": new_meta,
                               "append_lists": True,
                               "append_unique": True})

            # Save the updated meta back to the item
            item.meta = meta
            save_result = utils.save_json(item_meta_path, meta=meta)
            self.get_index().update(meta, target_name, item.path, item.repo)

        return {
            'return': 0, 'message': f"Tags updated successfully for {len(found_items)} item(s).", 'list': found_items}

    def cp(self, run_args):
        action_target = run_args['target']
        if action_target != "script":
            return {
                "return": 1, "error": f"The {action_target} target is not currently supported for mv/cp actions"}
        inp = {}
        src_item = run_args.get('src')
        src_tags = None

        if src_item:
            # remove backslash if there in src item
            if src_item.endswith('/'):
                src_item = src_item[:-1]

            src_split = src_item.split(":")
            if len(src_split) > 1:
                src_repo = src_split[0].strip()
                src_item = src_split[1].strip()
            else:
                src_item = src_split[0].strip()

            inp['alias'] = src_item
            # we dont know if the user gave the alias or the folder name, we
            # first check for alias and then the folder name
            inp['folder_name'] = src_item

            if utils.is_uid(src_item):
                inp['uid'] = src_item
            src_id = src_item
        else:
            # src_tags must be there
            if not run_args.get("src_tags"):
                return {
                    'return': 1, 'error': 'Either "src" or "src_tags" must be provided as an input for cp method'}
            src_tags = run_args['src_tags']
            inp['tags'] = src_tags
            src_id = src_tags

        inp['target_name'] = action_target

        res = self.search(inp)

        choice = 0
        if len(res['list']) == 0:
            return {'return': 1, 'error': f'No {action_target} found for {src_id}'}
        elif len(res['list']) > 1 and not run_args.get("quiet"):
            print(f"More than one {action_target} found for {src_id}:")

            # Display available options
            for idx, item in enumerate(res['list'], start=1):
                print(f"{idx}. {item.path}")

            # Ask user to choose an item
            while True:
                choice = input(
                    "Select the correct one (enter number, default=1): ").strip()
                if choice == "":
                    choice = 1
                try:
                    choice = int(choice) - 1
                    if 0 <= choice < len(res['list']):
                        break
                    else:
                        print(
                            "Invalid selection. Please enter a number from the list.")
                except ValueError:
                    print("Invalid input. Please enter a number.")

        result = res['list'][choice]
        src_item_path = result.path
        src_item_meta = result.meta

        target_item = run_args['dest']
        target_split = target_item.split(":")

        if len(target_split) > 1:
            target_repo_name = target_split[0].strip()
            if target_repo_name == ".":
                if not self.current_repo_path:
                    return {
                        'return': 1, 'error': f"""Current directory is not inside a registered MLC repo and so using ".:" is not valid"""}
                target_repo_name = os.path.basename(self.current_repo_path)

            # Match on alias or uid as well as folder basename. The two are
            # not the same thing: the packaged repo has alias
            # mlcommons@mlperf-automations but sits in a folder called
            # mlc_scripts, so a basename-only lookup rejects the name every
            # user would reach for.
            target_repo = next(
                (k for k in self.repos
                 if k.meta.get('alias') == target_repo_name
                 or k.meta.get('uid') == target_repo_name
                 or os.path.basename(k.path) == target_repo_name), None)
            if target_repo is None:
                return {
                    'return': 1,
                    'error': f"""The target repo {target_repo_name} is not registered in MLC. Either register it by cloning from git with `mlc pull repo`, or create it with `mlc add repo`, and rerun the command."""}

            # Use the registered repo's real path. Joining repos_path with
            # the name assumes every repo sits directly under the repo root,
            # which is false for the shared local repo (it lives under the
            # cache root) and for any externally registered folder - it would
            # create a phantom directory outside every registered repo.
            target_repo_path = target_repo.path
            target_item_name = target_split[1].strip()
        else:
            target_repo = result.repo
            target_repo_path = result.repo.path
            target_item_name = target_split[0].strip()

        # Applies to both branches. Without a "<repo>:" prefix the destination
        # defaults to the *source* repo, which for a packaged install is
        # site-packages - the case that has already produced stray scripts in
        # working trees.
        pkg_path = getattr(self, 'package_repo_path', None)
        if pkg_path and os.path.abspath(
                target_repo_path) == os.path.abspath(pkg_path):
            logger.warning(
                f"{target_repo_path} belongs to the installed {PACKAGE_REPO_DIST}. Anything written there is "
                f"lost on the next upgrade or uninstall - prefix the destination with `local:` to keep it.")

        target_item_path = os.path.join(
            target_repo_path, action_target, target_item_name)
        res = self.copy_item(src_item_path, target_item_path)
        if res['return'] > 0:
            return res

        ii = {}
        ii['meta'] = result.meta.copy()
        if action_target == "script":
            ii['yaml'] = True

        tags = run_args.get('tags')
        item_id = run_args.get('item_id')

        if tags:
            ii['tags'] = tags

        # Generate a new UID if not provided
        if not item_id:
            res = utils.get_new_uid()
            if res['return'] > 0:
                return res
            item_id = res['uid']

        res = self.save_new_meta(
            ii,
            item_id,
            target_item_name,
            action_target,
            target_item_path,
            target_repo)

        dest_item = Item(target_item_path, target_repo)

        if res['return'] > 0:
            return res
        logger.info(
            f"{action_target} {src_item_path} copied to {target_item_path}")

        return {'return': 0, 'src': result, 'dest': dest_item}

    def copy_item(self, source_path, destination_path):
        try:
            # Copy the source folder to the destination
            shutil.copytree(source_path, destination_path)
            logger.info(
                f"Folder successfully copied from {source_path} to {destination_path}")
        except FileExistsError:
            return {
                'return': 1, 'error': f"Destination folder {destination_path} already exists."}
        except FileNotFoundError:
            return {'return': 1, 'error': f"Source folder {source_path} not found"}
        except Exception as e:
            return {'return': 1, 'error': f"An error occurred {e}"}

        return {'return': 0}

    def mv(self, run_args):
        target_name = run_args['target']
        if target_name != "script":
            return {
                "return": 1, "error": f"The {target_name} target is not currently supported for mv/cp actions"}
        res = self.cp(run_args)
        if res['return'] > 0:
            return res
        src = res['src']
        dest = res['dest']
        ii = {}
        ii['item'] = src.meta['uid']
        ii['f'] = True  # To remove the source without asking for user permission
        res = self.rm(ii)
        if res['return'] > 0:
            return res

        # Put the src uid to the destination path
        dest.meta['uid'] = src.meta['uid']
        dest._save_meta()
        self.get_index().update(dest.meta, target_name, dest.path, dest.repo)
        logger.info(
            f"""Item with uid {dest.meta['uid']} successfully moved from {src.path} to {dest.path}""")

        return {'return': 0, 'src': src, 'dest': dest}

    def search(self, i):
        indices = self.get_index().indices
        target = i.get('target_name', self.action_type)
        target_index = indices.get(target)
        result = []
        uid = i.get("uid")
        alias = i.get("alias")
        item_repo = i.get('item_repo')
        exact_tags_match = i.get('exact_tags_match', False)
        fetch_all = True if i.get('fetch_all') else False

        # For targets like cache, sometimes user would need to clear the entire cache folder present in the system
        # this helps to fetch entire data pertaining to particular target
        if fetch_all:
            if not target_index:
                return {'return': 0, 'list': result}

            for res in target_index:
                it = self._item_from_index_entry(res, target)
                if it:
                    result.append(it)
            return {'return': 0, 'list': result}

        if not uid and not alias and i.get('details'):
            details = i['details']
            details_split = details.split(",")
            if len(details_split) > 1:
                # Only treat as alias,uid if the second part is actually a
                # valid UID
                if utils.is_uid(details_split[1]):
                    alias = details_split[0]
                    uid = details_split[1]
                # Otherwise, don't parse as alias,uid - let it be treated as
                # tags
            else:
                if utils.is_uid(details_split[0]):
                    uid = details_split[0]
                else:
                    alias = details_split[0]

        if alias and ":" in alias:
            alias_split = alias.split(":")
            alias = alias_split[1]
            item_repo = alias_split[0]
        folder_name = i.get("folder_name")
        found = False

        if item_repo:
            res = self.access(
                {
                    "action": "find",
                    "target": "repo",
                    "repo": f"{item_repo}"
                }
            )
            if res["return"] > 0:
                return res
            if len(res['list']) == 0:
                return {'return': 1, 'error': f"""No repo found for {item_repo}"""}
            item_repo = res['list'][0]

        if target_index:
            if uid or alias:
                for res in target_index:
                    if (res["uid"] == uid or (alias and res["alias"] == alias)) and (
                            not item_repo or item_repo == res['repo']):
                        it = self._item_from_index_entry(res, target)
                        if it:
                            result.append(it)
                            found = True
                if not found and folder_name:
                    for res in target_index:
                        if os.path.basename(res["path"]) == folder_name:
                            it = self._item_from_index_entry(res, target)
                            if it:
                                result.append(it)
            else:
                tags = i.get("tags")
                if tags:
                    tags_split = tags.split(",")
                else:
                    return {
                        "return": 1, "error": f"Tags are not specified for completing the requested action"}
                if target == "script":
                    non_variation_tags = [
                        t for t in tags_split if not t.startswith("_")]
                    tags_to_match = non_variation_tags
                elif target in ["cache", "experiment"]:
                    tags_to_match = tags_split
                else:
                    return {
                        'return': 1, 'error': f"""Target {target} not handled in mlc yet"""}
                n_tags_ = [p for p in tags_to_match if p.startswith("-")]
                n_tags = [p[1:] for p in n_tags_]
                p_tags = list(set(tags_to_match) - set(n_tags_))
                for res in target_index:
                    c_tags = res.get("tags") or []
                    if (exact_tags_match and set(p_tags) == set(c_tags)) or (not exact_tags_match and set(
                            p_tags).issubset(set(c_tags)) and set(n_tags).isdisjoint(set(c_tags))):
                        it = self._item_from_index_entry(res, target)
                        if it:
                            result.append(it)
        return {'return': 0, 'list': result}

    find = search

    def reindex(self, i):
        """
        Reindex the specified target or all targets if none specified.

        Args:
            i (dict): Input dictionary with the following keys:
                - reindex_target (str, optional): Target to reindex ('script', 'cache', 'repo', 'all', or None).
                                                   If not provided or 'all', reindexes all targets.

        Returns:
            dict: Result of the operation with 'return' code 0 on success.

        Example:
            mlc reindex               # Reindex all targets
            mlc reindex script        # Reindex only script target
            mlc reindex cache         # Reindex only cache target
        """
        reindex_target = i.get('reindex_target')

        if not reindex_target or reindex_target == 'all' or reindex_target == 'repos' or reindex_target == 'repo':
            # Reindex all targets
            logger.info(
                "Reindexing all targets (script, cache, experiment)...")
            index = self.get_index()
            index.build_index(force_rebuild=True)

            logger.info("Successfully reindexed all targets.")
            return {'return': 0, 'message': 'All targets reindexed successfully'}
        else:

            logger.info(f"Reindexing {reindex_target} target...")
            index = self.get_index()

            # Clear the specific index
            '''
            if reindex_target in index.indices:
                index.indices[reindex_target] = []
                # Clear modified times for this target type only
                keys_to_remove = [k for k in index.modified_times.keys() if reindex_target in k]
                for key in keys_to_remove:
                    del index.modified_times[key]
            '''

            # Rebuild the index (we are rebuilding for all targets here as the
            # individual target rebuild is not implemented and not very
            # critical)
            index.build_index(force_rebuild=True)

            logger.info(f"Successfully reindexed {reindex_target} target.")
            return {
                'return': 0, 'message': f'{reindex_target} target reindexed successfully'}


default_parent = None


def get_default_parent():
    """The shared Action, built on first use.

    Constructing it has real side effects - it creates the repo and cache
    roots, may write repos.json, and registers an installed mlc-scripts - so
    it must not happen merely because something imported mlc. `import mlc`
    used to build one at module scope, which meant a stray MLC_CACHE in the
    environment could rewrite a registry without any command being run.
    """
    global default_parent
    if default_parent is None:
        default_parent = Action()
    return default_parent


def peek_default_parent():
    """The shared Action if one already exists, else None.

    For error reporting: building an Action there would re-run the very
    construction that just failed and bury the real traceback under a second
    one.
    """
    return default_parent


def access(i):
    from .action_factory import get_action

    action = i['action']
    target = i.get('target', i.get('automation'))
    action_class = get_action(target, get_default_parent())
    r = action_class.access(i)
    return r
