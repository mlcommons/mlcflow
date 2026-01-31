from .logger import logger
import os
import json
import yaml
from .repo import Repo
from datetime import datetime

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Repo):
            # Customize how to serialize the Repo object
            return {
                "path": obj.path,
                "meta": obj.meta,
            }
        # For other unknown types, use the default behavior
        return super().default(obj)


class Index:
    def __init__(self, repos_path, repos):
        """
        Initialize the Index class.
        
        Args:
            repos_path (str): Path to the base folder containing repositories.
        """
        self.repos_path = repos_path
        self.repos = repos

        logger.debug(f"Repos path for Index: {self.repos_path}")
        self.index_files = {
            "script": os.path.join(repos_path, "index_script.json"),
            "cache": os.path.join(repos_path, "index_cache.json"),
            "experiment": os.path.join(repos_path, "index_experiment.json")
        }
        self.indices = {key: [] for key in self.index_files.keys()}
        self.modified_times_file = os.path.join(repos_path, "modified_times.json")
        self.modified_times = self._load_modified_times()
        self._load_existing_index()
        self.build_index()

    def _get_stored_mtime(self, key):
        """
        Helper method to safely extract mtime from stored data.
        Handles both old format (direct mtime) and new format (dict with mtime key).
        """
        old = self.modified_times.get(key)
        if old is None:
            return None
        return old["mtime"] if isinstance(old, dict) else old

    def _load_modified_times(self):
        """
        Load stored mtimes to check for changes in scripts.
        """
        if os.path.exists(self.modified_times_file):
            try:
                # logger.info(f"Loading modified times from {self.modified_times_file}")
                with open(self.modified_times_file, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to load modified times: {e}")
                return {}
        return {}

    def _save_modified_times(self):
        """
        Save updated mtimes in modified_times json file.
        """
        #logger.debug(f"Saving modified times to {self.modified_times_file}")
        with open(self.modified_times_file, "w") as f:
            json.dump(self.modified_times, f, indent=4)

    def _load_existing_index(self):
        """
        Load previously saved index to allow incremental updates.
        """
        for folder_type, file_path in self.index_files.items():
            if os.path.exists(file_path):
                try:
                    # logger.info(f"Loading existing index for {folder_type}")
                    with open(file_path, "r") as f:
                        self.indices[folder_type] = json.load(f)
                    # Convert repo dicts back into Repo objects
                    for item in self.indices[folder_type]:
                        if isinstance(item.get("repo"), dict):
                            item["repo"] = Repo(**item["repo"])

                except (json.JSONDecodeError, IOError, KeyError, TypeError) as e:
                    logger.warning(f"Failed to load index for {folder_type}: {e}")
                    pass   # fall back to empty index

    def add(self, meta, folder_type, path, repo):
        if not repo:
            logger.error(f"Repo for index add for {path} is none")
            return

        unique_id = meta['uid']
        alias = meta['alias']
        tags = meta['tags']
        
        index = self.get_index(folder_type, unique_id)

        if index == -1:
            self.indices[folder_type].append({
                    "uid": unique_id,
                    "tags": tags,
                    "alias": alias,
                    "path": path,
                    "repo": repo
                })
            self._save_indices()

    def get_index(self, folder_type, uid):
        for index in range(len(self.indices[folder_type])):
            if self.indices[folder_type][index]["uid"] == uid:
                return index
        return -1

    def update(self, meta, folder_type, path, repo):
        uid = meta['uid']
        alias = meta['alias']
        tags = meta['tags']
        index = self.get_index(folder_type, uid)
        if index == -1: #add it
            self.add(meta, folder_type, path, repo)
            logger.debug(f"Index update failed, new index created for {uid}")
        else:
            self.indices[folder_type][index] = {
                    "uid": uid,
                    "tags": tags,
                    "alias": alias,
                    "path": path,
                    "repo": repo
                }
        self._save_indices()

    def rm(self, meta, folder_type, path):
        uid = meta['uid']
        index = self.get_index(folder_type, uid)
        if index == -1: 
            logger.warning(f"Index is not having the {folder_type} item {path}")
        else:
            del(self.indices[folder_type][index])
        self._save_indices()

    def get_item_mtime(self,file):
        latest = 0
        t = os.path.getmtime(file)
        if t > latest:
            latest = t
        return latest

    def _index_single_repo(self, repo, repos_changed=False, current_item_keys=None):
        repo_path = repo.path
        if not os.path.isdir(repo_path):
            return False

        changed = False

        for folder_type in ["script", "cache", "experiment"]:
            folder_path = os.path.join(repo_path, folder_type)
            if not os.path.isdir(folder_path):
                continue

            for automation_dir in os.listdir(folder_path):
                automation_path = os.path.join(folder_path, automation_dir)
                if not os.path.isdir(automation_path):
                    continue

                yaml_path = os.path.join(automation_path, "meta.yaml")
                json_path = os.path.join(automation_path, "meta.json")

                if os.path.isfile(yaml_path):
                    config_path = yaml_path
                elif os.path.isfile(json_path):
                    config_path = json_path
                else:
                    # No config file found, remove from index if exists
                    delete_flag = False
                    
                    # Check and remove both possible config paths from modified_times
                    for config_name in ["meta.yaml", "meta.json"]:
                        config_key = os.path.join(automation_path, config_name)
                        if config_key in self.modified_times:
                            del self.modified_times[config_key]
                            delete_flag = True
                    
                    # Use exact path matching instead of substring
                    if any(item["path"] == automation_path for item in self.indices[folder_type]):
                        logger.debug(f"Removed index entry (if it exists) for {folder_type} : {automation_dir}")
                        delete_flag = True
                        self._remove_index_entry(automation_path)
                    
                    if delete_flag:
                        self._save_indices()
                    continue
                if current_item_keys is not None:
                    current_item_keys.add(config_path)
                mtime = self.get_item_mtime(config_path)
                old_mtime = self._get_stored_mtime(config_path)

                # skip if unchanged
                if old_mtime == mtime and not repos_changed:
                    continue

                self.modified_times[config_path] = {
                    "mtime": mtime,
                    "date_time": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                }
                
                # meta file changed, so reindex
                self._process_config_file(config_path, folder_type, automation_path, repo)
                changed = True
        
        return changed

    def build_index(self):
        """
        Build shared indices for script, cache, and experiment folders across all repositories.
        
        Returns:
            None
        """

        # track all currently detected item paths
        current_item_keys = set()
        changed = False
        force_rebuild = False

        # load modified times
        self.modified_times = self._load_modified_times()

        # if missing index file, then force full rebuild
        index_json_path = os.path.join(self.repos_path, "index_script.json")
        if not os.path.exists(index_json_path):
            logger.warning("index_script.json missing. Forcing full index rebuild...")
            self.modified_times = {}
            self.indices = {k: [] for k in self.index_files.keys()}
            force_rebuild = True
           

        # index each repo
        for repo in self.repos:
            repo_changed = self._index_single_repo(repo, force_rebuild, current_item_keys)
            if repo_changed:
                changed = True

        # remove deleted scripts
        deleted_keys = set(self.modified_times) - current_item_keys
        for key in deleted_keys:
            logger.warning(f"Detected deleted item, removing entry from modified times: {key}")
            del self.modified_times[key]
            folder_key = os.path.dirname(key)
            #logger.warning(f"Removing index entry for folder: {folder_key}")
            self._remove_index_entry(folder_key)
            changed = True
        if deleted_keys:
            logger.debug(f"Deleted keys removed from modified times and indices: {deleted_keys}")

        if force_rebuild or changed:
            logger.debug("Changes detected, saving updated index and modified times.")
            self._save_modified_times()
            self._save_indices()

    def _remove_index_entry(self, key):
        logger.debug(f"Removing index entry for {key}")
        # Normalize paths for comparison
        normalized_key = os.path.normpath(key)
        for ft in self.indices:
            self.indices[ft] = [
                item for item in self.indices[ft]
                if os.path.normpath(item["path"]) != normalized_key
            ]

    def _delete_by_uid(self, folder_type, uid, alias):
        """
        Delete old index entry using UID (prevents duplicates).
        """
        #logger.debug(f"Deleting and updating index entry for the script {alias} with UID {uid}")
        self.indices[folder_type] = [
            item for item in self.indices[folder_type]
            if item["uid"] != uid
        ]

    def _process_config_file(self, config_file, folder_type, folder_path, repo):
        """
        Process a single configuration file (meta.json or meta.yaml) and add its data to the corresponding index.

        Args:
            config_file (str): Path to the configuration file.
            folder_type (str): Type of folder (script, cache, or experiment).
            folder_path (str): Path to the folder containing the configuration file.

        Returns:
            None
        """
        if config_file is None:
            logger.debug(f"No meta file in {folder_path}, skipping")
            return

        try:
            # Determine the file type based on the extension
            if config_file.endswith(".yaml") or config_file.endswith(".yml"):
                with open(config_file, "r") as f:
                    data = yaml.safe_load(f) or {}
            elif config_file.endswith(".json"):
                with open(config_file, "r") as f:
                    data = json.load(f) or {}
            else:
                logger.warning(f"Skipping {config_file}: Unsupported file format.")
                return
            
            if not isinstance(data, dict):
                logger.warning(f"Skipping {config_file}: Invalid or empty meta")
                return
            # Extract necessary fields
            unique_id = data.get("uid")
            if not unique_id:
                logger.warning(f"Skipping {config_file}: missing uid")
                return
            tags = data.get("tags", [])
            alias = data.get("alias", None)

            # Validate and add to indices
            self._delete_by_uid(folder_type, unique_id, alias)
            self.indices[folder_type].append({
                "uid": unique_id,
                "tags": tags,
                "alias": alias,
                "path": folder_path,
                "repo": repo
            })

        except Exception as e:
            logger.error(f"Error processing {config_file}: {e}")


    def _save_indices(self):
        """
        Save the indices to JSON files.
        
        Returns:
            None
        """
        #logger.info(self.indices)
        for folder_type, index_data in self.indices.items():
            output_file = self.index_files[folder_type]
            try:
                with open(output_file, "w") as f:
                    json.dump(index_data, f, indent=4, cls=CustomJSONEncoder)
                #logger.debug(f"Shared index for {folder_type} saved to {output_file}.")
            except Exception as e:
                logger.error(f"Error saving shared index for {folder_type}: {e}")


    def add_repo(self, repo):
        """
        Incrementally index a newly registered repository.
        """
        changed = self._index_single_repo(repo, repos_changed=True)

        if changed:
            self._save_indices()
            self._save_modified_times()


    def remove_repo_from_index(self, repo_path):
        """
        Remove all index entries and modified times belonging to a repo.
        Called when a repo is unregistered from repos.json.
        """

        logger.info(f"Removing repo from index: {repo_path}")
        changed = False

        # remove index entries
        for folder_type in self.indices:
            before = len(self.indices[folder_type])
            self.indices[folder_type] = [
                item for item in self.indices[folder_type]
                if not item["path"].startswith(repo_path)
            ]
            if len(self.indices[folder_type]) != before:
                changed = True

        # remove modified times
        keys_to_delete = [
            k for k in self.modified_times
            if k.startswith(repo_path)
        ]

        for k in keys_to_delete:
            del self.modified_times[k]
            changed = True

        if changed:
            self._save_indices()
            self._save_modified_times()