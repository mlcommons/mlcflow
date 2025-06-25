import argparse
import os
import sys
from pathlib import Path
import inspect

from . import utils

from .action import Action, default_parent
from .repo_action import RepoAction
from .script_action import ScriptAction
from .cache_action import CacheAction
from .cfg_action import CfgAction
from .experiment_action import ExperimentAction

from .item import Item
from .action_factory import get_action
from .logger import logger, logging


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
        json_file = os.path.join(self.path, "meta.json")

        if os.path.exists(yaml_file):
            self.meta = utils.read_yaml(yaml_file)
        elif os.path.exists(json_file):
            self.meta = utils.read_json(json_file)
        else:
            logger.info(f"No meta file found in {self.path}")

    def search(self, i):
        indices = self.action_object.index.indices
        target_index = indices.get(self.automation_type)
        result = []
        if target_index:
            tags = i.get("tags")
            if tags == '':
                tags_split = []
            else:
                tags_split = tags.split(",")
            n_tags = [p for p in tags_split if p.startswith("-")]
            p_tags = list(set(tags_split) - set(n_tags))
            uid = None
            alias = None
            if not tags:
                if i.get('details'):
                    item_split = i['details'].split(",")
                    if len(item_split) > 1:
                        alias = item_split[0]
                        uid = item_split[1]
                    else:
                        uid = item_split[0]
            for res in target_index:
                c_tags = res["tags"]
                if set(p_tags).issubset(set(c_tags)) and set(n_tags).isdisjoint(set(c_tags)) and (not uid or uid == res['uid']) and (not alias or alias == res['alias']):
                    it = Item(res['path'], res['repo'])
                    result.append(it)
        #logger.info(result)
        return {'return': 0, 'list': result}
        #indices


def mlcr():
    first_arg_value = "run"
    second_arg_value = "script"

    # Insert the positional argument into sys.argv for the main function
    sys.argv.insert(1, first_arg_value)
    sys.argv.insert(2, second_arg_value)

    # Call the main function
    main()



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
    if "warnings" in res:
        logger.warning(f"{len(res['warnings'])} warning(s) found during the execution of the mlc command.")
        for warning in res["warnings"]:
            logger.warning(f"Warning code: {warning['code']}, Discription: {warning['description']}")

if default_parent is None:
    default_parent = Action()

# Main CLI function
def main():
    """
    MLCFlow is a CLI tool for managing repos, scripts, and caches.
    This framework is designed to streamline automation workflows for MLPerf benchmarks more efficiently.
    You can also use this tool for any of your workflow automation tasks.

    MLCFlow CLI operates using actions and targets. It enables users to perform actions on specified targets using the following syntax:
          
    mlc <action> <target> [options]

    Here, actions represent the operations to be performed, and the target is the object on which the action is executed.

    Each target has a specific set of actions to tailor automation workflows, as shown below:
    
    | Target  | Actions                                               |
    |---------|-------------------------------------------------------|
    | script  | run, find/search, rm, mv, cp, add, test, docker, show |
    | cache   | find/search, rm, show                                 |
    | repo    | pull, search, rm, list, find/search                   |
    
    Example:
      mlc run script detect-os
      
    For help related to a particular target, run: 
    
    mlc help <target>
    
    For help related to a specific action for a target, run: 
    
    mlc help <action> <target>
    """
    parser = argparse.ArgumentParser(prog='mlc', description='A CLI tool for managing repos, scripts, and caches.', add_help=False)

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

    # Script specific subcommands
    for action in ['docker', 'experiment', 'doc']:
        action_parser = subparsers.add_parser(action, help=f'{action.capitalize()} a target.')
        action_parser.add_argument('target', choices=['script', 'run'], help='Target type (script).')
        # the argument given after target and before any extra options like --tags will be stored in "details"
        action_parser.add_argument('details', nargs='?', help='Details or identifier (optional for list).')
        action_parser.add_argument('extra', nargs=argparse.REMAINDER, help='Extra options (e.g.,  -v)')

    for action in ['load']:
        load_parser = subparsers.add_parser(action, help=f'{action.capitalize()} a target.')
        load_parser.add_argument('target', choices=['cfg'], help='Target type (cfg).')
    
    for action in ['help']:
        action_parser = subparsers.add_parser(action, help=f'{action.capitalize()} a target.')
        action_parser.add_argument('action', help='action type (run).', nargs='?', default=None)
        action_parser.add_argument('target', choices=['script', 'cache', 'repo'], help='Target type (script).', nargs='?', default=None)
        action_parser.add_argument('extra', nargs=argparse.REMAINDER, help='Extra options (e.g.,  -v)')
    
    # Parse arguments
    args = parser.parse_args()

    #logger.info(f"Args = {args}")

    # set log level for MLCFlow if -v/--verbose or -s/--silent is specified
    log_flag_aliases = {
        '-v': '--verbose',
        '-s': '--silent'
        }
    
    log_levels = {
        '--verbose': logging.DEBUG,
        '--silent': logging.WARNING
        }

    # Modify args.extra in place
    args.extra[:] = [log_flag_aliases.get(arg, arg) for arg in args.extra]

    # Set log level based on the first matching flag
    for flag, level in log_levels.items():
        if flag in args.extra:
            logger.setLevel(level)
            args.extra.remove(flag)

    res = utils.convert_args_to_dictionary(args.extra)
    if res['return'] > 0:
        return res
    
    run_args = res['args_dict']

    # handle help in mlcflow
    if args.command in ['help']:
        help_text = ""
        if not args.action and not args.target:
            help_text += main.__doc__
        elif args.action and not args.target:
            if args.action not in ['script', 'cache', 'repo']:
                logger.error(f"Invalid target {args.action}")
                raise Exception(f"""Invalid target {args.action}""")
            else:
                args.target, args.action = args.action, None
            actions = get_action(args.target, default_parent)
            help_text += actions.__doc__
            # iterate through every method
            for method_name, method in inspect.getmembers(actions.__class__, inspect.isfunction):
                method = getattr(actions, method_name)
                if method.__doc__ and not method.__doc__.startswith("_"):
                    help_text += method.__doc__
        elif args.action and args.target and run_args.get('tags'):
            actions = get_action(args.target, default_parent)
            if actions and hasattr(actions, args.command):
                method = getattr(actions, args.command)
                res = method(run_args)
                if res['return'] > 0:
                    logger.error(res.get('error', f"Error in {action}"))
                    raise Exception(f"""An error occurred {res}""")
            else:
                logger.error(f"Error: '{args.command}' is not supported for {args.target}.")
        elif args.action and args.target:
            actions = get_action(args.target, default_parent)
            try:
                method = getattr(actions, args.action)
                help_text += actions.__doc__
                help_text += method.__doc__
            except:
                logger.error(f"Error: '{args.action}' is not supported for {args.target}.")
        if help_text != "":
            print(help_text)
        sys.exit(0)
    
    if hasattr(args, 'repo') and args.repo:
        run_args['repo'] = args.repo
        
    if args.command in ['pull', 'rm', 'add', 'find']:
        if args.target == "repo":
            run_args['repo'] = args.details
  
    if args.command in ['docker', 'experiment', 'doc']:
        if args.target == "run":
            run_args['target'] = 'script' #allowing run to be used for docker run instead of docker script
            args.target = "script"

    if hasattr(args, 'details') and args.details and not utils.is_uid(args.details) and not run_args.get("tags") and args.target in ["script", "cache"]:
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

