from .action import Action
import os
import subprocess
import re
import yaml
import json
import shutil
from . import utils
from .logger import logger

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

    def __init__(self, parent=None):
        #super().__init__(parent)
        self.parent = parent
        self.__dict__.update(vars(parent))


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
                self.pull_repo(dep['url'], branch=dep.get('branch'), checkout=dep.get('checkout'), ignore_on_conflict=dep.get('is_alias_okay', True))

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
        if utils.is_uid(repo):
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
            elif utils.is_uid(repo) and not any(i.meta['uid'] == repo_uid for i in self.repos):
                return {"return": 1, "error": f"No repository with UID: '{repo_uid}' was found"}
            elif "," in repo and not matched_repo_path and not any(i.meta['uid'] == repo_uid for i in self.repos) and not any(i.meta['alias'] == repo_name for i in self.repos):
                return {"return": 1, "error": f"No repository with alias: '{repo_name}' and UID: '{repo_uid}' was found"}
            elif not matched_repo_path and not any(i.meta['alias'] == repo_name for i in self.repos) and not any(i.meta['uid'] == repo_uid for i in self.repos ):
                return {"return": 1, "error": f"No repository with alias: '{repo_name}' was found"}
                
        # Append the matched repo path
        if(len(lst)==0):
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
            return {"return": 0, "value": os.path.basename(url).replace(".git", "")}

    def pull_repo(self, repo_url, branch=None, checkout = None, tag = None, pat = None, ssh = None, ignore_on_conflict = False):
        
        # Determine the checkout path from environment or default
        repo_base_path = self.repos_path # either the value will be from 'MLC_REPOS'
        os.makedirs(repo_base_path, exist_ok=True)  # Ensure the directory exists

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
                    print(local_changes.stdout.strip())
                    return {"return": 0, "warning": f"Local changes detected in the already existing repository: {repo_path}, skipping the pull"}
                else:
                    logger.info("No local changes detected. Pulling latest changes...")
                    subprocess.run(['git', '-C', repo_path, 'pull'], check=True)
                    logger.info("Repository successfully pulled.")

            if tag:
                checkout = "tags/"+tag

            # Checkout to a specific branch or commit if --checkout is provided
            if checkout or tag:
                logger.info(f"Checking out to {checkout} in {repo_path}...")
                subprocess.run(['git', '-C', repo_path, 'checkout', checkout], check=True)
            
            #if not tag:
            #    subprocess.run(['git', '-C', repo_path, 'pull'], check=True)
            #    logger.info("Repository successfully pulled.")

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
                    logger.debug("No changes made to repos.json.")
                    return {"return": 0}
                else:
                    if ignore_on_conflict:
                        logger.debug("Repo alias existing. Ignoring the repo pull")
                        return {"return": 0}

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
    - `--branch <branch_name>`: Checks out a specific branch **while cloning** a new repository.
    - `--tag <release_tag>`: Checks out a particular release tag.
    - `--pat <access_token>` or `--ssh`: Clones a private repository using a personal access token or SSH.

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
                if os.path.exists(os.path.join(repo_object.path, ".git")):
                    repo_folder_name = os.path.basename(repo_object.path)
                    res = self.pull_repo(repo_folder_name)
                    if res['return'] > 0:
                        return res
        else:
            branch = run_args.get('branch')
            checkout = run_args.get('checkout')
            tag = run_args.get('tag')

            pat = run_args.get('pat')
            ssh = run_args.get('ssh')

            if sum(bool(var) for var in [branch, checkout, tag]) > 1:
                    return {"return": 1, "error": "Only one among the three flags(branch, checkout and tag) could be specified"}

            res = self.pull_repo(repo_url, branch, checkout, tag, pat, ssh)
            if res['return'] > 0:
                return res

        return {'return': 0}

            
    def list(self, run_args):
        """
    ####################################################################################################################
    Target: Repo
    Action: List
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

    The `rm` action removes a specified repository from MLCFlow, deleting both the repo folder and its registration.  
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
            return {"return": 1, "error": "The repository to be removed is not specified"}

        repo_folder_name = run_args['repo']
        repo_path = os.path.join(self.repos_path, repo_folder_name)
        repos_file_path = os.path.join(self.repos_path, 'repos.json')
        
        force_remove = True if run_args.get('f') else False
        
        return rm_repo(repo_path, repos_file_path, force_remove) 
        
def rm_repo(repo_path, repos_file_path, force_remove):
        logger.info("rm command has been called for repo. This would delete the repo folder and unregister the repo from repos.json")
        
        repo_name = os.path.basename(repo_path)
        if os.path.exists(repo_path):
            # Check for local changes
            status_command = ['git', '-C', repo_path, 'status', '--porcelain', '--untracked-files=no']
            local_changes = subprocess.run(status_command, capture_output=True, text=True)

            if local_changes.stdout:
                logger.warning("Local changes detected in repository. Changes are listed below:")
                print(local_changes.stdout)
                confirm_remove = True if force_remove or (input("Continue to remove repo?").lower()) in ["yes", "y"] else False
            else:
                logger.info("No local changes detected. Removing repo...")
                confirm_remove = True
            if confirm_remove:
                if force_remove:
                    logger.info("Force remove is set.")
                shutil.rmtree(repo_path)
                logger.info(f"Repo {repo_name} residing in path {repo_path} has been successfully removed")
                logger.info("Checking whether the repo was registered in repos.json")
                unregister_repo(repo_path, repos_file_path)
            else:
                logger.info("rm repo ooperation cancelled by user!")
        else:
            logger.warning(f"Repo {repo_name} was not found in the repo folder. repos.json will be checked for any corrupted entry. If any, that will be removed.")
            unregister_repo(repo_path, repos_file_path)

        return {"return": 0}
    
def unregister_repo(repo_path, repos_file_path):
        logger.info(f"Unregistering the repo in path {repo_path}")

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

