import argparse
import os
import sys
from pathlib import Path
import inspect
import shlex
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
            if tags or uid or i.get('all'):
                for res in target_index:
                    c_tags = res["tags"]
                    if set(p_tags).issubset(set(c_tags)) and set(n_tags).isdisjoint(set(c_tags)) and (not uid or uid == res['uid']) and (not alias or alias == res['alias']):
                        it = Item(res['path'], res['repo'])
                        result.append(it)
        #logger.info(result)
        return {'return': 0, 'list': result}
        #indices


def mlc_expand_short(action, target = "script"):

    # Insert the positional argument into sys.argv for the main function
    sys.argv.insert(1, action)
    sys.argv.insert(2, target)

    # Call the main function
    main()

def mlcr():
    mlc_expand_short("run")
def mlcd():
    mlc_expand_short("docker")
def mlce():
    mlc_expand_short("experiment")
def mlct():
    mlc_expand_short("test")

def mlcp():
    mlc_expand_short("pull", "repo")


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


log_flag_aliases = {'-v': '--verbose', '-s': '--silent'}
log_levels = {'--verbose': logging.DEBUG, '--silent': logging.WARNING}


def build_pre_parser():
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("action", nargs="?", help="Top-level action (run, build, help, etc.)")
    pre_parser.add_argument("target", choices=['run', 'script', 'cache', 'repo'], nargs="?", help="Target (repo, script, cache, ...)")
    pre_parser.add_argument("-h", "--help", action="store_true")
    return pre_parser


def build_parser(pre_args):
    parser = argparse.ArgumentParser(prog="mlc", description="Manage repos, scripts, and caches.", add_help=False)
    subparsers = parser.add_subparsers(dest="command", required=not pre_args.help)

    # General commands
    for action in ['run', 'pull', 'test', 'add', 'show', 'list', 'find', 'search', 'rm', 'cp', 'mv', 'help']:
        p = subparsers.add_parser(action, add_help=False)
        p.add_argument('target', choices=['repo', 'script', 'cache'])
        p.add_argument('details', nargs='?', help='Details or identifier (optional)')
        p.add_argument('extra', nargs=argparse.REMAINDER)

    # Script-only
    for action in ['docker', 'docker-run', 'experiment', 'doc', 'lint']:
        p = subparsers.add_parser(action, add_help=False)
        p.add_argument('target', choices=['script', 'run'])
        p.add_argument('details', nargs='?', help='Details or identifier (optional)')
        p.add_argument('extra', nargs=argparse.REMAINDER)

    # Load cfg
    load_parser = subparsers.add_parser("load", add_help=False)
    load_parser.add_argument("target", choices=["cfg"])
    return parser


def configure_logging(args):
    if hasattr(args, 'extra') and args.extra:
        args.extra[:] = [log_flag_aliases.get(a, a) for a in args.extra]
        for flag, level in log_levels.items():
            if flag in args.extra:
                logging.getLogger().setLevel(level)
                args.extra.remove(flag)


def build_run_args(args):
    res = utils.convert_args_to_dictionary(getattr(args, 'extra', []))
    if res['return'] > 0:
        return res

    run_args = res['args_dict']
    run_args['mlc_run_cmd'] = shlex.join(sys.argv)

    if args.command in ['pull', 'rm', 'add', 'find'] and args.target == "repo":
        run_args['repo'] = args.details

    if args.command in ['docker', 'docker-run', 'experiment', 'doc', 'lint'] and args.target == "run":
        run_args['target'] = 'script'
        args.target = "script"

    if args.details and not utils.is_uid(args.details) and not run_args.get("tags") and args.target in ["script", "cache"]:
        run_args['tags'] = args.details

    if not run_args.get('details') and args.details:
        run_args['details'] = args.details

    if args.command in ["cp", "mv"]:
        run_args['target'] = args.target
        if args.details:
            run_args['src'] = args.details
        if args.extra:
            run_args['dest'] = args.extra[0]

    return run_args


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
    | script  | run, find/search, rm, mv, cp, add, test, docker-run, show |
    | cache   | find/search, rm, show                                 |
    | repo    | pull, search, rm, list, find/search                   |
    
    Example:
      mlc run script detect-os
      
    For help related to a particular target, run: 
    
    mlc <target> --help/-h

    Examples:
      mlc script --help
      mlc repo -h
    
    For help related to a specific action for a target, run: 
    
    mlc <action> <target> --help/-h
    Examples:
      mlc run script --help
      mlc pull repo -h
    """
    pre_parser = build_pre_parser()
    pre_args, remaining_args = pre_parser.parse_known_args()

    parser = build_parser(pre_args)
    args = parser.parse_args() if remaining_args or pre_args.target else pre_args
    
    if hasattr(args, 'command') and args.command:
        args.command = args.command.replace("-", "_")

    configure_logging(args)
    run_args = build_run_args(args) if hasattr(args, "command") else {}

    if pre_args.help and not "tags" in run_args:
        help_text = ""
        if pre_args.target == "run":
            if pre_args.action.startswith("docker"):
                pre_args.target = "script"
            else:
                logger.error(f"Invalid action-target {pre_args.action} - {pre_args.target} combination")
                raise Exception(f"Invalid action-target {pre_args.action} - {pre_args.target} combination")
        if not pre_args.action and not pre_args.target:
            help_text += main.__doc__
        elif pre_args.action and not pre_args.target:
            if pre_args.action not in ['script', 'cache', 'repo']:
                logger.error(f"Invalid target {pre_args.action}")
                raise Exception(f"""Invalid target {pre_args.action}""")
            else:
                pre_args.target, pre_args.action = pre_args.action, None
            actions = get_action(pre_args.target, default_parent)
            help_text += actions.__doc__
            # iterate through every method
            for method_name, method in inspect.getmembers(actions.__class__, inspect.isfunction):
                method = getattr(actions, method_name)
                if method.__doc__ and not method.__doc__.startswith("_"):
                    help_text += method.__doc__
        elif pre_args.action and pre_args.target:
            actions = get_action(pre_args.target, default_parent)
            try:
                method = getattr(actions, pre_args.action)
                help_text += actions.__doc__
                help_text += method.__doc__
            except:
                logger.error(f"Error: '{pre_args.action}' is not supported for {pre_args.target}.")
        if help_text != "":
            print(help_text)
        sys.exit(0)

    action = get_action(args.target, default_parent)

    if not action or not hasattr(action, args.command):
        logging.error("Error: '%s' is not supported for %s.", args.command, args.target)
        sys.exit(1)

    method = getattr(action, args.command)
    res = method(run_args)
    if res['return'] > 0:
        logging.error(res.get('error', f"Error in {action}"))
        raise Exception(f"An error occurred {res}")

    process_console_output(res, args.target, args.command, run_args)

if __name__ == '__main__':
    main()

