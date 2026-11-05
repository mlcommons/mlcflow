"""
--help for script actions: composite actions (mlcsr, mlcsa, mlcrd, ...) show
the help of every action they wrap, and every user-facing option read by the
automation code is documented in the matching help.
"""
import ast
import glob
import os
import re
import subprocess
import sys
import unittest

_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)

SHORT_COMMANDS = {
    'mlcr': 'run', 'mlcd': 'docker', 'mlca': 'apptainer', 'mlce': 'experiment',
    'mlcrr': 'remote_run', 'mlcrd': 'remote_docker',
    'mlcre': 'remote_experiment', 'mlcsr': 'slurm_run',
    'mlcsd': 'slurm_docker', 'mlcsa': 'slurm_apptainer',
    'mlcse': 'slurm_experiment', 'mlcrs': 'remote_slurm',
    'mlcres': 'remote_slurm_experiment', 'mlcrse': 'remote_slurm_experiment',
    'mlcrsd': 'remote_slurm_docker', 'mlcrsa': 'remote_slurm_apptainer',
}

# Keys read by the code that are internal, not command-line options.
INTERNAL_KEYS = {
    'slurm_action', 'remote_action_cmd', 'remote_run', 'remote_run_prepare',
    'remote_run_settings', 'docker_settings', 'docker_run_deps',
}

# Option prefix -> action whose help must document it.
PREFIX_ACTION = {
    'slurm': 'slurm_run', 'remote': 'remote_run', 'docker': 'docker_run',
    'apptainer': 'apptainer_run',
}


def _help(short_cmd, *extra):
    code = ("import sys; sys.argv = [{!r}] + {!r}; import mlc.main as m; "
            "getattr(m, {!r})()").format(short_cmd, list(extra), short_cmd)
    out = subprocess.run([sys.executable, '-c', code], cwd=_repo_root,
                         capture_output=True, text=True)
    return out.returncode, out.stdout


def _action_header(method_name):
    from mlc.script_action import ScriptAction
    doc = getattr(ScriptAction, method_name).__doc__
    return re.search(r'Action: (\S+)', doc).group(0)


def _read(path):
    with open(path) as f:
        return f.read()


def _options_read_by_code():
    src = ''.join(_read(f) for f in glob.glob(
        os.path.join(_repo_root, 'automation', 'script', '*.py')))
    opts = {p: set(re.findall(r"['\"](%s_[a-z0-9_]+)['\"]" % p, src))
            for p in PREFIX_ACTION}
    for k in re.findall(
            r"get_apptainer_input\(\s*\w+,\s*['\"]([a-z_]+)['\"]", src):
        opts['apptainer'].add('apptainer_' + k)
    for prefix, path, fn in [
            ('docker', 'docker_utils.py', 'prepare_docker_inputs'),
            ('apptainer', 'apptainer.py', 'prepare_apptainer_inputs')]:
        tree = ast.parse(_read(os.path.join(
            _repo_root, 'automation', 'script', path)))
        func = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == fn)
        for node in ast.walk(func):
            target = getattr(node, 'target', None) or (
                node.targets[0] if isinstance(node, ast.Assign) else None)
            if getattr(target, 'id', '') == 'keys' and isinstance(
                    getattr(node, 'value', None), ast.List):
                opts[prefix] |= {f'{prefix}_{e.value}'
                                 for e in node.value.elts}
    return opts


class ShortCommandHelpTest(unittest.TestCase):
    def test_short_commands_show_all_wrapped_actions(self):
        from mlc.script_action import ScriptAction
        for cmd, action in SHORT_COMMANDS.items():
            with self.subTest(cmd=cmd):
                rc, out = _help(cmd, '--help')
                self.assertEqual(rc, 0)
                headers = re.findall(r'Action: \S+', out)
                expected = [_action_header(c)
                            for c in ScriptAction.HELP_COMPONENTS[action]]
                self.assertEqual(headers, expected)

    def test_every_option_is_documented(self):
        from mlc.script_action import ScriptAction
        for prefix, options in _options_read_by_code().items():
            doc = getattr(ScriptAction, PREFIX_ACTION[prefix]).__doc__
            missing = sorted(
                o for o in options - INTERNAL_KEYS
                if not re.search(r'--%s\b' % re.escape(o), doc))
            with self.subTest(prefix=prefix):
                self.assertEqual(missing, [])


if __name__ == '__main__':
    unittest.main()
