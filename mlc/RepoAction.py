from .action import Action
import os
import re
import subprocess
from . import utils
from .logger import logger

class RepoAction(Action):

    def __init__(self, parent=None):
        if parent is None:
            parent = default_parent
        #super().__init__(parent)
        self.parent = parent
        self.__dict__.update(vars(parent))


    def add(self, run_args):
        if not run_args['repo']:
            logger.error("The repository to be added is not specified")
            return {"return": 1, "error": "The repository to be added is not specified"}

        i_repo_path = run_args['repo'] #can be a path, forder_name or URL
        repo_folder_name = os.path.basename(i_repo_path)

        repo_path = os.path.join(self.repos_path, repo_folder_name)

        if os.path.exists(repo_path):
            return {'return': 1, "error": f"""Repo {run_args['repo']} already exists at {repo_path}"""}
        for repo in self.repos:
            if repo.path == i_repo_path:
                return {'return': 1, "error": f"""Repo {run_args['repo']} already exists at {repo_path}"""}

        if not os.path.exists(i_repo_path):
            #check if its an URL
            if utils.is_valid_url(i_repo_path):
                if "github.com" in i_repo_path:
                    res = self.github_url_to_user_repo_format(i_repo_path)
                    if res['return'] > 0:
                        return res
                    repo_folder_name = res['value']
                    repo_path = os.path.join(self.repos_path, repo_folder_name)

            os.makedirs(repo_path)
        else:
            repo_path = os.path.abspath(i_repo_path)
        logger.info(f"""New repo path: {repo_path}""")

        #check if it has MLC meta
        meta_file = os.path.join(repo_path, "meta.yaml")
        if not os.path.exists(meta_file):
            meta = {}
            meta['uid'] = utils.get_new_uid()['uid']
            meta['alias'] = repo_folder_name
            meta['git'] = True
            utils.save_yaml(meta_file, meta)
        else:
            meta = utils.read_yaml(meta_file)
        self.register_repo(repo_path, meta)

        return {'return': 0}

    def conflicting_repo(self, repo_meta):
        for repo_object in self.repos:
            if repo_object.meta.get('uid', '') == '':
                return {"return": 1, "error": f"UID is not present in file 'meta.yaml' in the repo path {repo_object.path}"}
            if repo_meta["uid"] == repo_object.meta.get('uid', ''):
                if repo_meta['path'] == repo_object.path:
                    return {"return": 1, "error": f"Same repo is already registered"}
                else:
                    return {"return": 1, "error": f"Conflicting with repo in the path {repo_object.path}", "conflicting_path": repo_object.path}
        return {"return": 0}
    
    def register_repo(self, repo_path, repo_meta):
    
        if repo_meta.get('deps'):
            for dep in repo_meta['deps']:
                self.pull_repo(dep['url'], branch=dep.get('branch'), checkout=dep.get('checkout'))

        # Get the path to the repos.json file in $HOME/MLC
        repos_file_path = os.path.join(self.repos_path, 'repos.json')

        with open(repos_file_path, 'r') as f:
            repos_list = json.load(f)
        
        if repo_path not in repos_list:
            repos_list.append(repo_path)
            logger.info(f"Added new repo path: {repo_path}")

        with open(repos_file_path, 'w') as f:
            json.dump(repos_list, f, indent=2)
            logger.info(f"Updated repos.json at {repos_file_path}")
        return {'return': 0}

    def unregister_repo(self, repo_path):
        logger.info(f"Unregistering the repo in path {repo_path}")
        repos_file_path = os.path.join(self.repos_path, 'repos.json')

        with open(repos_file_path, 'r') as f:
            repos_list = json.load(f)
        
        if repo_path in repos_list:
            repos_list.remove(repo_path)
            with open(repos_file_path, 'w') as f:
                json.dump(repos_list, f, indent=2)  
            logger.info(f"Path: {repo_path} has been removed.")
        else:
            logger.info(f"Path: {repo_path} not found in {repos_file_path}. Nothing to be unregistered!")
        return {'return': 0}

    def find(self, run_args):
        try:
            # Get repos_list using the existing method
            repos_list = self.load_repos_and_meta()
            if(run_args.get('item', run_args.get('artifact'))):
                repo = run_args.get('item', run_args.get('artifact'))
            else:
                repo = run_args.get('repo', run_args.get('item', run_args.get('artifact')))

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

            # Check if the repo is in the format of a repo UID (alphanumeric string)
            if self.is_uid(repo):
                repo_uid = repo
            if "," in repo:
                repo_split = repo.split(",")
                repo_name = repo_split[0]
                if len(repo_split) > 1:
                    repo_uid = repo_split[1]
            elif "@" in repo:
                repo_name = repo
            elif "github.com" in repo:
                result = self.github_url_to_user_repo_format(repo)
                if result["return"] == 0:
                    repo_name = result["value"]
                else:
                    return result
            
            # Check if repo_name exists in repos.json
            matched_repo_path = None
            for repo_obj in repos_list:
                if repo_name and repo_name == os.path.basename(repo_obj.path) :
                    matched_repo_path = repo_obj
                    break

            # Search through self.repos for matching repos
            lst = []
            for i in self.repos:
                if repo_uid and i.meta['uid'] == repo_uid:
                    lst.append(i)
                elif repo_name == i.meta['alias']:
                    lst.append(i)
                elif self.is_uid(repo) and not any(i.meta['uid'] == repo_uid for i in self.repos):
                    return {"return": 1, "error": f"No repository with UID: '{repo_uid}' was found"}
                elif "," in repo and not matched_repo_path and not any(i.meta['uid'] == repo_uid for i in self.repos) and not any(i.meta['alias'] == repo_name for i in self.repos):
                    return {"return": 1, "error": f"No repository with alias: '{repo_name}' and UID: '{repo_uid}' was found"}
                elif not matched_repo_path and not any(i.meta['alias'] == repo_name for i in self.repos) and not any(i.meta['uid'] == repo_uid for i in self.repos ):
                    return {"return": 1, "error": f"No repository with alias: '{repo_name}' was found"}
                
            # Append the matched repo path
            if(len(lst)==0):
                lst.append(matched_repo_path)
            
            return {'return': 0, 'list': lst}
        except Exception as e:
            # Return error message if any exception occurs
            return {"return": 1, "error": str(e)}

    def github_url_to_user_repo_format(self, url):
        """
        Converts a GitHub repo URL to user@repo_name format.

        :param url: str, GitHub repository URL (e.g., https://github.com/user/repo_name.git)
        :return: str, formatted as user@repo_name
        """
        import re

        # Regex to match GitHub URLs
        pattern = r"(?:https?://)?(?:www\.)?github\.com/([^/]+)/([^/.]+)(?:\.git)?"

        match = re.match(pattern, url)
        if match:
            user, repo_name = match.groups()
            return {"return": 0, "value": f"{user}@{repo_name}"}
        else:
            return {"return": 0, "value": os.path.basename(url).replace(".git", "")}

    def pull_repo(self, repo_url, branch=None, checkout = None):
        
        # Determine the checkout path from environment or default
        repo_base_path = self.repos_path # either the value will be from 'MLC_REPOS'
        os.makedirs(repo_base_path, exist_ok=True)  # Ensure the directory exists

        # Handle user@repo format (convert to standard GitHub URL)
        if re.match(r'^[\w-]+@[\w-]+$', repo_url):
            user, repo = repo_url.split('@')
            repo_url = f"https://github.com/{user}/{repo}.git"

        # Extract the repo name from URL
        repo_name = repo_url.split('/')[-1].replace('.git', '')
        res = self.github_url_to_user_repo_format(repo_url)
        if res["return"] > 0:
            return res
        else:
            repo_download_name = res["value"]
            repo_path = os.path.join(repo_base_path, repo_download_name)

        try:
            # If the directory doesn't exist, clone it
            if not os.path.exists(repo_path):
                logger.info(f"Cloning repository {repo_url} to {repo_path}...")
                
                # Build clone command without branch if not provided
                clone_command = ['git', 'clone', repo_url, repo_path]
                if branch:
                    clone_command = ['git', 'clone', '--branch', branch, repo_url, repo_path]
                
                subprocess.run(clone_command, check=True)

            else:
                logger.info(f"Repository {repo_name} already exists at {repo_path}. Checking for local changes...")
    
                # Check for local changes
                status_command = ['git', '-C', repo_path, 'status', '--porcelain', '--untracked-files=no']
                local_changes = subprocess.run(status_command, capture_output=True, text=True)

                if local_changes.stdout.strip():
                    logger.warning("There are local changes in the repository. Please commit or stash them before checking out.")
                    return {"return": 0, "warning": f"Local changes detected in the already existing repository: {repo_path}, skipping the pull"}
                else:
                    logger.info("No local changes detected. Fetching latest changes...")
                    subprocess.run(['git', '-C', repo_path, 'fetch'], check=True)
            
            # Checkout to a specific branch or commit if --checkout is provided
            if checkout:
                logger.info(f"Checking out to {checkout} in {repo_path}...")
                subprocess.run(['git', '-C', repo_path, 'checkout', checkout], check=True)
            
            logger.info("Repository successfully pulled.")
            logger.info("Registering the repo in repos.json")

            # check the meta file to obtain uids
            meta_file_path = os.path.join(repo_path, 'meta.yaml')
            if not os.path.exists(meta_file_path):
                logger.warning(f"meta.yaml not found in {repo_path}. Repo pulled but not register in mlc repos. Skipping...")
                return {"return": 0}
            
            with open(meta_file_path, 'r') as meta_file:
                meta_data = yaml.safe_load(meta_file)
                meta_data["path"] = repo_path

            # Check UID conflicts
            is_conflict = self.conflicting_repo(meta_data)
            if is_conflict['return'] > 0:
                if "UID not present" in is_conflict['error']:
                    logger.warning(f"UID not found in meta.yaml at {repo_path}. Repo pulled but can not register in mlc repos. Skipping...")
                    return {"return": 0}
                elif "already registered" in is_conflict["error"]:
                    #logger.warning(is_conflict["error"])
                    logger.info("No changes made to repos.json.")
                    return {"return": 0}
                else:
                    logger.warning(f"The repo to be cloned has conflict with the repo already in the path: {is_conflict['conflicting_path']}")
                    self.unregister_repo(is_conflict['conflicting_path'])
                    self.register_repo(repo_path, meta_data)
                    logger.warning(f"{repo_path} is registered in repos.json and {is_conflict['conflicting_path']} is unregistered.")
                    return {"return": 0}
            else:         
                r = self.register_repo(repo_path, meta_data)
                if r['return'] > 0:
                    return r
                return {"return": 0}

        except subprocess.CalledProcessError as e:
            return {'return': 1, 'error': f"Git command failed: {e}"}
        except Exception as e:
            return {'return': 1, 'error': f"Error pulling repository: {str(e)}"}

    def pull(self, run_args):
        repo_url = run_args.get('repo', run_args.get('url', 'repo'))
        if not repo_url or repo_url == "repo":
            for repo_object in self.repos:
                repo_folder_name = os.path.basename(repo_object.path)
                if "@" in repo_folder_name:
                    res = self.pull_repo(repo_folder_name)
                    if res['return'] > 0:
                        return res
        else:
            branch = run_args.get('branch')
            checkout = run_args.get('checkout')

            res = self.pull_repo(repo_url, branch, checkout)
            if res['return'] > 0:
                return res

        return {'return': 0}

            
    def list(self, run_args):
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
        logger.info("rm command has been called for repo. This would delete the repo folder and unregister the repo from repos.json")
        
        if not run_args['repo']:
            logger.error("The repository to be removed is not specified")
            return {"return": 1, "error": "The repository to be removed is not specified"}

        repo_folder_name = run_args['repo']

        repo_path = os.path.join(self.repos_path, repo_folder_name)

        if os.path.exists(repo_path):
            # Check for local changes
            status_command = ['git', '-C', repo_path, 'status', '--porcelain']
            local_changes = subprocess.run(status_command, capture_output=True, text=True)

            if local_changes.stdout:
                logger.warning("Local changes detected in repository. Changes are listed below:")
                print(local_changes.stdout)
                confirm_remove = True if(input("Continue to remove repo?").lower()) in ["yes", "y"] else False
            else:
                logger.info("No local changes detected. Removing repo...")
                confirm_remove = True
            if confirm_remove:
                shutil.rmtree(repo_path)
                logger.info(f"Repo {run_args['repo']} residing in path {repo_path} has been successfully removed")
                logger.info("Checking whether the repo was registered in repos.json")
                self.unregister_repo(repo_path)
            else:
                logger.info("rm repo ooperation cancelled by user!")
        else:
            logger.warning(f"Repo {run_args['repo']} was not found in the repo folder. repos.json will be checked for any corrupted entry. If any, that will be removed.")
            self.unregister_repo(repo_path)

        return {"return": 0}
        
