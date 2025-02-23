import argparse
import os
from pathlib import Path

from . import utils

from .action import Action, get_action, logger
from .RepoAction import RepoAction
from .ScriptAction import ScriptAction
from .CacheAction import CacheAction
from .logger import logger


class Item:
    def __init__(self, path, repo):
        self.meta = None
        self.path = path
        self.repo = repo
        self._load_meta()


    def _load_meta(self):
        yaml_file = os.path.join(self.path, "meta.yaml")
        json_file = os.path.join(self.path, "meta.json")

        if os.path.exists(yaml_file):
            self.meta = utils.read_yaml(yaml_file)
        elif os.path.exists(json_file):
            self.meta = utils.read_json(json_file)
        else:
            logger.info(f"No meta file found in {self.path} for {self.meta}")

    def _save_meta(self):
        yaml_file = os.path.join(self.path, "meta.yaml")
        _file = os.path.join(self.path, "meta.")

        if os.path.exists(yaml_file):
            utils.save_yaml(yaml_file, self.meta)
        elif os.path.exists(_file):
            utils.save_(_file, self.meta)

class Automation:
    action_object = None
    automation_type = None
    meta = None
    path = None

    def __init__(self, action, automation_type, automation_file):
        #logger.info(f"action = {action}")
        self.action_object = action
        self.automation_type = automation_type
        self.path = os.path.dirname(automation_file)
        self._load_meta()

    def _load_meta(self):
        yaml_file = os.path.join(self.path, "meta.yaml")
        _file = os.path.join(self.path, "meta.")

        if os.path.exists(yaml_file):
            self.meta = utils.read_yaml(yaml_file)
        elif os.path.exists(_file):
            self.meta = utils.read_(_file)
        else:
            logger.info(f"No meta file found in {self.path}")

    def search(self, i):
        indices = self.action_object.index.indices
        target_index = indices.get(self.automation_type)
        result = []
        if target_index:
            tags= i.get("tags")
            tags_split = tags.split(",")
            n_tags = [p for p in tags_split if p.startswith("-")]
            p_tags = list(set(tags_split) - set(n_tags))
            for res in target_index:
                c_tags = res["tags"]
                if set(p_tags).issubset(set(c_tags)) and set(n_tags).isdisjoint(set(c_tags)):
                    it = Item(res['path'], res['repo'])
                    result.append(it)
        #logger.info(result)
        return {'return': 0, 'list': result}
        #indices
        

# Child classes for specific entities (Repo, Script, Cache)
# Extends Action class


class ExperimentAction(Action):
    def __init__(self, parent=None):
        if parent is None:
            parent = default_parent
        #super().__init__(parent)
        self.parent = parent
        self.__dict__.update(vars(parent))

    def show(self, args):
        logger.info(f"Showing experiment with identifier: {args.details}")
        return {'return': 0}

    def list(self, args):
        logger.info("Listing all experiments.")
        return {'return': 0}


class CfgAction(Action):
    def __init__(self, parent=None):
        if parent is None:
            parent = default_parent
        #super().__init__(parent)
        self.parent = parent
        self.__dict__.update(vars(parent))

    def load(self, args):
        """
        Load the configuration.
        
        Args:
            args (dict): Contains the configuration details such as file path, etc.
        """
        #logger.info("In cfg load")
        default_config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.yaml')
        config_file = args.get('config_file', default_config_path)
        logger.info(f"In cfg load, config file = {config_file}")
        if not config_file or not os.path.exists(config_file):
            logger.error(f"Error: Configuration file '{config_file}' not found.")
            return {'return': 1, 'error': f"Error: Configuration file '{config_file}' not found."}
        
        #logger.info(f"Loading configuration from {config_file}")
        
        # Example loading YAML configuration (can be modified based on your needs)
        try:
            with open(config_file, 'r') as file:
                config_data = yaml.safe_load(file)
                logger.info(f"Loaded configuration: {config_data}")
                # Store configuration in memory or perform other operations
                self.cfg = config_data
        except yaml.YAMLError as e:
            logger.error(f"Error loading YAML configuration: {e}")
        
        return {'return': 0, 'config': self.cfg}


def mlcr():
    first_arg_value = "run"
    second_arg_value = "script"

    # Insert the positional argument into sys.argv for the main function
    sys.argv.insert(1, first_arg_value)
    sys.argv.insert(2, second_arg_value)

    # Call the main function
    main()

default_parent = None

if default_parent is None:
    default_parent = Action()

def process_console_output(res, target, action, run_args):
    if action in ["find", "search"]:
        if "list" not in res:
            logger.error("'list' entry not found in find result")
            return  # Exit function if there's an error
        if len(res['list']) == 0:
            logger.warning(f"""No {target} entry found for the specified input: {run_args}!""")
        else:
            for item in res['list']:
                logger.info(f"""Item path: {item.path}""")

# Main CLI function
def main():
    parser = argparse.ArgumentParser(prog='mlc', description='A CLI tool for managing repos, scripts, and caches.')

    # Subparsers are added to main parser, allowing for different commands (subcommands) to be defined. 
    # The chosen subcommand will be stored in the "command" attribute of the parsed arguments.
    subparsers = parser.add_subparsers(dest='command', required=True)

    # Script and Cache-specific subcommands
    for action in ['run', 'pull', 'test', 'add', 'show', 'list', 'find', 'search', 'rm', 'cp', 'mv']:
        action_parser = subparsers.add_parser(action, help=f'{action} a target.')
        action_parser.add_argument('target', choices=['repo', 'script', 'cache'], help='Target type (repo, script, cache).')
        # the argument given after target and before any extra options like --tags will be stored in "details"
        action_parser.add_argument('details', nargs='?', help='Details or identifier (optional for list).')
        action_parser.add_argument('extra', nargs=argparse.REMAINDER, help='Extra options (e.g.,  -v)')

    # Script and specific subcommands
    for action in ['docker', 'help']:
        action_parser = subparsers.add_parser(action, help=f'{action.capitalize()} a target.')
        action_parser.add_argument('target', choices=['script', 'run'], help='Target type (script).')
        # the argument given after target and before any extra options like --tags will be stored in "details"
        action_parser.add_argument('details', nargs='?', help='Details or identifier (optional for list).')
        action_parser.add_argument('extra', nargs=argparse.REMAINDER, help='Extra options (e.g.,  -v)')

    for action in ['load']:
        load_parser = subparsers.add_parser(action, help=f'{action.capitalize()} a target.')
        load_parser.add_argument('target', choices=['cfg'], help='Target type (cfg).')
    
    
    # Parse arguments
    args = parser.parse_args()

    #logger.info(f"Args = {args}")

    res = utils.convert_args_to_dictionary(args.extra)
    if res['return'] > 0:
        return res

    run_args = res['args_dict']
    if hasattr(args, 'repo') and args.repo:
        run_args['repo'] = args.repo
        
    if args.command in ['pull', 'rm', 'add', 'find']:
        if args.target == "repo":
            run_args['repo'] = args.details
  
    if args.command in ['docker']:
        if args.target == "run":
            run_args['target'] = 'script' #allowing run to be used for docker run instead of docker script
            args.target = "script"

    if hasattr(args, 'details') and args.details and "," in args.details and not run_args.get("tags") and args.target in ["script", "cache"]:
        run_args['tags'] = args.details

    if not run_args.get('details') and args.details:
        run_args['details'] = args.details

    if args.command in ["cp", "mv"]:
        run_args['target'] = args.target
        if hasattr(args, 'details') and args.details:
            run_args['src'] = args.details
        if hasattr(args, 'extra') and args.extra:
            run_args['dest'] = args.extra[0]

    # Get the action handler for other commands
    action = get_action(args.target, default_parent)
    # Dynamically call the method (e.g., run, list, show)
    if action and hasattr(action, args.command):
        method = getattr(action, args.command)
        res = method(run_args)
        if res['return'] > 0:
            logger.error(res.get('error', f"Error in {action}"))
            raise Exception(f"""An error occurred {res}""")
        process_console_output(res, args.target, args.command, run_args)
    else:
        logger.error(f"Error: '{args.command}' is not supported for {args.target}.")

if __name__ == '__main__':
    main()

