from .action import Action
import os
import sys
import importlib
from . import utils
from .logger import logger

class ScriptAction(Action):
    """
    ####################################################################################################################
    Script Action
    ####################################################################################################################

    The following actions are currently supported for scripts:
    1.  Add
    2.  Find
    3.  Show
    4.  Move(mv)
    5.  Remove(rm)
    6.  Copy(cp)
    7.  Run
    8.  Docker
    9.  Test
    10. Experiment

    Scripts in MLCFlow can be identified using different methods:

    Using tags: --tags=<comma-separated-tags> (e.g., --tags=detect,os)
    Using alias: <script_alias> (e.g., detect-os)
    Using UID: <script_uid> (e.g., 5b4e0237da074764)
    Using both alias and UID: <script_alias>,<script_uid> (e.g., detect-os,5b4e0237da074764)

    """
    parent = None
    def __init__(self, parent=None):
        self.parent = parent
        self.__dict__.update(vars(parent))

    def search(self, i):
        """
    ####################################################################################################################
    Target: Script
    Action: Find (Alias: Search)
    ####################################################################################################################

    The `find` (or `search`) action retrieves the path of scripts available in MLC repositories.

    Example Command:

    mlc find script --tags=detect,os -f

        """
        if not i.get('target_name'):
            i['target_name'] = "script"
        res = self.parent.search(i)
        return res

    find = search
        
    def rm(self, i):
        """
    ####################################################################################################################
    Target: Script
    Action: Remove(rm)
    ####################################################################################################################

    The `remove` (`rm`) action deletes one or more scripts from MLC repositories.  

    Example Command:

    mlc rm script --tags=detect,os -f

        """
        if not i.get('target_name'):
            i['target_name'] = "script"
        logger.debug(f"Removing script with input: {i}")
        return self.parent.rm(i)

    def show(self, run_args):
        """
    ####################################################################################################################
    Target: Script
    Action: Show
    ####################################################################################################################

    The `show` action retrieves the path and metadata of the searched script in MLC repositories.  

    Example Command:

    mlc show script --tags=detect,os

    Example Output:
          
      arjun@intel-spr-i9:~$ mlc show script --tags=detect,os
      [2025-02-14 02:56:16,604 main.py:1404 INFO] - Showing script with tags: detect,os
      Location: /home/arjun/MLC/repos/gateoverflow@mlperf-automations/script/detect-os:
      Main Script Meta:
        uid: 863735b7db8c44fc
        alias: detect-os
        tags: ['detect-os', 'detect', 'os', 'info']
        new_env_keys: ['MLC_HOST_OS_*', '+MLC_HOST_OS_*', 'MLC_HOST_PLATFORM_*', 'MLC_HOST_PYTHON_*', 'MLC_HOST_SYSTEM_NAME', 
                       'MLC_RUN_STATE_DOCKER', '+PATH']
        new_state_keys: ['os_uname_*']
      ......................................................
      For full script meta, see meta file at /home/arjun/MLC/repos/gateoverflow@mlperf-automations/script/detect-os/meta.yaml

    Note:
    - The `find` action is a subset of `show`, retrieving only the path of the searched script in MLC repositories.

        """
        self.action_type = "script"
        res = self.search(run_args)
        if res['return'] > 0:
            return res
        logger.info(f"Showing script with tags: {run_args.get('tags')}")
        script_meta_keys_to_show = ["uid", "alias", "tags", "new_env_keys", "new_state_keys", "cache"]
        for item in res['list']:
            print(f"""Location: {item.path}:
Main Script Meta:""")
            for key in script_meta_keys_to_show:
                if key in item.meta:
                    print(f"""    {key}: {item.meta[key]}""")
            if "input_mapping" in item.meta:
                print("    Input mapping:")
                utils.printd(item.meta["input_mapping"], begin_spaces=8)
            print("......................................................")
            print(f"""For full script meta, see meta file at {os.path.join(item.path, "meta.yaml")}""")
            print("")
            
        return {'return': 0}

    def add(self, i):
        """
    ####################################################################################################################
    Target: Script
    Action: Add
    ####################################################################################################################

    The `add` action creates a new script in a registered MLC repository.  

    Syntax:

    mlc add script <user@repo>:new_script --tags=benchmark

    Options:
        --template_tags: A comma-separated list of tags to create a new MLC script based on existing templates.  

    Example Output:
          
      arjun@intel-spr-i9:~$ mlc add script gateoverflow@mlperf-automations --tags=benchmark --template_tags=app,mlperf,inference
      More than one script found for None:
      1. /home/arjun/MLC/repos/gateoverflow@mlperf-automations/script/app-mlperf-inference-mlcommons-python
      2. /home/arjun/MLC/repos/gateoverflow@mlperf-automations/script/app-mlperf-inference-ctuning-cpp-tflite
      3. /home/arjun/MLC/repos/gateoverflow@mlperf-automations/script/app-mlperf-inference
      4. /home/arjun/MLC/repos/gateoverflow@mlperf-automations/script/app-mlperf-inference-mlcommons-cpp
      Select the correct one (enter number, default=1): 1
      [2025-02-14 02:58:33,453 main.py:664 INFO] - Folder successfully copied from /home/arjun/MLC/repos/
        gateoverflow@mlperf-automations/script/app-mlperf-inference-mlcommons-python to /home/arjun/MLC/repos/
        gateoverflow@mlperf-automations/script/gateoverflow@mlperf-automations

        """
        # """
        # Adds a new script to the repository.

        # Args:
        #     i (dict): Input dictionary with the following keys:
        #         - item_repo (tuple): Repository alias and UID (default: local repo).
        #         - item (str): Item alias and optional UID in "alias,uid" format.
        #         - tags (str): Comma-separated tags.
        #         - yaml (bool): Whether to save metadata in YAML format. Defaults to JSON.

        # Returns:
        #     dict: Result of the operation with 'return' code and error/message if applicable.
        # """
        # Determine repository
        if i.get('details'):
            item = i['details']
        else:
            item = i.get('item')
        if not item:
            return {'return': 1, 'error': f"""No script item given to add. Please use mlc add script <repo_name>:<script_name> --tags=<script_tags> format to add a script to a given repo"""}
        ii = {}
        ii['target'] = "script"
        ii['src_tags'] = i.get("template_tags", "template,generic")
        ii['dest'] = item
        ii['tags'] = i.get('tags', [])
        res =  self.cp(ii)

        return res

    def dynamic_import_module(self, script_path):
        # Validate the script_path
        if not os.path.exists(script_path):
            raise FileNotFoundError(f"Script file not found: {script_path}")

        # Add the parent folder of the script to sys.path
        script_dir = os.path.dirname(script_path)
        automation_dir = os.path.dirname(script_dir)  # automation folder

        if automation_dir not in sys.path:
            sys.path.insert(0, automation_dir)

        # Dynamically load the module
        module_name = os.path.splitext(os.path.basename(script_path))[0]
        spec = importlib.util.spec_from_file_location(module_name, script_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create a module spec for: {script_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        return module

    def call_script_module_function(self, function_name, run_args):
        self.action_type = "script"
        repos_folder = self.repos_path

        # Import script submodule 
        script_path = self.find_target_folder("script")
        if not script_path:
            return {'return': 1, 'error': f"""Script automation not found. Have you done "mlc pull repo mlcommons@mlperf-automations --branch=dev"?"""}

        module_path = os.path.join(script_path, "module.py")
        module = self.dynamic_import_module(module_path)

        # Check if ScriptAutomation is defined in the module
        if hasattr(module, 'ScriptAutomation'):
            automation_instance = module.ScriptAutomation(self, module_path)
            if function_name == "run":
                result = automation_instance.run(run_args)  # Pass args to the run method
            elif function_name == "docker":
                result = automation_instance.docker(run_args)  # Pass args to the run method
            elif function_name == "test":
                result = automation_instance.test(run_args)  # Pass args to the run method
            elif function_name == "experiment":
                result = automation_instance.experiment(run_args)  # Pass args to the experiment method
            elif function_name == "doc":
                result = automation_instance.doc(run_args)  # Pass args to the doc method
            else:
                return {'return': 1, 'error': f'Function {function_name} is not supported'}
            
            if result['return'] > 0:
                error = result.get('error', "")
                raise ScriptExecutionError(f"Script {function_name} execution failed. Error : {error}")
            return result
        else:
            logger.info("ScriptAutomation class not found in the script.")
            return {'return': 1, 'error': 'ScriptAutomation class not found in the script.'}

    def docker(self, run_args):
        """
    ####################################################################################################################
    Target: Script
    Action: Docker
    ####################################################################################################################

    The `docker` action runs scripts inside a containerized environment.  

    An MLCFlow script can be executed inside a Docker container using either of the following syntaxes:

    1. Docker Run: mlc docker run --tags=<script tags> <run flags> (e.g., mlc docker run --tags=detect,os --docker_dt 
                       --docker_cache=no)
    2. Docker Script: mlc docker script --tags=<script tags> <run flags> (e.g., mlc docker script --tags=detect,os 
                          --docker_dt --docker_cache=no)

    Flags Available:

    1. --docker_dt or --docker_detached:
        Runs the specified script inside a Docker container in detached mode (e.g., `mlc docker run --tags=detect,os --docker_dt).
        By default, the Docker container is launched in interactive mode.
    2. --docker_cache:
        Disabling this flag forces Docker to build all layers from scratch, ignoring cached layers. (e.g., mlc docker run --tags=detect,os --docker_cache=no)
        By default, the value is set to true/yes.
    3. --docker_rebuild:
        Enables rebuilding the Docker container even if an existing container with the same tag is present. (e.g., mlc docker run --tags=detect,os --docker_rebuild)
        By default, the value is set to False.
    4. --dockerfile_recreate:
        Forces recreation of the **Dockerfile** during execution. (e.g., mlc docker run --tags=detect,os --docker_rebuild --dockerfile_recreate)
        By default, the value is set to False.

    Example Command:

    mlc docker script --tags=detect,os -j

        """
        return self.call_script_module_function("docker", run_args)


    def run(self, run_args):
        """
    ####################################################################################################################
    Target: Script
    Action: Run
    ####################################################################################################################

    The `run` action executes a script from an MLC repository.  

    Example Command:

    mlc run script --tags=detect,os -j

    Options:

    1. -j: Displays the output in JSON format.
    2. Instead of using `mlc run script --tags=`, you can simply use `mlcr`.
    3. *<Individual script inputs>: The `mlcr` command can accept additional inputs defined in the script's `input_mappings` metadata.  

        """
        return self.call_script_module_function("run", run_args)


    def test(self, run_args):
        """
    ####################################################################################################################
    Target: Script
    Action: test
    ####################################################################################################################

    The `test` action validates scripts that are configured with a `tests` section in `meta.yaml`.  

    Example Command:

    mlc test script --tags=benchmark

        """
        return self.call_script_module_function("test", run_args)


    def doc(self, run_args):
        """
    ####################################################################################################################
    Target: Script
    Action: doc
    ####################################################################################################################

    The `doc` action creates automatic README for scripts from the contents in `meta.yaml`.  

    Example Command:

    mlc doc script --tags=detect,os

        """
        return self.call_script_module_function("doc", run_args)


    def help(self, run_args):
        # Internal function to call the help function in script automation module.py
        return self.call_script_module_function("help", run_args)


    def list(self, args):
        """
    ####################################################################################################################
    Target: Script
    Action: List
    ####################################################################################################################

    The `list` action displays all scripts and their paths from repositories registered in MLC.  

    Example Command:

    mlc list script

        """
        self.action_type = "script"
        run_args = {"fetch_all": True}  # to fetch the details of all the scripts present in repos registered  in mlc
        
        res = self.search(run_args)
        if res['return'] > 0:
            return res
        
        logger.info(f"Listing all the scripts and their paths present in repos which are registered in MLC")
        print("......................................................")
        for item in res['list']:
            print(f"alias: {item.meta['alias'] if item.meta.get('alias') else 'None'}")
            print(f"Location: {item.path}")
            print("......................................................")

        return {"return": 0}

    def experiment(self, run_args):
        """
    ####################################################################################################################
    Target: Script
    Action: Experiment
    ####################################################################################################################

    The `experiment` action currently does the function same as of run script, proper workflow will be added in future.
    experiment-specific functionality.

    Example Command:

    mlc experiment script --tags=detect,os -j

        """
        return self.call_script_module_function("experiment", run_args)

class ScriptExecutionError(Exception):
    # """Custom error for configuration issues."""
    pass
