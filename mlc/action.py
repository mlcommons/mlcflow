import os
import logging
import json
import yaml
import logging
import re
import shutil
from pathlib import Path

from .logger import logger, setup_logging

from . import utils
from .index import Index
from .repo import Repo
from .item import Item

# Base class for actions
class Action:
    repos_path = None
    cfg = None
    action_type = None
    logger = None
    local_repo = None
    current_repo_path = None
    #mlc = None
    repos = [] #list of Repo objects

    # Main access function to simulate a Python interface for CLI
    def access(self, options):
        """
        Access function to simulate CLI actions in Python.

        Args:
        options (dict): Dictionary containing action and relevant parameters.
        """
        from .action_factory import get_action

        #logger.info(f"options in access = {options}") 
        
        action_name = options.get('action')
        if not action_name:
            return {'return': 1, 'error': "'action' key is required in options"}
        #logger.info(f"options = {options}")

        action_target = options.get('target')
        if not action_target:
            action_target = options.get('automation', 'script')  # Default to script if not provided
        action_target_split = action_target.split(",")
        action_target = action_target_split[0]

        action = get_action(action_target, self.parent if self.parent else self)

        if action and hasattr(action, action_name):
            # Find the method and call it with the options
            method = getattr(action, action_name)
            result = method(options)
            #logger.info(f"result ={result}")
            return result
        else:
            return {'return': 1, 'error': f"'{action_name}' action is not supported for {action_target}."}
        return {'return': 0}

    def find_target_folder(self, target):
        # Traverse through each repo to find the first 'target' folder inside an 'automation' folder
        for repo in self.repos:
            repo_path = repo.path
            if os.path.isdir(repo_path):
                automation_folder = os.path.join(repo_path, 'automation')
                
                if os.path.isdir(automation_folder):
                    # Check if there's a 'script' folder inside the 'automation' folder
                    target_folder = os.path.join(automation_folder, target)
                    if os.path.isdir(target_folder):
                        return target_folder
        return None

    def load_repos_and_meta(self):
        repos_list = []
        repos_file_path = os.path.join(self.repos_path, 'repos.json')

        # Read the JSON file line by line
        try:
            # Load and parse the JSON file containing the list of repository paths
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
                logger.warning(f"""Warning: {repo_path} not found. Considering it as a corrupt entry and deleting automatically...""")
                logger.warning(f"Deleting the {meta_yaml_path} entry from repos.json")
                from .repo_action import rm_repo
                res = rm_repo(repo_path, os.path.join(self.repos_path, 'repos.json'), True)

                if res["return"] > 0:
                    return res
                continue

            if is_curdir_inside_path(repo_path):
                self.current_repo_path = repo_path
            repo_path = repo_path.strip()  # Remove any extra whitespace or newlines

           # Skip empty lines
            if not repo_path:
                continue

            meta_yaml_path = os.path.join(repo_path, "meta.yaml")

            # Check if meta.yaml exists
            if not os.path.isfile(meta_yaml_path):
                logger.warning(f"{meta_yaml_path} not found. Could be due to accidental deletion of meta.yaml. Try to stash the changes or reclone by doing `rm repo` and `pull repo`. Skipping...")
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
    

    def __init__(self):        
        setup_logging(log_path=os.getcwd(),log_file='mlc-log.txt')
        self.logger = logger

        temp_repo = os.environ.get('MLC_REPOS','').strip()
        if temp_repo == '':
            self.repos_path = os.path.join(os.path.expanduser("~"), "MLC", "repos")
        else:
            self.repos_path = temp_repo

        mlc_local_repo_path = os.path.join(self.repos_path, 'local')
        
        mlc_local_repo_path_expanded = Path(mlc_local_repo_path).expanduser().resolve()

        if not os.path.exists(mlc_local_repo_path):
            os.makedirs(mlc_local_repo_path, exist_ok=True)
        
        if not os.path.isfile(os.path.join(mlc_local_repo_path, "meta.yaml")):
            local_repo_meta = {"alias": "local", "name": "MLC local repository", "uid": utils.get_new_uid()['uid']}
            with open(os.path.join(mlc_local_repo_path, "meta.yaml"), "w") as json_file:
                json.dump(local_repo_meta, json_file, indent=4)
        
        repo_json_path = os.path.join(self.repos_path, "repos.json")
        if not os.path.exists(repo_json_path):
            with open(repo_json_path, 'w') as f:
                json.dump([str(mlc_local_repo_path_expanded)], f, indent=2)
                logger.info(f"Created repos.json in {os.path.dirname(self.repos_path)} and initialised with local cache folder path: {mlc_local_repo_path}")

        self.local_cache_path = os.path.join(mlc_local_repo_path, "cache")
        if not os.path.exists(self.local_cache_path):
            os.makedirs(self.local_cache_path, exist_ok=True)

        self.repos = self.load_repos_and_meta()
        #logger.info(f"In Action class: {self.repos_path}")
        self.index = Index(self.repos_path, self.repos)


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
            return {'return': 1, 'error': f"""The given repo {item_repo} is not registered in MLC"""}

        # Determine paths and metadata format
        repo = res["list"][0]
        repo_path = repo.path
        
        target_name = i.get('target_name', self.action_type)
        target_path = os.path.join(repo_path, target_name)
        if target_name == "cache":
            folder_name = f"""{i["script_alias"]}_{item_name or item_id[:8]}""" if i.get("script_alias") else item_name or item_id
        else:
            folder_name = item_name or item_id

        item_path = os.path.join(target_path, folder_name)

        if os.path.exists(item_path):
            return {"return": 1, "error": f"""Item exists at {item_path}"""}

        # Create item directory if it does not exist
        os.makedirs(item_path)

        res = self.save_new_meta(i, item_id, item_name, target_name, item_path, repo)
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
        item = i.get("item",i.get('artifact', i.get('details')))
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
        # Setting force remove to true would lead to removal of assets without user prompt
        force_remove = True if i.get('f') else False

        if item_name:
            inp['alias'] = item_name
            inp['folder_name'] = item_name #we dont know if the user gave the alias or the folder name, we first check for alias and then the folder name
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
                logger.warning(f"{target_name} is empty! nothing to be cleared!")
                return {"return": 0}
            else:
                return {'return': 16, 'error': f'No {target_name} found for {inp}'}
        elif len(res['list']) > 1:
            logger.info(f"More than 1 {target_name} found for {inp}:")
            if not i.get('all'):
                for idx, item in enumerate(res["list"]):
                    logger.info(f"{idx}. Path: {item.path}, Meta: {item.meta}")

                if not force_remove:
                    user_choice = input("Would you like to proceed with all items? (yes/no): ").strip().lower()
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
                    user_choice = input(f"Confirm to delete {target_name} item: {item_path}? (yes/no): ").strip().lower()
                    if user_choice not in ['yes', 'y']:
                        continue
                    else:
                        shutil.rmtree(item_path)

                logger.info(f"{target_name} item: {item_path} has been successfully removed")

            self.index.rm(item_meta, target_name, item_path)
        
        return {
            "return": 0,
            "message": f"Item {item_path} successfully removed",
        }

    def save_new_meta(self, i, item_id, item_name, target_name, item_path, repo):
        # Prepare metadata
        item_meta = i.get('meta', {})
        item_meta.update({
            "alias": item_name,
            "uid": item_id,
        })

        # Process tags
        tags = i.get("tags", "").split(",") if i.get("tags") else item_meta.get("tags", [])
        new_tags = i.get("new_tags", "").split(",") if i.get("new_tags") else []

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
    
        self.index.add(item_meta, target_name, item_path, repo)
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
        target_name = i.get('target_name',"cache")
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
            if res['return'] > 0 :
                return res
            found_items.append(Item(res['path'], res['repo']))
            #return {'return': 0, 'message': 'No items found for the given tags.'}

        # Step 2: Prepare to update tags
        search_tags = i.get("search_tags", [])

        new_tags = set(search_tags)
        if len(found_items) > 1:
            # Step 3: Ask user for confirmation if multiple items are found
            user_input = input(f"{len(found_items)} items found. Do you want to update all? (yes/no): ").strip().lower()
            if user_input not in ['yes', 'y']:
                return {'return': 0, 'message': 'Update operation canceled by the user.'}

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
                if res['return']> 0:
                    return res
                meta = res['meta']
            if i.get('replace_lists') and i.get("tags"):
                meta["tags"] = i["tags"].split(",")
            else:
                current_tags = set(meta.get("tags", []))
                updated_tags = current_tags.union(new_tags)
                meta["tags"] = list(updated_tags)
            utils.merge_dicts({"dict1": meta, "dict2": new_meta, "append_lists": True, "append_unique":True})
        
            # Save the updated meta back to the item
            item.meta = meta
            save_result = utils.save_json(item_meta_path, meta=meta)
            self.index.update(meta, target_name, item.path, item.repo)

        return {'return': 0, 'message': f"Tags updated successfully for {len(found_items)} item(s).", 'list': found_items }



    def cp(self, run_args):
        action_target = run_args['target']
        if action_target != "script":
            return {"return": 1, "error": f"The {action_target} target is not currently supported for mv/cp actions"}
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
            inp['folder_name'] = src_item #we dont know if the user gave the alias or the folder name, we first check for alias and then the folder name
        
            if utils.is_uid(src_item):
                inp['uid'] = src_item
            src_id = src_item
        else:
            #src_tags must be there
            if not run_args.get("src_tags"):
                return {'return': 1, 'error': 'Either "src" or "src_tags" must be provided as an input for cp method'}
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
                choice = input("Select the correct one (enter number, default=1): ").strip()
                if choice == "":
                    choice = 1
                try:
                    choice = int(choice) - 1
                    if 0 <= choice < len(res['list']):
                        break
                    else:
                        print("Invalid selection. Please enter a number from the list.")
                except ValueError:
                    print("Invalid input. Please enter a number.")

        result = res['list'][choice]
        src_item_path = result.path
        src_item_meta = result.meta

        target_item = run_args['dest']
        target_split = target_item.split(":")

        if len(target_split) > 1:
            target_repo = target_split[0].strip()
            if target_repo == ".":
                if not self.current_repo_path:
                    return {'return': 1, 'error': f"""Current directory is not inside a registered MLC repo and so using ".:" is not valid"""}
                target_repo = self.current_repo_path
            else:
                if not any(os.path.basename(repodata.path) == target_repo for repodata in self.repos):
                    return {'return': 1, 'error': f"""The target repo {target_repo} is not registered in MLC. Either register in MLC by cloning from Git through command `mlc pull repo` or create repo using `mlc add repo` command and try to rerun the command again"""}
            target_repo_path = os.path.join(self.repos_path, target_repo)
            target_repo = Repo(target_repo_path)
            target_item_name = target_split[1].strip()
        else:
            target_repo = result.repo
            target_repo_path = result.repo.path
            target_item_name = target_split[0].strip()


        target_item_path = os.path.join(target_repo_path, action_target, target_item_name)
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

        res = self.save_new_meta(ii, item_id, target_item_name, action_target, target_item_path, target_repo)

        dest_item = Item(target_item_path, target_repo)
        
        if res['return'] > 0:
            return res
        logger.info(f"{action_target} {src_item_path} copied to {target_item_path}")

        return {'return': 0, 'src': result, 'dest': dest_item}

    def copy_item(self, source_path, destination_path):
        try:
            # Copy the source folder to the destination
            shutil.copytree(source_path, destination_path)
            logger.info(f"Folder successfully copied from {source_path} to {destination_path}")
        except FileExistsError:
            return {'return': 1, 'error': f"Destination folder {destination_path} already exists."}
        except FileNotFoundError:
            return {'return': 1, 'error': f"Source folder {source_path} not found"}
        except Exception as e:
            return {'return': 1, 'error': f"An error occurred {e}"}

        return {'return': 0}

    def mv(self, run_args):
        target_name = run_args['target']
        if target_name != "script":
            return {"return": 1, "error": f"The {target_name} target is not currently supported for mv/cp actions"}
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
        
        #Put the src uid to the destination path
        dest.meta['uid'] = src.meta['uid']
        dest._save_meta()
        self.index.update(dest.meta, target_name, dest.path, dest.repo)
        logger.info(f"""Item with uid {dest.meta['uid']} successfully moved from {src.path} to {dest.path}""")

        return {'return': 0, 'src': src, 'dest': dest}

    def search(self, i):
        indices = self.index.indices
        target = i.get('target_name', self.action_type)
        target_index = indices.get(target)
        result = []
        uid = i.get("uid")
        alias = i.get("alias")
        item_repo = i.get('item_repo')
        fetch_all = True if i.get('fetch_all') else False

        # For targets like cache, sometimes user would need to clear the entire cache folder present in the system
        # this helps to fetch entire data pertaining to particular target
        if fetch_all:
            for res in target_index:
                result.append(Item(res['path'], res['repo']))
            return {'return': 0, 'list': result}

        if not uid and not alias and i.get('details'):
            details = i['details']
            details_split = details.split(",")
            if len(details_split) > 1:
                alias = details_split[0]
                uid = details_split[1]
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
                    if (res["uid"] == uid or (alias and res["alias"] == alias)) and (not item_repo or item_repo == res['repo']):
                        it = Item(res['path'], res['repo'])
                        result.append(it)
                        found = True
                if not found and folder_name:
                    for res in target_index:
                        if os.path.basename(res["path"]) == folder_name:
                            it = Item(res['path'], res['repo'])
                            #result.append(it)
            else:
                tags = i.get("tags")
                if tags:
                    tags_split = tags.split(",")
                else:
                    return {"return":1, "error": f"Tags are not specifeid for completing the specific action"}
                if target == "script":
                    non_variation_tags = [t for t in tags_split if not t.startswith("_")]
                    tags_to_match = non_variation_tags
                elif target =="cache":
                    tags_to_match = tags_split
                else:
                    return {'return': 1, 'error': f"""Target {target} not handled in mlc yet"""}
                n_tags_ = [p for p in tags_to_match if p.startswith("-")]
                n_tags = [p[1:] for p in n_tags_]
                p_tags = list(set(tags_to_match) - set(n_tags_))
                for res in target_index:
                    c_tags = res["tags"]
                    if set(p_tags).issubset(set(c_tags)) and set(n_tags).isdisjoint(set(c_tags)):
                        it = Item(res['path'], res['repo'])
                        result.append(it)
        return {'return': 0, 'list': result}

    find = search

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



