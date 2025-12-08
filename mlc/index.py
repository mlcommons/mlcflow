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
        #logger.info(repos)

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

    def _load_modified_times(self):
        """
        Load stored mtimes to check for changes in scripts.
        """
        if os.path.exists(self.modified_times_file):
            try:
                # logger.info(f"Loading modified times from {self.modified_times_file}")
                with open(self.modified_times_file, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_modified_times(self):
        """
        Save updated mtimes in modified_times json file.
        """
        logger.debug(f"Saving modified times to {self.modified_times_file}")
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

                except Exception:
                    pass   # fall back to empty index

    def add(self, meta, folder_type, path, repo):
        if not repo:
            logger.error(f"Repo for index add for {path} is none")
            return

        unique_id = meta['uid']
        alias = meta['alias']
        tags = meta['tags']
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
        # logger.debug(f"Getting latest modified time for file: {file}")
        latest = 0
        t = os.path.getmtime(file)
        if t > latest:
            latest = t
            logger.debug(f"Latest modified time updated to: {latest}")
        # logger.debug("No changes in modified time detected.")
        return latest
    
    def build_index(self):
        """
        Build shared indices for script, cache, and experiment folders across all repositories.
        
        Returns:
            None
        """

        # track all currently detected item paths
        current_item_keys = set()
        changed = False
        repos_changed = False
        
        # load existing modified times
        self.modified_times = self._load_modified_times()

        index_json_path = os.path.join(self.repos_path, "index_script.json")

        rebuild_index = False

        #file does not exist, rebuild
        if not os.path.exists(index_json_path):
            logger.warning("index_script.json missing. Forcing full index rebuild...")
            logger.debug("Resetting modified_times...")
            self.modified_times = {}
            self._save_modified_times()
        else:
            logger.debug("index_script.json exists. Skipping forced rebuild.")

        #check repos.json mtime
        repos_json_path = os.path.join(self.repos_path, "repos.json")
        repos_mtime = os.path.getmtime(repos_json_path)

        key = f"{repos_json_path}"
        old = self.modified_times.get(key)
        repo_old_mtime = old["mtime"] if isinstance(old, dict) else old

        logger.debug(f"Current repos.json mtime: {repos_mtime}")
        logger.debug(f"Old repos.json mtime: {repo_old_mtime}")
        current_item_keys.add(key)

        # if changed, reset indexes
        if repo_old_mtime is None or repo_old_mtime != repos_mtime:
            logger.debug("repos.json modified. Clearing index ........")
            # reset indices
            self.indices = {key: [] for key in self.index_files.keys()}
            # record repo mtime
            self.modified_times[key] = {
                "mtime": repos_mtime,
                "date_time": datetime.fromtimestamp(repos_mtime).strftime("%Y-%m-%d %H:%M:%S")
            }
            # clear modified times except for repos.json
            self.modified_times = {key: self.modified_times[key]}
            self._save_indices()
            self._save_modified_times()
            repos_changed = True
        else:
            logger.debug("Repos.json not modified")

        for repo in self.repos:
            repo_path = repo.path #os.path.join(self.repos_path, repo)
            if not os.path.isdir(repo_path):
                continue
            logger.debug(f"Checking repository: {repo_path}")
            # Filter for relevant directories in the repo
            for folder_type in ["script", "cache", "experiment"]:
                logger.debug(f"Checking folder type: {folder_type}")
                folder_path = os.path.join(repo_path, folder_type)
                if not os.path.isdir(folder_path):
                    continue

                # Process each automation directory
                for automation_dir in os.listdir(folder_path):
                    # logger.debug(f"Checking automation directory: {automation_dir}")
                    automation_path = os.path.join(folder_path, automation_dir)
                    if not os.path.isdir(automation_path):
                        logger.debug(f"Skipping non-directory automation path: {automation_path}")
                        continue
                    
                    yaml_path = os.path.join(automation_path, "meta.yaml")
                    json_path = os.path.join(automation_path, "meta.json")

                    if os.path.isfile(yaml_path):
                        # logger.debug(f"Found YAML config file: {yaml_path}")
                        config_path = yaml_path
                    elif os.path.isfile(json_path):
                        # logger.debug(f"Found JSON config file: {json_path}")
                        config_path = json_path
                    else:
                        logger.debug(f"No config file found in {automation_path}, skipping")
                        if automation_dir in self.modified_times:
                            del self.modified_times[automation_dir]
                        if any(automation_dir in item["path"] for item in self.indices[folder_type]):
                            logger.debug(f"Removed index entry (if it exists) for {folder_type} : {automation_dir}")
                            self._remove_index_entry(automation_path)
                        self._save_indices()
                        continue
                    current_item_keys.add(config_path)
                    mtime = self.get_item_mtime(config_path)

                    old = self.modified_times.get(config_path)
                    old_mtime = old["mtime"] if isinstance(old, dict) else old

                    # skip if unchanged
                    if old_mtime == mtime and repos_changed != 1:
                        # logger.debug(f"No changes detected for {config_path}, skipping reindexing.")
                        continue
                    if(old_mtime is None):
                        logger.debug(f"New config file detected: {config_path}. Adding to index.")
                    # update mtime
                    logger.debug(f"{config_path} is modified, index getting updated")
                    if config_path not in self.modified_times:
                        logger.debug(f"*************{config_path} not found in modified_times; creating new entry***************")

                    self.modified_times[config_path] = {
                        "mtime": mtime,
                        "date_time": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                    }
                    logger.debug(f"Modified time for {config_path} updated to {mtime}")
                    changed = True
                    # meta file changed, so reindex
                    self._process_config_file(config_path, folder_type, automation_path, repo)

        # remove deleted scripts
        old_keys = set(self.modified_times.keys())
        deleted_keys = old_keys - current_item_keys
        for key in deleted_keys:
            logger.warning(f"Detected deleted item, removing entry form modified times: {key}")
            del self.modified_times[key]
            folder_key = os.path.dirname(key)
            logger.warning(f"Removing index entry for folder: {folder_key}")
            self._remove_index_entry(folder_key)
            changed = True
        logger.debug(f"Deleted keys removed from modified times and indices: {deleted_keys}")

        if changed:
            logger.debug("Changes detected, saving updated index and modified times.")
            self._save_modified_times()
            self._save_indices()
            logger.debug("**************Index updated (changes detected).*************************")
        else:
            logger.debug("**************Index unchanged (no changes detected).********************")

    def _remove_index_entry(self, key):
        logger.debug(f"Removing index entry for {key}")
        for ft in self.indices:
            self.indices[ft] = [
                item for item in self.indices[ft]
                if key not in item["path"]
            ]

    def _delete_by_uid(self, folder_type, uid, alias):
        """
        Delete old index entry using UID (prevents duplicates).
        """
        logger.debug(f"Deleting and updating index entry for the script {alias} with UID {uid}")
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
            if unique_id:
                self._delete_by_uid(folder_type, unique_id, alias)
                self.indices[folder_type].append({
                    "uid": unique_id,
                    "tags": tags,
                    "alias": alias,
                    "path": folder_path,
                    "repo": repo
                })
            else:
                logger.warning(f"Skipping {config_file}: Missing 'uid' field.")

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
                logger.debug(f"Shared index for {folder_type} saved to {output_file}.")
            except Exception as e:
                logger.error(f"Error saving shared index for {folder_type}: {e}")
