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
        logger.info(f"Saving modified times to {self.modified_times_file}")
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

    def get_script_mtime(self,folder):
        # logger.info(f"Getting latest modified time for folder: {folder}")
        latest = 0
        for root, _, files in os.walk(folder):
            for f in files:
                fp = os.path.join(root, f)
                t = os.path.getmtime(fp)
                if t > latest:
                    latest = t
        return latest
    
    def build_index(self):
        """
        Build shared indices for script, cache, and experiment folders across all repositories.
        
        Returns:
            None
        """

        # track all currently detected script paths
        current_script_keys = set()
        changed = False

        #for repo in os.listdir(self.repos_path):
        for repo in self.repos:
            repo_path = repo.path #os.path.join(self.repos_path, repo)
            if not os.path.isdir(repo_path):
                continue

            # Filter for relevant directories in the repo
            for folder_type in ["script", "cache", "experiment"]:
                folder_path = os.path.join(repo_path, folder_type)
                if not os.path.isdir(folder_path):
                    continue

                # Process each automation directory
                for automation_dir in os.listdir(folder_path):
                    automation_path = os.path.join(folder_path, automation_dir)
                    if not os.path.isdir(automation_path):
                        continue

                    # Check for configuration files (meta.yaml or meta.json)
                    for config_file in ["meta.yaml", "meta.json"]:
                        config_path = os.path.join(automation_path, config_file)
                        if os.path.isfile(config_path):   
                            key = f"{repo_path}/{folder_type}/{automation_dir}"
                            current_script_keys.add(key)
                            mtime = self.get_script_mtime(automation_path)

                            old = self.modified_times.get(key)
                            old_mtime = old["mtime"] if isinstance(old, dict) else old

                            # skip if unchanged
                            if old_mtime == mtime:
                                continue

                            # update mtime
                            logger.debug("Script is modified, index getting updated")

                            self.modified_times[key] = {
                                "mtime": mtime,
                                "date_time": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                            }
                            changed = True
                            # script changed, so reindex
                            self._process_config_file(config_path, folder_type, automation_path, repo)
                            break  # Only process one config file per automation_dir

        # remove deleted scripts
        old_keys = set(self.modified_times.keys())
        deleted_keys = old_keys - current_script_keys
        for key in deleted_keys:
            del self.modified_times[key]
            self._remove_index_entry(key)
            changed = True

        if changed:
            self._save_modified_times()
            self._save_indices()
            logger.info("Index updated (changes detected).")
        else:
            logger.debug("Index unchanged (no changes detected).")

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
        for cf in ("meta.yaml", "meta.json"):
            p = os.path.join(folder_path, cf)
            if os.path.isfile(p):
                config_file = p
                break

        if not config_file:
            return

        try:
            # Determine the file type based on the extension
            if config_file.endswith(".yaml") or config_file.endswith(".yml"):
                with open(config_file, "r") as f:
                    data = yaml.safe_load(f)
            elif config_file.endswith(".json"):
                with open(config_file, "r") as f:
                    data = json.load(f)
            else:
                logger.info(f"Skipping {config_file}: Unsupported file format.")
                return

            # Extract necessary fields
            unique_id = data.get("uid")
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
                logger.info(f"Skipping {config_file}: Missing 'uid' field.")

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
