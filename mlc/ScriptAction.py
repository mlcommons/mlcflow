from .action import Action
import os
from . import utils
from logger import logger

class ScriptAction(Action):
    parent = None
    def __init__(self, parent=None):
        if parent is None:
            parent = default_parent
        self.parent = parent
        self.__dict__.update(vars(parent))

    def search(self, i):
        if not i.get('target_name'):
            i['target_name'] = "script"
        res = self.parent.search(i)
        #print(res)
        return res

    find = search
        
    def rm(self, i):
        if not i.get('target_name'):
            i['target_name'] = "script"
        logger.debug(f"Removing script with input: {i}")
        return self.parent.rm(i)

    def show(self, run_args):
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
        Adds a new script to the repository.

        Args:
            i (dict): Input dictionary with the following keys:
                - item_repo (tuple): Repository alias and UID (default: local repo).
                - item (str): Item alias and optional UID in "alias,uid" format.
                - tags (str): Comma-separated tags.
                - yaml (bool): Whether to save metadata in YAML format. Defaults to JSON.

        Returns:
            dict: Result of the operation with 'return' code and error/message if applicable.
        """
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
        return self.call_script_module_function("docker", run_args)

    def run(self, run_args):
        return self.call_script_module_function("run", run_args)

    def test(self, run_args):
        return self.call_script_module_function("test", run_args)


    def list(self, args):
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


class ScriptExecutionError(Exception):
    """Custom error for configuration issues."""
    pass
