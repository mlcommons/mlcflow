"""Check --help of every installed short command (and with script tags)."""
import re
import subprocess
import sys

from mlc.script_action import ScriptAction

SHORT_COMMANDS = {
    'mlcr': 'run', 'mlcd': 'docker', 'mlca': 'apptainer', 'mlce': 'experiment',
    'mlcrr': 'remote_run', 'mlcrd': 'remote_docker',
    'mlcre': 'remote_experiment', 'mlcsr': 'slurm_run',
    'mlcsd': 'slurm_docker', 'mlcsa': 'slurm_apptainer',
    'mlcse': 'slurm_experiment', 'mlcrs': 'remote_slurm',
    'mlcres': 'remote_slurm_experiment', 'mlcrse': 'remote_slurm_experiment',
    'mlcrsd': 'remote_slurm_docker', 'mlcrsa': 'remote_slurm_apptainer',
}


def headers(names):
    return [re.search(r'Action: \S+', getattr(ScriptAction, n).__doc__)
            .group(0) for n in names]


def run(cmd):
    out = subprocess.run(cmd, capture_output=True, text=True)
    return out.returncode, out.stdout + out.stderr


failures = []
with_tags = '--with-tags' in sys.argv
for cmd, action in SHORT_COMMANDS.items():
    components = ScriptAction.HELP_COMPONENTS[action]
    errors = []
    for flag in ('--help', '-h'):
        rc, out = run([cmd, flag])
        got = re.findall(r'Action: \S+', out)
        if rc != 0 or got != headers(components):
            errors.append(f'{cmd} {flag}: rc={rc} sections={got}')
    if with_tags:
        # Script help must not run the script, srun, ssh or docker.
        rc, out = run([cmd, 'detect,os', '--help'])
        got = re.findall(r'Action: \S+', out)
        expected = headers([c for c in components if c != 'run'])
        if rc != 0 or got != expected or 'Script Name: detect-os' not in out:
            errors.append(f'{cmd} detect,os --help: rc={rc} sections={got}')
    print(f'{cmd}: ' + ('FAILED' if errors else 'ok'))
    failures += errors

if failures:
    print('\n'.join(failures))
    sys.exit(1)
