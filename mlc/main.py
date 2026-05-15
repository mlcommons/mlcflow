import argparse
import os
import sys
from pathlib import Path
import inspect
import shlex
import unicodedata
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
        # logger.info(f"action = {action}")
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
        indices = self.action_object.get_index().indices
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
                    if set(p_tags).issubset(set(c_tags)) and set(n_tags).isdisjoint(set(c_tags)) and (
                            not uid or uid == res['uid']) and (not alias or alias == res['alias']):
                        it = Item(res['path'], res['repo'])
                        result.append(it)
        # logger.info(result)
        return {'return': 0, 'list': result}
        # indices


mlc_run_cmd = None
_current_target = None


def get_version_info():
    """Return mlcflow version string with commit hash."""
    try:
        from . import __version__
        return f"mlcflow {__version__}"
    except ImportError:
        pass
    try:
        from importlib.metadata import version
        return f"mlcflow {version('mlcflow')}"
    except Exception:
        return "mlcflow (unknown version)"


def _get_repo_hashes():
    """Get git info for all repos. Returns list of (alias, branch, hash, has_local_changes)."""
    import subprocess
    if default_parent is None:
        return []
    results = []
    for repo in default_parent.repos:
        alias = os.path.basename(repo.path)
        git_dir = os.path.join(repo.path, '.git')
        if not os.path.isdir(git_dir):
            continue
        try:
            commit = subprocess.check_output(
                ["git", "-C", repo.path, "rev-parse", "--short", "HEAD"],
                stderr=subprocess.DEVNULL, text=True
            ).strip()
            branch = subprocess.check_output(
                ["git", "-C", repo.path, "rev-parse", "--abbrev-ref", "HEAD"],
                stderr=subprocess.DEVNULL, text=True
            ).strip()
            # Only tracked file changes (ignore untracked files)
            dirty = subprocess.check_output(
                ["git", "-C", repo.path, "status", "--porcelain", "-uno"],
                stderr=subprocess.DEVNULL, text=True
            ).strip()
            results.append((alias, branch, commit, bool(dirty)))
        except Exception:
            pass
    return results


def _report_error(e):
    import traceback
    from .script_action import ScriptExecutionError

    # Log the error with target context
    etype = type(e).__name__ if not isinstance(e, ScriptExecutionError) else ''
    prefix = f'{etype}: ' if etype else ''
    if _current_target:
        logger.error(f"Error during '{_current_target}' action: {prefix}{e}")
    else:
        logger.error(f"{prefix}{e}")

    # Show the last traceback frame from outside the mlcflow package
    tb = traceback.extract_tb(e.__traceback__)
    if tb:
        _mlc_pkg_dir = os.path.dirname(os.path.abspath(__file__))
        # Prefer the last frame outside the mlcflow package
        last = tb[-1]
        for frame in reversed(tb):
            if not os.path.abspath(frame.filename).startswith(_mlc_pkg_dir):
                last = frame
                break
        logger.error(f"  at {last.filename}:{last.lineno} in {last.name}")

    # For script execution errors, show actionable info
    if isinstance(e, ScriptExecutionError):
        script_name = e.script_name
        repo_alias = e.repo_alias
        run_args = e.run_args

        if script_name:
            # Build rerun command with user-facing inputs only
            rerun_parts = ["mlcr", script_name]
            _skip_keys = {
                'mlc_run_cmd', 'tags', 'details', 'path_only', 'p',
                'action', 'target', 'rebuild', 'env', 'script_tags',
                'run_cmd', 'run_final_cmds', 'skip_run_cmd', 'run_cmd_prefix',
                'add_deps_recursive', 'add_deps', 'file_path',
                'quiet', 'real_run', 'fake_run_deps', 'keep_detached',
                'pass_user_group', 'use_host_group_id', 'use_host_user_id',
                'extra_run_args', 'port_maps', 'mounts', 'pre_run_cmds',
                'docker_run_deps',
            }
            for k, v in run_args.items():
                if k in _skip_keys:
                    continue
                if isinstance(v, (dict, list)):
                    continue
                if k.startswith('MLC_') or k.startswith('mlc_'):
                    continue
                rerun_parts.append(f"--{k}={v}")
            rerun_cmd = " ".join(rerun_parts)
            logger.error(f"Failed script: {script_name}")
            logger.error(f"To rerun just the failed part: {rerun_cmd}")

        if e.version_info_file:
            logger.error(f"Dependency versions: {e.version_info_file}")

        # Derive issues URL from repo alias
        issues_url = 'https://github.com/mlcommons/mlperf-automations/issues'
        if repo_alias and '@' in repo_alias:
            issues_url = 'https://github.com/' + \
                repo_alias.replace('@', '/') + '/issues'
        logger.error(
            f"Please file an issue at {issues_url} with the full console log.")

    # Show version and repo commit hashes for debugging
    logger.error(f"{get_version_info()}")
    repo_hashes = _get_repo_hashes()
    if repo_hashes:
        for alias, branch, commit, dirty in repo_hashes:
            marker = " (local changes)" if dirty else ""
            logger.error(f"  {alias}: {branch} {commit}{marker}")


def mlc_expand_short(action, target="script"):
    global mlc_run_cmd
    mlc_run_cmd = shlex.join(sys.argv)
    # Insert the positional argument into sys.argv for the main function
    sys.argv.insert(1, action)
    sys.argv.insert(2, target)

    # Call the main function
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
    except SystemExit:
        raise
    except Exception as e:
        _report_error(e)
        sys.exit(1)


def mlcr():
    mlc_expand_short("run")


def mlcd():
    mlc_expand_short("docker")


def mlca():
    mlc_expand_short("apptainer")


def mlcrr():
    mlc_expand_short("remote-run")


def mlcre():
    mlc_expand_short("remote-experiment")


def mlcrd():
    mlc_expand_short("remote-docker")


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
            # Only show warning if not in path-only mode
            if not run_args.get('path_only'):
                logger.warning(
                    f"""No {target} entry found for the specified input: {run_args}!""")
                logger.info(
                    "Tip: Run 'mlc pull repo' to fetch the latest upstream changes.")
                repo_hashes = _get_repo_hashes()
                for alias, branch, commit, dirty in repo_hashes:
                    if dirty:
                        logger.warning(
                            f"Repo '{alias}' ({branch}) has local changes - 'mlc pull repo' may fail. Commit or stash changes first.")
        else:
            for item in res['list']:
                if run_args.get('path_only'):
                    # Print only the path without logger prefix for
                    # script-friendly output
                    print(item.path)
                else:
                    logger.info(f"""Item path: {item.path}""")
    if action == "reindex":
        if "message" in res:
            logger.info(res['message'])
    if "warnings" in res:
        logger.warning(
            f"{len(res['warnings'])} warning(s) found during the execution of the mlc command.")
        for warning in res["warnings"]:
            logger.warning(
                f"Warning code: {warning['code']}, Discription: {warning['description']}")


if default_parent is None:
    default_parent = Action()


log_flag_aliases = {'-v': '--verbose', '-s': '--silent'}
log_levels = {'--verbose': logging.DEBUG, '--silent': logging.WARNING}


def convert_hyphen_to_underscore_in_args():
    for i, arg in enumerate(sys.argv):
        if arg.startswith("--"):
            # Split --option=value into ("option", "value")
            if "=" in arg:
                name, value = arg[2:].split("=", 1)
                new_name = name.replace("-", "_") if "." not in name else name
                sys.argv[i] = f"--{new_name}={value}"
            else:
                # No value: just convert the option name
                name = arg[2:]
                new_name = name.replace("-", "_")
                sys.argv[i] = f"--{new_name}"


def build_pre_parser():
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument(
        "action",
        nargs="?",
        help="Top-level action (run, build, help, etc.)")
    pre_parser.add_argument(
        "target",
        choices=[
            'run',
            'script',
            'cache',
            'repo',
            'repos',
            'experiment',
            'all'],
        nargs="?",
        help="Target (repo, script, cache, ...)")
    pre_parser.add_argument("-h", "--help", action="store_true")
    return pre_parser


def build_parser(pre_args):
    parser = argparse.ArgumentParser(
        prog="mlc",
        description="Manage repos, scripts, and caches.",
        add_help=False)
    subparsers = parser.add_subparsers(
        dest="command", required=not pre_args.help)

    # General commands
    for action in ['run', 'pull', 'test', 'add', 'show', 'list',
                   'find', 'search', 'rm', 'cp', 'mv', 'help', 'prune']:
        p = subparsers.add_parser(action, add_help=False)
        p.add_argument('target', choices=['repo', 'repos', 'script', 'cache'])
        p.add_argument(
            'details',
            nargs='?',
            help='Details or identifier (optional)')
        p.add_argument('extra', nargs=argparse.REMAINDER)

    # Reindex command (target is optional)
    reindex_parser = subparsers.add_parser('reindex', add_help=False)
    reindex_parser.add_argument(
        'target',
        nargs='?',
        choices=[
            'repo',
            'repos',
            'script',
            'cache',
            'experiment',
            'all'],
        help='Target to reindex (optional, defaults to all)')
    reindex_parser.add_argument(
        'details',
        nargs='?',
        help='Details or identifier (optional)')
    reindex_parser.add_argument('extra', nargs=argparse.REMAINDER)

    # Script-only
    for action in ['docker', 'docker-run', 'apptainer',
                   'experiment', 'remote-run', 'remote-experiment',
                   'remote-docker', 'doc', 'lint']:
        p = subparsers.add_parser(action, add_help=False)
        p.add_argument('target', choices=['script', 'run'])
        p.add_argument(
            'details',
            nargs='?',
            help='Details or identifier (optional)')
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
                logger.setLevel(level)
                args.extra.remove(flag)


def build_run_args(args):
    global mlc_run_cmd
    res = utils.convert_args_to_dictionary(getattr(args, 'extra', []))
    if res['return'] > 0:
        return res

    run_args = res['args_dict']
    if not mlc_run_cmd:
        mlc_run_cmd = shlex.join(
            [os.path.basename(sys.argv[0]), *sys.argv[1:]])
    run_args['mlc_run_cmd'] = mlc_run_cmd

    if args.command in ['pull', 'rm', 'add', 'find'] and args.target == "repo":
        run_args['repo'] = args.details

    if args.command in ['docker', 'docker-run', 'apptainer', 'experiment',
                        'remote-run', 'remote-experiment',
                        'remote-docker', 'doc', 'lint'] and args.target == "run":
        # run_args['target'] = 'script' #dont modify this as script might have
        # target as in input
        args.target = "script"

    if args.details and not utils.is_uid(args.details) and not run_args.get(
            "tags") and args.target in ["script", "cache"]:
        run_args['tags'] = args.details

    if not run_args.get('details') and args.details:
        run_args['details'] = args.details

    if args.command in ["cp", "mv"]:
        run_args['target'] = args.target
        if args.details:
            run_args['src'] = args.details
        if args.extra:
            run_args['dest'] = args.extra[0]

    if hasattr(args, 'command') and args.command == "reindex":
        if hasattr(args, 'target') and args.target:
            run_args['reindex_target'] = args.target

    # Check for path-only flag (for script-friendly output)
    if run_args.get('path_only') or run_args.get('p'):
        run_args['path_only'] = True

    return run_args


def is_quoted(arg):
    return (arg.startswith("'") and arg.endswith("'")) or \
           (arg.startswith('"') and arg.endswith('"'))


def check_raw_arguments_for_non_ascii():
    bad_args = []

    # Skip sys.argv[0] (script name)
    for arg in sys.argv[1:]:
        if is_quoted(arg):
            continue  # allow non-ASCII inside quotes
        for ch in arg:
            if ord(ch) > 127:   # non-ASCII
                bad_args.append((arg, ch, unicodedata.name(ch, "UNKNOWN")))
                break  # report each arg once

    if bad_args:
        print("\n⚠️  ERROR: Non-ASCII characters detected in command-line arguments!\n")
        for arg, ch, name in bad_args:
            print(f"  → Argument: {arg}")
            print(f"    Contains non-ASCII character: '{ch}' ({name})")
        print("\nThis often happens due to copy-paste from PDFs or documents.\n"
              "Please retype the arguments using plain ASCII.\n")
        sys.exit(1)


def main():
    """
    MLCFlow is a CLI tool for managing repos, scripts, and caches.
    This framework is designed to streamline automation workflows for MLPerf benchmarks more efficiently.
    You can also use this tool for any of your workflow automation tasks.

    MLCFlow CLI operates using actions and targets. It enables users to perform actions on specified targets using the following syntax:

    mlc <action> <target> [options]

    Here, actions represent the operations to be performed, and the target is the object on which the action is executed.

    Each target has a specific set of actions to tailor automation workflows, as shown below:

    | Target  | Actions                                                   |
    |---------|-----------------------------------------------------------|
    | script  | run, find/search, rm, mv, cp, add, test, docker-run, show |
    | cache   | find/search, rm, show                                     |
    | repo    | pull, search, rm, list, find/search                       |

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

    check_raw_arguments_for_non_ascii()
    convert_hyphen_to_underscore_in_args()

    # Handle version before argparse to avoid --version conflicting with
    # script arguments like --version=3.4
    if len(sys.argv) >= 2 and sys.argv[1] in ('--version', '-V', 'version'):
        print(get_version_info())
        sys.exit(0)

    pre_parser = build_pre_parser()
    pre_args, remaining_args = pre_parser.parse_known_args()

    parser = build_parser(pre_args)
    # Force full parsing for reindex command even without target, or if there
    # are remaining args or target
    args = parser.parse_args() if (
        remaining_args or pre_args.target or pre_args.action == 'reindex') else pre_args

    if hasattr(args, 'command') and args.command:
        args.command = args.command.replace("-", "_")

    configure_logging(args)
    run_args = build_run_args(args) if hasattr(args, "command") else {}

    if pre_args.help and not "tags" in run_args:
        help_text = ""
        if pre_args.target == "run":
            if pre_args.action.startswith(
                    "docker") or pre_args.action == "apptainer":
                pre_args.target = "script"
            else:
                logger.error(
                    f"Invalid action-target {pre_args.action} - {pre_args.target} combination")
                raise Exception(
                    f"Invalid action-target {pre_args.action} - {pre_args.target} combination")
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
            for method_name, method in inspect.getmembers(
                    actions.__class__, inspect.isfunction):
                method = getattr(actions, method_name)
                if method.__doc__ and not method.__doc__.startswith("_"):
                    help_text += method.__doc__
        elif pre_args.action and pre_args.target:
            actions = get_action(pre_args.target, default_parent)
            try:
                method = getattr(actions, pre_args.action)
                help_text += actions.__doc__
                help_text += method.__doc__
            except BaseException:
                logger.error(
                    f"Error: '{pre_args.action}' is not supported for {pre_args.target}.")
        if help_text != "":
            print(help_text)
        sys.exit(0)

    if hasattr(args, 'target') and args.target == "repos":
        args.target = "repo"

    # Handle reindex command specially - it can work without a target or with
    # 'all'
    if hasattr(args, 'command') and args.command == "reindex":
        if not hasattr(
                args, 'target') or not args.target or args.target == "all":
            # Reindex all targets by using the base Action class
            args.target = "script"  # Use script as default to get access to the action

    # Check if command attribute exists
    if not hasattr(args, 'command'):
        logging.error("Error: No command specified.")
        sys.exit(1)

    global _current_target
    _current_target = args.target

    action = get_action(args.target, default_parent)

    if not action or not hasattr(action, args.command):
        logging.error(
            "Error: '%s' is not supported for %s.",
            args.command,
            args.target)
        sys.exit(1)

    method = getattr(action, args.command)
    res = method(run_args)
    if res['return'] > 0:
        logging.error(res.get('error', f"Error in {action}"))
        sys.exit(1)

    process_console_output(res, args.target, args.command, run_args)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
    except SystemExit:
        raise
    except Exception as e:
        _report_error(e)
        sys.exit(1)
