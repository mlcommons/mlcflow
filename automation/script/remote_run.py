from collections import defaultdict
import os
import shlex
import uuid
import mlc.utils as utils
from mlc import utils
from utils import *
import logging
from pathlib import PureWindowsPath, PurePosixPath
import time
import copy
from datetime import datetime
from script.script_utils import *
import platform


def _get_local_mlc_cache_path(self_module):
    repos_path = getattr(
        getattr(self_module, 'action_object', None), 'repos_path', '')
    if not isinstance(repos_path, str) or not repos_path:
        repos_path = os.path.join(os.path.expanduser("~"), "MLC", "repos")
    return os.path.join(repos_path, 'local', 'cache')


def remote_run(self_module, i):
    """
    Remote run of MLC scripts.

    Args:
        self_module: Reference to the current module for internal calls.
        i: Dictionary containing input parameters for the experiment execution.

    Returns:
        Dictionary with the result of the operation. Keys:
        - 'return': 0 on success, >0 on error.
        - 'error': Error message (if any).
    """

    # Extract and handle basic inputs
    quiet = i.get('quiet', False)
    show_time = i.get('show_time', False)
    logger = self_module.logger
    env = i.get('env', {})
    remote_host = i.get('remote_host', 'localhost')
    remote_port = i.get('remote_port', '22')
    remote_action = i.get('remote_action', 'run')
    remote_shell = i.get('remote_shell', '')
    remote_no_internet = is_true(i.get('remote_no_internet', False))
    remote_mlcflow_upgrade = is_true(i.get('remote_mlcflow_upgrade', False))
    remote_copy_back_mlc_cache = is_true(i.get('remote_copy_back_mlc_cache', False))
    remote_copy_back_mlc_cache_path = i.get('remote_copy_back_mlc_cache_path', '')
    if remote_mlcflow_upgrade and remote_no_internet:
        return {
            'return': 1,
            'error': '--remote_mlcflow_upgrade cannot be combined with --remote_no_internet: the remote node has no network access to upgrade mlcflow.'
        }
    remote_isolated = is_true(i.get('remote_isolated', False))
    remote_isolated_base_dir = i.get('remote_isolated_base_dir', '')

    prune_result = prune_input(
        {'input': i, 'extra_keys_starts_with': ['remote_']})
    if prune_result['return'] > 0:
        return prune_result

    run_input = prune_result['new_input']
    mlc_run_cmd = run_input['mlc_run_cmd']

    # print(script_cmd)
    cur_dir = os.getcwd()

    r = self_module._select_script(i)
    if r['return'] > 0:
        return r

    script = r['script']

    meta, script_path = script.meta, script.path
    tags, script_alias, script_uid = meta.get(
        "tags", []), meta.get(
        'alias', ''), meta.get(
        'uid', '')

    r = self_module.update_run_state_for_selected_script_and_variations(
        script, i)
    if r['return'] > 0:
        return r

    run_state = self_module.run_state
    remote_run_settings = run_state.get('remote_run', {})
    remote_run_settings_default_env = remote_run_settings.get(
        'default_env', {})
    for key in remote_run_settings_default_env:
        env.setdefault(key, remote_run_settings_default_env[key])

    remote_env = {}

    env = self_module.env
    state = self_module.state

    files_to_copy_back = i.get('files_to_copy_back', [])
    path_to_copy_back_files = i.get('path_to_copy_back_files', '')
    skip_ssh_key_file = i.get('skip_ssh_key_file', '')

    r = call_remote_run_prepare(self_module, meta, script, i)
    if r['return'] > 0:
        return r

    files_to_copy = r.get('files_to_copy', [])

    remote_env = r.get('remote_env', {})

    mlc_script_input = {
        'action': remote_action, 'target': 'script'
    }

    run_cmds = []
    remote_mlc_python_venv = i.get('remote_python_venv') or 'mlcflow'
    run_cmds_start_index = 0
    remote_copy_directory = i.get(
        "remote_copy_directory",
        "mlc-remote-artifacts")

    remote_copy_directory_for_cmd = remote_copy_directory

    # For isolated mode, generate a unique temp dir path in Python rather than
    # using shell constructs like $(mktemp -d).  Shell variable references such
    # as $PWD, $(mktemp -d) and $MLC_ISOLATED_TMP_DIR inside run_cmds end up
    # stored in env['MLC_SSH_CMD'], which convert_env_to_script wraps in
    # double-quotes (export MLC_SSH_CMD="...").  When bash sources that env
    # file, double-quote context expands $PWD and $(mktemp -d) locally and
    # resolves $MLC_ISOLATED_TMP_DIR to empty, causing [ -n "" ] to fail.
    # Using a Python-generated literal path avoids all unintended local
    # expansion.
    _remote_tmp_dir = ''
    if remote_isolated:
        if remote_no_internet:
            return {
                'return': 1,
                'error': '--remote_isolated is incompatible with --remote_no_internet: '
                         'each isolated run re-installs mlcflow into a fresh venv, '
                         'which requires network access on the target host.'
            }
        _uid = uuid.uuid4().hex[:16]
        if remote_isolated_base_dir:
            # Escape shell metacharacters so the value is safe to embed inside
            # double-quoted shell strings (same escaping as slurm_run.py).
            _safe_base = (
                str(remote_isolated_base_dir)
                .replace('\\', '\\\\')
                .replace('"', '\\"')
                .replace('$', '\\$')
                .replace('`', '\\`')
                .rstrip('/')
            )
            _remote_tmp_dir = f'{_safe_base}/mlcflow-isolated-{_uid}'
        else:
            _safe_base = ''
            _remote_tmp_dir = f'/tmp/mlcflow-isolated-{_uid}'
        # Do NOT change remote_copy_directory_for_cmd here.  Files are rsynced
        # to the relative (home-dir-relative) copy_directory BEFORE the remote
        # command payload runs — which is the payload that creates the isolated
        # dir via mkdir.  Pointing copy_directory at the isolated path would
        # mean rsync tries to write to a directory that does not yet exist.
        # Artifact paths stay relative/unchanged; only MLC_REPOS is redirected
        # to the isolated temp dir so that MLC state is contained and cleaned
        # up.
        preamble = [
            f'MLC_ISOLATED_TMP_DIR="{_remote_tmp_dir}"',
        ]
        if remote_isolated_base_dir:
            # Require that the base directory already exists (consistent with
            # slurm_isolated_base_dir behaviour) so a typo is a hard error
            # rather than creating an unexpected directory tree.
            preamble.append(
                f'[ -d "{_safe_base}" ] || {{ echo "remote_isolated_base_dir does not exist: {_safe_base}" >&2; exit 1; }}')
        preamble.extend([
            f'mkdir -p "{_remote_tmp_dir}" || exit 1',
            f'chmod 700 "{_remote_tmp_dir}"',
            f'[ -d "{_remote_tmp_dir}" ] || exit 1',
            f'export MLC_REPOS="{_remote_tmp_dir}/MLC"',
            f'trap "rm -rf {_remote_tmp_dir}" EXIT INT TERM HUP',
        ])
        run_cmds.extend(preamble)
        run_cmds_start_index = len(run_cmds)

    # Determine if the local system is Windows to adjust command formatting
    is_windows = platform.system() == 'Windows'

    # Export user-specified environment variables on the remote shell early,
    # before the installer runs (e.g. LC_ALL for locale, PATH for brew).
    # Usage: --remote_env.LC_ALL=C.UTF-8
    # --remote_env.PATH='$PATH:/opt/homebrew/bin'
    user_remote_env = i.get('remote_env', {})
    if isinstance(user_remote_env, dict):
        for key, value in user_remote_env.items():
            run_cmds.append(f'export {key}={value}')

    # Note: The remote activation command uses Unix syntax because we're SSHing into a (likely) Unix server
    # Even if we're running from Windows locally, the remote commands execute
    # on the remote server
    if remote_no_internet:
        # --remote_no_internet selects the local-installer path; network-requiring
        # operations like --remote_mlcflow_upgrade are already blocked by the
        # guard above.
        installer_local_path = _get_local_installer()
        files_to_copy.append(installer_local_path)
        remote_installer = remote_copy_directory_for_cmd + "/" + \
            os.path.basename(installer_local_path)
        run_cmds.append(
            f'bash "{remote_installer}" --yes --venv-dir {shlex.quote(remote_mlc_python_venv)}')
    else:
        upgrade_flag = ' --upgrade' if remote_mlcflow_upgrade else ''
        run_cmds.append(
            f'curl -sSL https://raw.githubusercontent.com/mlcommons/mlcflow/refs/heads/main/docs/install/mlcflow_unix_installer.sh | bash -s -- --yes --venv-dir {shlex.quote(remote_mlc_python_venv)}{upgrade_flag}')
    run_cmds.append(build_venv_activation_command(remote_mlc_python_venv))
    # is_true() rather than a bare truthiness check: this arrives from the CLI
    # as a string, so '--remote_pull_mlc_repos=no' is a non-empty (truthy)
    # str and would otherwise still pull.
    if is_true(i.get('remote_pull_mlc_repos', False)):
        run_cmds.append("mlc pull repo")

    env_keys_to_copy = remote_run_settings.get('env_keys_to_copy', [])
    input_mapping = meta.get('input_mapping', {})

    for key in env_keys_to_copy:
        if key in env and os.path.exists(env[key]):
            # the files_to_copy list contains the path to files in host
            files_to_copy.append(env[key])
            # Use forward slashes for remote path (Unix/Linux servers)
            remote_env[key] = remote_copy_directory_for_cmd + "/" + \
                os.path.basename(
                env[key])  # if host path is /home/user/file.txt, remote path will be mlc-remote-artifacts/file.txt

            for k, value in input_mapping.items():
                if value == key and k in run_input:
                    run_input[k] = remote_env[key]

    i_copy = copy.deepcopy(i)
    i_copy['run_cmd'] = run_input
    # Avoid passing through the full original command line when rebuilding the
    # nested remote command. It can contain shell-quoted arguments (for example
    # quoted SSH key paths) that lead to invalid nested quoting in the SSH
    # wrapper.
    i_copy['run_cmd'].pop('mlc_run_cmd', None)

    r = regenerate_script_cmd(i_copy)
    if r['return'] > 0:
        return r
    # " ".join(mlc_run_cmd.split(" ")[1:])
    script_run_cmd = r['run_cmd_string']

    # Propagate --quiet to the remote mlcr command so MLC skips interactive
    # prompts (e.g. file selection) that cause EOFError in CI/non-interactive.
    if quiet:
        script_run_cmd += ' --quiet'

    if remote_env:
        for key in remote_env:
            script_run_cmd += f" --env.{key}={remote_env[key]}"

    remote_pre_run_cmds = i.get('remote_pre_run_cmds', [])
    remote_post_run_cmds = i.get('remote_post_run_cmds', [])
    if isinstance(remote_post_run_cmds, str):
        remote_post_run_cmds = [remote_post_run_cmds] if remote_post_run_cmds else []
    elif remote_post_run_cmds is None:
        remote_post_run_cmds = []
    else:
        remote_post_run_cmds = list(remote_post_run_cmds)

    # Insert pre_run_cmds into run_cmds (after install+activate) so they
    # execute with mlcflow available, rather than passing them separately
    # which would place them before the mlcflow bootstrap.
    run_cmds.extend(remote_pre_run_cmds)

    run_cmds.append(f"{script_run_cmd}")

    remote_inputs = {}

    for key in ["host", "port", "user", "client_refresh",
                "password", "skip_host_verify", "ssh_key_file", "copy_directory"]:
        if i.get(f"remote_{key}"):
            remote_inputs[key] = i[f"remote_{key}"]

    if files_to_copy:
        remote_inputs['files_to_copy'] = files_to_copy
        # In isolated mode the SCP target must match the absolute path the
        # commands reference; in normal mode use the (possibly relative)
        # copy_directory as before.
        remote_inputs['copy_directory'] = remote_copy_directory_for_cmd

    # For repo copying, add a separate copy with MLC/repos target
    if i.get('remote_copy_mlc_repos', False):
        local_repos_path = os.path.join(
            os.path.expanduser("~"), "MLC", "repos")
        repos_to_copy = i.get('remote_copy_mlc_repos', [])
        if isinstance(repos_to_copy, bool) or repos_to_copy is True:
            repos_to_copy = [
                d for d in os.listdir(local_repos_path)
                if os.path.isdir(os.path.join(local_repos_path, d))
            ]
        repo_files = [
            os.path.join(local_repos_path, repo)
            for repo in repos_to_copy
            if os.path.isdir(os.path.join(local_repos_path, repo))
        ]
        if repo_files:
            remote_inputs['files_to_copy'] = remote_inputs.get(
                'files_to_copy', []) + repo_files
            remote_mlc_repos_path = i.get("remote_mlc_repos_path", "MLC/repos")
            # In isolated mode the repos are still rsynced to the relative path
            # (home-dir-relative), the same as non-isolated.  The isolated dir
            # is not created until the command payload runs, so pointing
            # copy_directory at a path inside it would fail at rsync time.
            remote_mlc_repos_path_for_cmd = remote_mlc_repos_path
            remote_inputs['copy_directory'] = remote_mlc_repos_path_for_cmd
            # On the remote, if MLC_REPOS is set and differs, symlink so
            # mlcflow finds the copied repos
            run_cmds.insert(run_cmds_start_index,
                            f'if [ -n "$MLC_REPOS" ] && [ "$MLC_REPOS" != "{remote_mlc_repos_path_for_cmd}" ]; then '
                            f'mkdir -p "{remote_mlc_repos_path_for_cmd}" && '
                            f'ln -sfn "$(realpath {remote_mlc_repos_path_for_cmd})"/* "$MLC_REPOS/"; '
                            f'fi')

    if remote_copy_back_mlc_cache:
        if remote_isolated:
            remote_cache_path = f'{_remote_tmp_dir}/MLC/local/cache'
            staged_remote_cache_path = str(
                PurePosixPath(remote_copy_directory_for_cmd) / 'local' / 'cache')
            staged_remote_cache_parent = str(
                PurePosixPath(remote_copy_directory_for_cmd) / 'local')
            remote_post_run_cmds.append(
                f'rm -rf {shlex.quote(staged_remote_cache_path)} && '
                f'mkdir -p {shlex.quote(staged_remote_cache_parent)} && '
                f'if [ -d {shlex.quote(remote_cache_path)} ]; then '
                f'cp -a {shlex.quote(remote_cache_path)} {shlex.quote(staged_remote_cache_path)}; '
                f'else mkdir -p {shlex.quote(staged_remote_cache_path)}; fi'
            )
            remote_cache_path = staged_remote_cache_path
        else:
            remote_cache_path = '~/MLC/repos/local/cache'
        files_to_copy_back.append(remote_cache_path)
        if remote_copy_back_mlc_cache_path:
            path_to_copy_back_files = remote_copy_back_mlc_cache_path
        elif not path_to_copy_back_files:
            path_to_copy_back_files = _get_local_mlc_cache_path(self_module)

    if files_to_copy_back:
        remote_inputs['files_to_copy_back'] = files_to_copy_back

    if path_to_copy_back_files:
        remote_inputs['path_to_copy_back_files'] = path_to_copy_back_files

    if skip_ssh_key_file:
        remote_inputs['skip_ssh_key_file'] = skip_ssh_key_file

    # If a remote shell is specified, pass it to the remote-run-commands script
    if remote_shell:
        remote_inputs["remote_shell"] = remote_shell

    # Execute the remote command
    mlc_remote_input = {
        'action': 'run', 'target': 'script', 'tags': 'remote,run,cmds,ssh',
        'script_tags': i.get('tags'), 'run_cmds': run_cmds,
        'post_run_cmds': remote_post_run_cmds,
        'quiet': quiet,
        **remote_inputs
    }

    r = self_module.action_object.access(mlc_remote_input)
    if r['return'] > 0:
        return r

    return {'return': 0}


def call_remote_run_prepare(self_module, meta, script_item, i):

    path_to_customize_py = os.path.join(script_item.path, 'customize.py')
    logger = self_module.logger
    recursion_spaces = ''

    # Check and run remote_run_prepare in customize.py
    if os.path.isfile(path_to_customize_py) and has_function_in_file(
            path_to_customize_py, "remote_run_prepare"):

        customize_code = load_customize_with_deps(path_to_customize_py)

        customize_common_input = {
            'input': i,
            'automation': self_module,
            'artifact': script_item,
            # 'customize': script_item.meta.get('customize', {}),
            # 'os_info': os_info,
            # 'recursion_spaces': recursion_spaces,
            # 'script_tags': script_tags,
            # 'variation_tags': variation_tags
        }

        run_script_input = {
            "customize_code": customize_code,
            "customize_common_input": customize_common_input,
            "run_state": {},
        }

        ii = copy.deepcopy(customize_common_input)
        ii["meta"] = meta
        ii["env"] = self_module.env
        ii["state"] = self_module.state
        ii["automation"] = self_module
        ii["run_script_input"] = run_script_input

        return customize_code.remote_run_prepare(ii)

    return {'return': 0}


def regenerate_script_cmd(i):

    remote_run_settings = i.get('remote_run_settings', {})
    fake_run = i.get('fake_run', False)
    remote_action = i.get('remote_action', 'run')
    remote_shell = i.get('remote_shell', '')

    i_run_cmd = i['run_cmd']

    # Remove environment variables with host path values
    if 'env' in i_run_cmd:
        env = i_run_cmd['env']
        for key in list(env):
            value = env[key]

            # Check if the value is a string containing the specified paths
            # Use both forward and backward slashes for Windows compatibility
            if isinstance(value, str) and (
                    os.path.join("local", "cache", "") in value or
                    "local/cache/" in value or
                    "local\\cache\\" in value or
                    os.path.join("MLC", "repos", "") in value or
                    "MLC/repos/" in value or
                    "MLC\\repos\\" in value or
                    "<<<" in value
            ):
                del env[key]

            # Check if the value is a list and remove matching items
            elif isinstance(value, list):
                # Identify values to remove
                values_to_remove = [
                    val for val in value
                    if isinstance(val, str) and (
                        os.path.join("local", "cache", "") in val or
                        "local/cache/" in val or
                        "local\\cache\\" in val or
                        os.path.join("MLC", "repos", "") in val or
                        "MLC/repos/" in val or
                        "MLC\\repos\\" in val or
                        "<<<" in val
                    )
                ]

                # Remove key if all values match; otherwise, filter the list
                if len(values_to_remove) == len(value):
                    del env[key]
                else:
                    env[key] = [
                        val for val in value if val not in values_to_remove]

    # docker_run_cmd_prefix = i.get('docker_run_cmd_prefix', '')

    # Regenerate command from dictionary input
    _remote_action_cmd = {
        'docker': 'mlcd',
        'experiment': 'mlce',
        'slurm-run': 'mlcsr',
        'slurm-experiment': 'mlcse',
        'slurm-docker': 'mlcsd',
        'slurm-apptainer': 'mlcsa',
    }
    run_cmd = _remote_action_cmd.get(remote_action, 'mlcr')

    skip_input_for_fake_run = remote_run_settings.get(
        'skip_input_for_fake_run', [])
    add_quotes_to_keys = remote_run_settings.get('add_quotes_to_keys', [])

    def rebuild_flags(
            command_dict,
            is_fake_run,
            skip_keys_for_fake_run,
            quote_keys,
            prefix
    ):
        """
        Recursively rebuilds command-line flags from a dictionary of inputs.

        :param command_dict: Dictionary containing command-line keys and values.
        :param is_fake_run: Boolean indicating if this is a fake run.
        :param skip_keys_for_fake_run: List of keys to skip in fake run mode.
        :param quote_keys: List of keys that require values to be quoted.
        :param prefix: String to prepend to keys for hierarchical keys.
        :return: A reconstructed command-line string.
        """
        command_line = ""

        # Sort keys to ensure 'tags' appears first if present.
        keys = sorted(command_dict.keys(), key=lambda x: x != "tags")

        for key in keys:
            # if key in ["input", "output", "outdirname"]:
            #    continue  # We have the corresponding env keys in container env string
            # Construct the full key with the prefix.
            full_key = f"{prefix}.{key}" if prefix else key

            # Skip keys marked for exclusion in fake run mode.
            if is_fake_run and full_key in skip_keys_for_fake_run:
                continue

            value = command_dict[key]
            quote = '"' if full_key in quote_keys else ""

            # Recursively process nested dictionaries.
            if isinstance(value, dict):
                if value:
                    command_line += rebuild_flags(
                        value,
                        is_fake_run,
                        skip_keys_for_fake_run,
                        quote_keys,
                        full_key
                    )
            # Process lists by concatenating values with commas.
            elif isinstance(value, list):
                if value:
                    list_values = ",".join(
                        quote_if_needed(
                            item, quote) for item in value)
                    command_line += f" --{full_key},={list_values}"
            # Process scalar values.
            else:
                if full_key in ['s', 'v']:
                    command_line += f" -{full_key}"
                else:
                    command_line += f" --{full_key}={quote_if_needed(value, quote)}"

        return command_line

    run_cmd += rebuild_flags(i_run_cmd,
                             fake_run,
                             skip_input_for_fake_run,
                             add_quotes_to_keys,
                             '')

    # run_cmd = docker_run_cmd_prefix + ' && ' + \
    #    run_cmd if docker_run_cmd_prefix != '' else run_cmd

    return {'return': 0, 'run_cmd_string': run_cmd}


INSTALLER_URL = 'https://raw.githubusercontent.com/mlcommons/mlcflow/refs/heads/dev/docs/install/mlcflow_unix_installer.sh'


def _get_local_installer():
    """
    Get the mlcflow installer script locally. First checks if it's available
    in the local mlcflow repo, otherwise downloads it to a temp location.
    Returns the local path to the installer script.
    """
    import tempfile

    # Check if the installer exists in the local mlcflow package
    local_installer = os.path.join(
        os.path.dirname(
            os.path.dirname(
                os.path.dirname(
                    os.path.abspath(__file__)))),
        'docs', 'install', 'mlcflow_unix_installer.sh')
    if os.path.isfile(local_installer):
        return local_installer

    # Download to a temp file
    import urllib.request
    tmp_path = os.path.join(tempfile.gettempdir(), 'mlcflow_unix_installer.sh')
    urllib.request.urlretrieve(INSTALLER_URL, tmp_path)
    return tmp_path
