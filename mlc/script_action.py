import re
from .action import Action
import os
import sys
import json
from .index import Index
from . import utils
from .engine import ScriptAutomation
from .error_codes import get_error_guidance
from .logger import logger


def get_mlcflow_version():
    """Return the installed mlcflow version for error context.

    Replaces the pre-migration behaviour of embedding the git module path in
    error messages (the engine no longer lives at a ``/repos/.../module.py``
    path).
    """
    try:
        from importlib.metadata import version
        return f"mlcflow {version('mlcflow')}"
    except Exception:
        return "mlcflow (unknown version)"


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
        description: Detects the operating system and platform information
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
        script_meta_keys_to_show = [
            "uid",
            "alias",
            "description",
            "tags",
            "new_env_keys",
            "new_state_keys",
            "cache"]
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
            print(
                f"""For full script meta, see meta file at {os.path.join(item.path, "meta.yaml")}""")
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
        res = self.cp(ii)

        return res

    def call_script_module_function(self, function_name, run_args):
        self.action_type = "script"

        # Engine is now part of mlcflow (mlc/engine/) and imported directly.
        # No dynamic module loading and no auto-clone of mlperf-automations.
        # Script *content* is discovered at run time via the index, which
        # includes both registered local repos and the bundled mlc-scripts
        # package (see index.py / find_scripts_dir).
        automation_instance = ScriptAutomation(self, run_args)

        _version_str = get_mlcflow_version()

        try:
            if function_name == "run":
                result = automation_instance.run(run_args)
            elif function_name == "docker":
                result = automation_instance.docker(run_args)
            elif function_name == "test":
                result = automation_instance.test(run_args)
            elif function_name == "experiment":
                result = automation_instance.experiment(run_args)
            elif function_name == "remote_run":
                result = automation_instance.remote_run(run_args)
            elif function_name == "help":
                result = automation_instance.help(run_args)
            elif function_name == "doc":
                result = automation_instance.doc(run_args)
            elif function_name == "lint":
                result = automation_instance.lint(run_args)
            else:
                return {
                    'return': 1, 'error': f'Function {function_name} is not supported'}
        except ScriptExecutionError:
            raise
        except Exception as exc:
            _script_name = run_args.get('tags', run_args.get('details'))
            raise ScriptExecutionError(
                f"Script {function_name} execution failed ({_version_str})." +
                "\nError : " + f"{type(exc).__name__}: {exc}",
                script_name=_script_name, run_args=run_args) from exc

        if result['return'] > 0:
            error = result.get('error', "")
            error_guidance = get_error_guidance(
                result.get('error_code', result.get('return')), error)
            _name_match = re.search(r'name\s*=\s*([^,)]+)', error)
            _script_name = _name_match.group(1).strip() if _name_match else run_args.get(
                'tags', run_args.get('details'))
            # Dump dependency version info to file for debugging
            _version_info_file = None
            _version_info = result.get('version_info', [])
            if _version_info:
                _version_info_file = os.path.join(
                    os.getcwd(), 'mlc-error-version-info.json')
                try:
                    with open(_version_info_file, 'w') as _vf:
                        json.dump(_version_info, _vf, indent=2)
                except Exception:
                    _version_info_file = None
            raise ScriptExecutionError(
                f"Script {function_name} execution failed ({_version_str}). \nError : {error}",
                script_name=_script_name, run_args=run_args,
                version_info_file=_version_info_file,
                error_code=error_guidance.get(
                    'error_code') if error_guidance else None,
                error_guidance=error_guidance)

        if str(run_args.get("mlc_output")).lower() in [
                "on", "true", "yes", "1"]:
            with open("tmp-state.json", "w") as f:
                json.dump(result['new_state'], f, indent=2)

            with open("tmp-run-env.out", "w") as f:
                for key, val in result['new_env'].items():
                    f.write(f"""{key}="{val}"\n""")

        return result

    def docker(self, run_args):
        return self.docker_run(run_args)

    def docker_run(self, run_args):
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
        Runs the specified script inside a Docker container in detached mode.
        By default, the Docker container is launched in interactive mode.
    2. --docker_cache:
        Disabling this flag forces Docker to build all layers from scratch, ignoring cached layers (default: yes)
    3. --docker_rebuild:
        Rebuilds the Docker image even if one with the same tag already exists (default: False)
    4. --docker_noregenerate:
        Skip regeneration of the Dockerfile during execution (default: False)
    5. --docker_image_repo:
        Custom Docker image repository name
    6. --docker_verbose:
        Enable verbose output during Docker operations
    7. --docker_silent:
        Suppress output during Docker operations
    8. --docker_host_mlc_repos:
        Mount host MLC repos inside the container
    9. --docker_upload:
        Push the built Docker image after execution
    10. --docker_run_cmd_prefix:
        Prefix to prepend to the run command inside the container

    Example Command:

    mlc docker script --tags=detect,os -j
    mlcd detect,os -j

        """
        return self.call_script_module_function("docker", run_args)

    docker.__doc__ = docker_run.__doc__

    def remote_run(self, run_args):
        """
    ####################################################################################################################
    Target: Script
    Action: remote-run
    ####################################################################################################################

    The `remote-run` action runs a shell command on a remote machine via ssh connection.


    Flags Available:

    1. --remote_host:
        IP or hostname for the remote machine (default: localhost)
    2. --remote_port:
        SSH port for the remote machine (default: 22)
    3. --remote_user:
        Username for SSH login on the remote machine
    4. --remote_password:
        Password for SSH authentication
    5. --remote_ssh_key_file:
        Path to the SSH private key file for authentication
    6. --remote_skip_host_verify:
        Skip SSH host key verification
    7. --remote_python_venv:
        Name of the Python virtual environment on the remote machine (default: mlcflow)
    8. --remote_pull_mlc_repos:
        Pull MLC repos on the remote machine before running
    9. --remote_copy_directory:
        Remote directory to copy files to (default: mlc-remote-artifacts)
    10. --remote_pre_run_cmds:
        Commands to run on the remote machine before the main script
    11. --remote_client_refresh:
        Refresh the SSH client connection

    Example Command:

    mlc remote-run script --tags=detect,os -j
    mlcrr detect,os -j

        """
        return self.call_script_module_function("remote_run", run_args)

    def run(self, run_args):
        """
    ####################################################################################################################
    Target: Script
    Action: Run
    ####################################################################################################################

    The `run` action executes a script from an MLC repository.

    Example Command:

    mlc run script --tags=detect,os -j
    mlcr detect,os -j

    Options:

    1. -j: Displays the output in JSON format.
    2. Instead of using `mlc run script --tags=`, you can simply use `mlcr`.
    3. *<Individual script inputs>: The `mlcr` command can accept additional inputs defined in the script's `input_mappings` metadata.

        """
        if not run_args.get('tags') and not run_args.get('details'):
            return self.call_script_module_function("help", run_args)
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

    def lint(self, run_args):
        """
    ####################################################################################################################
    Target: Script
    Action: lint
    ####################################################################################################################

    The `lint` action automatically formats the contents in `meta.yaml`.

    Example Command:

    mlc lint script --tags=detect,os

        """
        return self.call_script_module_function("lint", run_args)

    def help(self, run_args):
        # Internal function to call the help function in script automation
        # module.py
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
        # to fetch the details of all the scripts present in repos registered
        # in mlc
        run_args = {"fetch_all": True}

        res = self.search(run_args)
        if res['return'] > 0:
            return res

        logger.info(
            f"Listing all the scripts and their paths present in repos which are registered in MLC")
        print("......................................................")
        for item in res['list']:
            print(
                f"alias: {item.meta['alias'] if item.meta.get('alias') else 'None'}")
            print(f"Location: {item.path}")
            print("......................................................")

        return {"return": 0}

    def experiment(self, run_args):
        """
    ####################################################################################################################
    Target: Script
    Action: Experiment
    ####################################################################################################################

    The `experiment` action automates exploration runs of MLC scripts.

    Flags Available:

    1. --exp_tags:
        Comma-separated extra tags for the experiment run
    2. --exp_skip_state_save:
        Skip saving the system state during the experiment (default: False)
    3. --exp.<key>=<value>:
        Pass experiment-specific parameters using the `exp.` prefix (e.g., --exp.batch_size=32)

    In addition, all flags supported by the `run` action are also available.

    Example Command:

    mlc experiment script --tags=detect,os -j
    mlce detect,os -j

        """
        return self.call_script_module_function("experiment", run_args)

    def remote_experiment(self, run_args):
        """
    ################################################################################################################################################
    Target: Script
    Action: remote-experiment
    ################################################################################################################################################

    The `remote-experiment` action runs an experiment on a remote machine via ssh connection.

    Flags Available:

    1. --remote_host:
        IP or hostname for the remote machine (default: localhost)
    2. --remote_port:
        SSH port for the remote machine (default: 22)
    3. --remote_user:
        Username for SSH login on the remote machine
    4. --remote_password:
        Password for SSH authentication
    5. --remote_ssh_key_file:
        Path to the SSH private key file for authentication
    6. --remote_skip_host_verify:
        Skip SSH host key verification
    7. --remote_python_venv:
        Name of the Python virtual environment on the remote machine (default: mlcflow)
    8. --remote_pull_mlc_repos:
        Pull MLC repos on the remote machine before running
    9. --remote_copy_directory:
        Remote directory to copy files to (default: mlc-remote-artifacts)
    10. --remote_pre_run_cmds:
        Commands to run on the remote machine before the main script
    11. --remote_client_refresh:
        Refresh the SSH client connection

    Example Command:

    mlc remote-experiment script --tags=detect,os -j
    mlcre detect,os -j

        """
        run_args["remote_action"] = "experiment"
        return self.call_script_module_function("remote_run", run_args)

    def remote_docker(self, run_args):
        """
    ################################################################################################################################################
    Target: Script
    Action: remote-docker
    ################################################################################################################################################

    The `remote-docker` action runs a script inside a Docker container on a remote machine via ssh connection.

    Flags Available:

    1. --remote_host:
        IP or hostname for the remote machine (default: localhost)
    2. --remote_port:
        SSH port for the remote machine (default: 22)
    3. --remote_user:
        Username for SSH login on the remote machine
    4. --remote_password:
        Password for SSH authentication
    5. --remote_ssh_key_file:
        Path to the SSH private key file for authentication
    6. --remote_skip_host_verify:
        Skip SSH host key verification
    7. --remote_python_venv:
        Name of the Python virtual environment on the remote machine (default: mlcflow)
    8. --remote_pull_mlc_repos:
        Pull MLC repos on the remote machine before running
    9. --remote_copy_directory:
        Remote directory to copy files to (default: mlc-remote-artifacts)
    10. --remote_pre_run_cmds:
        Commands to run on the remote machine before the main script
    11. --remote_client_refresh:
        Refresh the SSH client connection

    Example Command:

    mlc remote-docker script --tags=detect,os -j
    mlcrd detect,os -j

        """
        run_args["remote_action"] = "docker"
        return self.call_script_module_function("remote_run", run_args)


class ScriptExecutionError(Exception):
    def __init__(self, message, script_name=None, repo_alias=None,
                 module_path=None, run_args=None, version_info_file=None,
                 error_code=None, error_guidance=None):
        super().__init__(message)
        self.script_name = script_name
        self.repo_alias = repo_alias
        self.module_path = module_path
        self.run_args = run_args or {}
        self.version_info_file = version_info_file
        self.error_code = error_code
        self.error_guidance = error_guidance
