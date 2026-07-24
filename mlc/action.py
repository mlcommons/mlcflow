import os
import logging
import json
import yaml
import logging
import re
import shutil
import hashlib
import importlib.metadata as importlib_metadata
from pathlib import Path

from .logger import logger, setup_logging

from . import utils
from .index import Index
from .repo import Repo
from .item import Item
from .error_codes import WarningCode

# Entry-point group that pip-installable script-content packages advertise
# themselves under (e.g. a package shipping the mlperf-automations script/
# tree, or a fork of it under a different distribution name).
SCRIPT_PACKAGE_ENTRY_POINT_GROUP = "mlc.script_packages"


def _get_script_package_entry_points():
    """
    Version-compatible retrieval of entry points in
    SCRIPT_PACKAGE_ENTRY_POINT_GROUP. Python 3.10+ supports
    entry_points(group=...) directly; 3.8/3.9 only support the argument-less
    entry_points(), which returns a plain dict (or dict-like
    SelectableGroups) keyed by group name.
    """
    try:
        return list(importlib_metadata.entry_points(
            group=SCRIPT_PACKAGE_ENTRY_POINT_GROUP))
    except TypeError:
        # Python < 3.10: entry_points() takes no 'group' kwarg.
        try:
            all_eps = importlib_metadata.entry_points()
            return list(all_eps.get(SCRIPT_PACKAGE_ENTRY_POINT_GROUP, []))
        except Exception as e:
            logger.debug(
                f"Could not enumerate '{SCRIPT_PACKAGE_ENTRY_POINT_GROUP}' "
                f"entry points on this Python version: {e}")
            return []
    except Exception as e:
        logger.debug(
            f"Could not enumerate '{SCRIPT_PACKAGE_ENTRY_POINT_GROUP}' entry points: {e}")
        return []


def _pip_repo_cache_path(repos_path):
    return os.path.join(repos_path, "package_repos_cache.json")


def _load_pip_repo_cache(repos_path):
    cache_file = _pip_repo_cache_path(repos_path)
    if not os.path.isfile(cache_file):
        return {}
    try:
        with open(cache_file, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_pip_repo_cache(repos_path, cache):
    try:
        os.makedirs(repos_path, exist_ok=True)
        with open(_pip_repo_cache_path(repos_path), "w") as f:
            json.dump(cache, f, indent=2)
    except OSError as e:
        logger.debug(f"Could not save pip script package cache: {e}")


def discover_pip_script_repos(repos_path):
    """
    Discover script-content repos advertised by installed pip packages via
    the SCRIPT_PACKAGE_ENTRY_POINT_GROUP entry-point group. Returns a list
    of Repo objects, one per distinct installed *distribution*.

    Deliberately aliases each repo by the entry point's owning distribution
    name (`ep.dist.name`), NOT the self-chosen entry-point name (`ep.name`).
    PyPI enforces distribution-name uniqueness the same way GitHub enforces
    owner/repo uniqueness, so this is what lets a fork of a script-content
    package coexist with the original even if both declare the same
    entry-point name and even if the fork copied script uids verbatim.

    entry_points() itself is a fast, local, no-network scan of installed
    *.dist-info/entry_points.txt files (the same mechanism `pip list` relies
    on) and is called every run - it's cheap. What's NOT free is `.load()`,
    which actually imports the resolver module; that's cached across runs in
    <repos_path>/package_repos_cache.json keyed by distribution name, so an
    already-known package's content dir is reused directly without
    re-importing anything.

    Distributions that disappear (uninstalled) are simply left out of the
    returned list - Index.build_index()'s existing deleted-item detection
    (comparing each run's indexed files against modified_times.json) already
    prunes their content automatically, so no explicit
    Index.remove_repo_from_index() call is needed here.
    """
    cache = _load_pip_repo_cache(repos_path)
    updated_cache = {}
    discovered = {}
    cache_changed = False

    for ep in _get_script_package_entry_points():
        dist = getattr(ep, 'dist', None)
        dist_name = dist.name if dist is not None else ep.name
        if dist_name in discovered:
            # Same distribution declaring more than one entry point in this
            # group - first one found wins, it's still the same repo.
            continue

        content_dir = cache.get(dist_name)
        if content_dir and os.path.isdir(content_dir):
            # Already known from a previous run - reuse it, skip the
            # (import-triggering) ep.load() call entirely.
            updated_cache[dist_name] = content_dir
        else:
            try:
                module = ep.load()
                content_dir = os.path.dirname(os.path.abspath(module.__file__))
            except Exception as e:
                logger.warning(
                    f"Skipping script package entry point '{ep.name}' from "
                    f"distribution '{dist_name}': failed to load ({e})")
                continue

            if not os.path.isdir(content_dir):
                logger.warning(
                    f"Script package '{dist_name}' entry point resolved to "
                    f"a non-existent directory: {content_dir}. Skipping.")
                continue

            updated_cache[dist_name] = content_dir
            cache_changed = True
            logger.info(
                f"Discovered new script package '{dist_name}' at {content_dir}")

        uid = hashlib.md5(dist_name.encode('utf-8')).hexdigest()[:16]
        discovered[dist_name] = Repo(path=updated_cache[dist_name], meta={
            'alias': dist_name,
            'uid': uid,
            'source': 'pip',
        })

    if set(cache.keys()) - set(updated_cache.keys()):
        # one or more previously-known packages disappeared (uninstalled)
        cache_changed = True

    if cache_changed:
        _save_pip_repo_cache(repos_path, updated_cache)

    return list(discovered.values())


# Base class for actions


class Action:
    repos_path = None
    cfg = None
    action_type = None
    logger = None
    local_repo = None
    current_repo_path = None
    repos = []  # list of Repo objects

    @staticmethod
    def _is_pip_sourced_repo(repo_obj):
        """
        True if repo_obj (a Repo instance) was discovered from an installed
        pip package rather than a git-cloned/registered repo. Its files live
        inside the Python environment's site-packages, not ~/MLC/repos, and
        must not be mutated by mlc add/cp/mv/rm - that would corrupt the
        installed package outside of pip's own bookkeeping.
        """
        return bool(repo_obj) and getattr(
            repo_obj, 'meta', {}).get('source') == 'pip'

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
        # automation/ ships as a top-level package alongside mlc/, both in the
        # editable checkout (mlcflow/automation) and in site-packages once
        # installed, since mlc/action.py always lives one level under the
        # package root that automation/ is a sibling of.
        pkg_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        target_folder = os.path.join(pkg_root, 'automation', target)
        return target_folder if os.path.isdir(target_folder) else None

    def find_target_folder(self, target):
        # Prefer the automation engine bundled with mlcflow itself; fall back
        # to scanning registered repos for a custom/external 'automation'
        # folder (e.g. a dev override) if the bundled one isn't present.
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

        temp_repo = os.environ.get('MLC_REPOS', '').strip()
        if temp_repo == '':
            self.repos_path = os.path.join(
                os.path.expanduser("~"), "MLC", "repos")
        else:
            self.repos_path = temp_repo

        mlc_local_repo_path = os.path.join(self.repos_path, 'local')

        mlc_local_repo_path_expanded = Path(
            mlc_local_repo_path).expanduser().resolve()

        if not os.path.exists(mlc_local_repo_path):
            os.makedirs(mlc_local_repo_path, exist_ok=True)

        if not os.path.isfile(os.path.join(mlc_local_repo_path, "meta.yaml")):
            local_repo_meta = {
                "alias": "local",
                "name": "MLC local repository",
                "uid": utils.get_new_uid()['uid']}
            with open(os.path.join(mlc_local_repo_path, "meta.yaml"), "w") as json_file:
                json.dump(local_repo_meta, json_file, indent=4)

        repo_json_path = os.path.join(self.repos_path, "repos.json")
        if not os.path.exists(repo_json_path):
            with open(repo_json_path, 'w') as f:
                json.dump([str(mlc_local_repo_path_expanded)], f, indent=2)
                logger.info(
                    f"Created repos.json in {os.path.dirname(self.repos_path)} and initialised with local cache folder path: {mlc_local_repo_path}")

        self.local_cache_path = os.path.join(mlc_local_repo_path, "cache")
        if not os.path.exists(self.local_cache_path):
            os.makedirs(self.local_cache_path, exist_ok=True)

        # Pip-sourced script-content repos are prepended (processed first),
        # so git-cloned repos loaded below are processed last and win any
        # script-uid conflicts - pip is a second, lower-trust source for now
        # (see mlcflow-pip-script-packages-proposal.pptx, Phase 1).
        self.repos = discover_pip_script_repos(
            self.repos_path) + self.load_repos_and_meta()
        # logger.info(f"In Action class: {self.repos_path}")
        self._index = None

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
        if self._is_pip_sourced_repo(repo):
            return {
                'return': 1,
                'error': f"""Repo '{repo.meta.get('alias')}' is sourced from an installed pip package (read-only) - cannot add items to it. Use a git-cloned repo or the local repo instead."""}
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

            if self._is_pip_sourced_repo(getattr(result, 'repo', None)):
                logger.warning(
                    f"Skipping removal of {item_path}: sourced from an "
                    f"installed pip package (read-only), not a git-cloned repo.")
                continue

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

            # Match by alias first - the on-disk directory basename doesn't
            # always match the repo's alias (e.g. a pip-sourced repo's
            # site-packages directory "mlc_scripts_content" vs its
            # distribution-name alias "mlc-scripts"). Fall back to basename
            # matching for repos with no alias set.
            target_repo = next(
                (k for k in self.repos
                 if k.meta.get('alias') == target_repo_name
                 or os.path.basename(k.path) == target_repo_name), None)

            if target_repo is None:
                return {'return': 1, 'error': f"""The target repo {target_repo_name} is not registered in MLC. Either register in MLC by cloning from Git through command `mlc pull repo` or create repo using `mlc add repo` command and try to rerun the command again"""}
            target_repo_path = target_repo.path
            target_item_name = target_split[1].strip()
        else:
            target_repo = result.repo
            target_repo_path = result.repo.path
            target_item_name = target_split[0].strip()

        if self._is_pip_sourced_repo(target_repo):
            return {
                'return': 1,
                'error': f"""Target repo '{getattr(target_repo, 'meta', {}).get('alias')}' is sourced from an installed pip package (read-only) - cannot copy/move items into it."""}

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
if not default_parent:
    default_parent = Action()


def access(i):
    from .action_factory import get_action

    action = i['action']
    target = i.get('target', i.get('automation'))
    action_class = get_action(target, default_parent)
    r = action_class.access(i)
    return r
