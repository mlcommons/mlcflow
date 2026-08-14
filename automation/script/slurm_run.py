import os
import shlex
import shutil
import subprocess
import copy
from utils import is_true, prune_input
from script.script_utils import *


def slurm_run(self_module, i, slurm_action='run'):
    """
    Run MLC scripts on a SLURM cluster node via srun.

    Args:
        self_module: Reference to the current module for internal calls.
        i: Dictionary containing input parameters for the slurm execution.
        slurm_action: The MLC action to use on the node ('run', 'docker',
            'apptainer', 'experiment'). Defaults to 'run'.

    Returns:
        Dictionary with the result of the operation. Keys:
        - 'return': 0 on success, >0 on error.
        - 'error': Error message (if any).
    """

    # Extract and handle basic inputs
    quiet = i.get('quiet', False)
    logger = self_module.logger
    env = i.get('env', {})

    # SLURM-specific options with reasonable defaults
    slurm_partition = i.get('slurm_partition', '')
    slurm_nodes = i.get('slurm_nodes', '1')
    slurm_ntasks = i.get('slurm_ntasks', '1')
    slurm_ntasks_per_node = i.get('slurm_ntasks_per_node', '')
    slurm_cpus_per_task = i.get('slurm_cpus_per_task', '')
    slurm_gpus = i.get('slurm_gpus', '')
    slurm_gpus_per_node = i.get('slurm_gpus_per_node', '')
    slurm_gpus_per_task = i.get('slurm_gpus_per_task', '')
    slurm_mem = i.get('slurm_mem', '')
    slurm_mem_per_cpu = i.get('slurm_mem_per_cpu', '')
    slurm_mem_per_gpu = i.get('slurm_mem_per_gpu', '')
    slurm_time = i.get('slurm_time', '')
    slurm_job_name = i.get('slurm_job_name', '')
    slurm_output = i.get('slurm_output', '')
    slurm_error = i.get('slurm_error', '')
    slurm_account = i.get('slurm_account', '')
    slurm_qos = i.get('slurm_qos', '')
    slurm_constraint = i.get('slurm_constraint', '')
    slurm_exclusive = i.get('slurm_exclusive', False)
    slurm_export = i.get('slurm_export', 'ALL')
    slurm_srun_extra_args = i.get('slurm_srun_extra_args', '')
    slurm_python_venv = i.get('slurm_python_venv') or 'mlcflow'
    slurm_pull_mlc_repos = i.get('slurm_pull_mlc_repos', False)
    slurm_pre_run_cmds = i.get('slurm_pre_run_cmds', [])
    slurm_post_run_cmds = i.get('slurm_post_run_cmds', [])
    slurm_no_internet = is_true(i.get('slurm_no_internet', False))
    slurm_mlcflow_upgrade = is_true(i.get('slurm_mlcflow_upgrade', False))
    if slurm_mlcflow_upgrade and slurm_no_internet:
        return {
            'return': 1,
            'error': '--slurm_mlcflow_upgrade cannot be combined with --slurm_no_internet: the SLURM node has no network access to upgrade mlcflow.'
        }

    # Normalize str → list so a single command string doesn't get iterated
    # char-by-char
    if isinstance(slurm_pre_run_cmds, str):
        slurm_pre_run_cmds = [slurm_pre_run_cmds] if slurm_pre_run_cmds else []
    if isinstance(slurm_post_run_cmds, str):
        slurm_post_run_cmds = [
            slurm_post_run_cmds] if slurm_post_run_cmds else []

    # Check that srun is available before proceeding
    if not shutil.which('srun'):
        return {
            'return': 1,
            'error': "srun not found in PATH -- are you on a SLURM login node?"
        }

    # Validate and normalize integer SLURM parameters
    int_params = {
        'slurm_nodes': slurm_nodes,
        'slurm_ntasks': slurm_ntasks,
        'slurm_ntasks_per_node': slurm_ntasks_per_node,
        'slurm_cpus_per_task': slurm_cpus_per_task,
    }
    for param_name, param_val in int_params.items():
        if param_val != '':
            try:
                int(param_val)
            except (ValueError, TypeError):
                return {
                    'return': 1,
                    'error': f'Invalid value for {param_name}: {param_val!r} (must be an integer)'
                }
    slurm_nodes = str(int(slurm_nodes)) if slurm_nodes else ''
    slurm_ntasks = str(int(slurm_ntasks)) if slurm_ntasks else ''
    slurm_ntasks_per_node = str(
        int(slurm_ntasks_per_node)) if slurm_ntasks_per_node else ''
    slurm_cpus_per_task = str(
        int(slurm_cpus_per_task)) if slurm_cpus_per_task else ''

    prune_result = prune_input(
        {'input': i, 'extra_keys_starts_with': ['slurm_']})
    if prune_result['return'] > 0:
        return prune_result

    run_input = prune_result['new_input']

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

    env = self_module.env
    state = self_module.state

    i_copy = copy.deepcopy(i)
    i_copy['run_cmd'] = run_input
    i_copy['slurm_action'] = slurm_action

    r = regenerate_script_cmd(i_copy)
    if r['return'] > 0:
        return r

    script_run_cmd = r['run_cmd_string']

    if quiet:
        script_run_cmd += ' --quiet'

    # Build the commands to run inside srun
    run_cmds = []

    # Bootstrap mlcflow on the node
    if slurm_no_internet:
        # Use installer from local mlcflow repo or pre-downloaded copy
        installer_path = _get_local_installer()
        run_cmds.append(
            f'bash {shlex.quote(installer_path)} --yes --venv-dir {shlex.quote(slurm_python_venv)}')
    else:
        upgrade_flag = ' --upgrade' if slurm_mlcflow_upgrade else ''
        run_cmds.append(
            f'curl -sSL https://raw.githubusercontent.com/mlcommons/mlcflow/refs/heads/dev/docs/install/mlcflow_unix_installer.sh | bash -s -- --yes --venv-dir {shlex.quote(slurm_python_venv)}{upgrade_flag}')
    run_cmds.append(build_venv_activation_command(slurm_python_venv))

    if is_true(slurm_pull_mlc_repos):
        run_cmds.append('mlc pull repo')

    # Pre-run commands (after mlcflow is available)
    run_cmds.extend(slurm_pre_run_cmds)

    # The actual script command
    run_cmds.append(script_run_cmd)

    # Post-run commands
    run_cmds.extend(slurm_post_run_cmds)

    # Join all commands with && so failure stops execution
    combined_cmd = ' && '.join(run_cmds)

    # Build srun command
    srun_args = []
    srun_args.append('srun')

    if slurm_partition:
        srun_args.extend(['--partition', slurm_partition])
    if slurm_nodes:
        srun_args.extend(['--nodes', str(slurm_nodes)])
    if slurm_ntasks:
        srun_args.extend(['--ntasks', str(slurm_ntasks)])
    if slurm_ntasks_per_node:
        srun_args.extend(['--ntasks-per-node', str(slurm_ntasks_per_node)])
    if slurm_cpus_per_task:
        srun_args.extend(['--cpus-per-task', str(slurm_cpus_per_task)])
    if slurm_gpus:
        srun_args.extend(['--gpus', str(slurm_gpus)])
    if slurm_gpus_per_node:
        srun_args.extend(['--gpus-per-node', str(slurm_gpus_per_node)])
    if slurm_gpus_per_task:
        srun_args.extend(['--gpus-per-task', str(slurm_gpus_per_task)])
    if slurm_mem:
        srun_args.extend(['--mem', str(slurm_mem)])
    if slurm_mem_per_cpu:
        srun_args.extend(['--mem-per-cpu', str(slurm_mem_per_cpu)])
    if slurm_mem_per_gpu:
        srun_args.extend(['--mem-per-gpu', str(slurm_mem_per_gpu)])
    if slurm_time:
        srun_args.extend(['--time', str(slurm_time)])
    if slurm_job_name:
        srun_args.extend(['--job-name', slurm_job_name])
    if slurm_output:
        srun_args.extend(['--output', slurm_output])
    if slurm_error:
        srun_args.extend(['--error', slurm_error])
    if slurm_account:
        srun_args.extend(['--account', slurm_account])
    if slurm_qos:
        srun_args.extend(['--qos', slurm_qos])
    if slurm_constraint:
        srun_args.extend(['--constraint', slurm_constraint])
    if is_true(slurm_exclusive):
        srun_args.append('--exclusive')
    if slurm_export:
        srun_args.extend(['--export', slurm_export])

    # Append any extra srun arguments the user provided
    if slurm_srun_extra_args:
        srun_args.extend(shlex.split(slurm_srun_extra_args))

    # Wrap the combined command in bash -c for srun
    srun_args.extend(['bash', '-c', combined_cmd])

    logger.info(f'Running on SLURM: {shlex.join(srun_args)}')

    rc = subprocess.call(srun_args)

    if rc != 0:
        return {'return': 1,
                'error': f'srun exited with return code {rc}'}

    return {'return': 0}


def regenerate_script_cmd(i):
    """
    Rebuild the mlcr/mlcd/mlce/mlca command string from the pruned input dict.
    """

    i_run_cmd = i['run_cmd']
    slurm_action = i.get('slurm_action', 'run')

    action_to_cmd = {
        'run': 'mlcr',
        'docker': 'mlcd',
        'apptainer': 'mlca',
        'experiment': 'mlce',
    }
    run_cmd = action_to_cmd.get(slurm_action, 'mlcr')

    def rebuild_flags(command_dict, prefix):
        command_line = ""
        keys = sorted(command_dict.keys(), key=lambda x: x != "tags")

        for key in keys:
            full_key = f"{prefix}.{key}" if prefix else key
            value = command_dict[key]

            if isinstance(value, dict):
                if value:
                    command_line += rebuild_flags(value, full_key)
            elif isinstance(value, list):
                if value:
                    list_values = ",".join(
                        shlex.quote(str(item)) for item in value)
                    command_line += f" --{full_key},={list_values}"
            else:
                if full_key in ['s', 'v']:
                    command_line += f" -{full_key}"
                else:
                    command_line += f" --{full_key}={shlex.quote(str(value))}"

        return command_line

    run_cmd += rebuild_flags(i_run_cmd, "")

    return {'return': 0, 'run_cmd_string': run_cmd}


def slurm_docker(self_module, i):
    """Run an MLC docker script on a SLURM cluster node via srun."""
    return slurm_run(self_module, i, slurm_action='docker')


def slurm_apptainer(self_module, i):
    """Run an MLC apptainer script on a SLURM cluster node via srun."""
    return slurm_run(self_module, i, slurm_action='apptainer')


def slurm_experiment(self_module, i):
    """Run an MLC experiment on a SLURM cluster node via srun."""
    return slurm_run(self_module, i, slurm_action='experiment')


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
