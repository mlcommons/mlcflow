"""
Tests for container/slurm command rebuilding: mlc_run_cmd is not forwarded,
unresolved <<<VAR>>> placeholders are dropped, values survive tmp-run.sh,
apptainer bind mounts reach the definition-file build, and the script index
heals entries missing from it.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
_automation_dir = os.path.join(_repo_root, 'automation')
for _p in (_repo_root, _automation_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _bash_argv(script_lines, var):
    """Source script_lines in bash, word-split $var as the shell would when
    eval'ing it, and return the resulting argv."""
    with tempfile.NamedTemporaryFile('w', suffix='.sh', delete=False) as f:
        f.write('\n'.join(script_lines) + '\n')
        path = f.name
    try:
        out = subprocess.run(
            ['bash', '-c',
             f'. "{path}" && eval "set -- ${var}" && printf "%s\\0" "$@"'],
            capture_output=True, check=True)
    finally:
        os.unlink(path)
    return out.stdout.decode().split('\0')[:-1]


class QuoteIfNeededTest(unittest.TestCase):
    def test_plain_value_unquoted(self):
        from utils import quote_if_needed
        self.assertEqual(quote_if_needed('detect,os'), 'detect,os')

    def test_shell_metachars_quoted(self):
        from utils import quote_if_needed
        for v in ['a b', '<<<X>>>', 'a;b', 'a|b', 'a&b', "it's"]:
            self.assertEqual(quote_if_needed(v), f'"{v}"')

    def test_double_quote_value_single_quoted(self):
        from utils import quote_if_needed
        self.assertEqual(quote_if_needed('say "hi"'), '\'say "hi"\'')


class DockerUtilsRegenerateTest(unittest.TestCase):
    def _regen(self, run_cmd):
        from script.docker_utils import regenerate_script_cmd
        r = regenerate_script_cmd({
            'script_uid': 'x', 'script_alias': 'x', 'tags': [],
            'run_cmd': run_cmd})
        self.assertEqual(r['return'], 0)
        return r['run_cmd_string']

    def test_drops_mlc_run_cmd(self):
        cmd = self._regen({
            'tags': 'detect,os',
            'mlc_run_cmd': "mlcsa x '--slurm_pre_run_cmds,=a > b'"})
        self.assertNotIn('mlc_run_cmd', cmd)

    def test_drops_placeholder_list_items(self):
        cmd = self._regen({'tags': 't', 'env': {
            'L': ['keep', '<<<UNRESOLVED>>>'], 'S': '<<<X>>>'}})
        self.assertNotIn('<<<', cmd)
        self.assertIn('--env.L,=keep', cmd)

    def test_values_survive_tmp_run_export(self):
        # Mirrors run-apptainer-container: the container command is written
        # to tmp-run.sh as `export VAR="..."` and later word-split by bash.
        from script.module import convert_env_to_script
        cmd = self._regen({
            'tags': 't',
            'extra_sys_deps': 'apt-get install -y "libfoo"',
            'repos': 'amd@mlperf-automations,mlc',
            'note': "it's a test",
        })
        lines = convert_env_to_script(
            {'MLC_RUN_CMD': cmd},
            {'platform': 'linux', 'set_env': 'export ${key}="${value}"',
             'env_separator': ':'})
        argv = _bash_argv(lines, 'MLC_RUN_CMD')
        self.assertIn('--extra_sys_deps=apt-get install -y "libfoo"', argv)
        self.assertIn('--repos=amd@mlperf-automations,mlc', argv)
        self.assertIn("--note=it's a test", argv)


class SlurmRegenerateTest(unittest.TestCase):
    def test_drops_mlc_run_cmd_and_placeholders(self):
        from script.slurm_run import regenerate_script_cmd
        r = regenerate_script_cmd({
            'slurm_action': 'apptainer',
            'run_cmd': {
                'tags': 't',
                'mlc_run_cmd': "mlcsa t '--x=a b'",
                'env': {'MLC_AOCC_DIR_PATH': '<<<MLC_AOCC_LATEST_DIR_PATH>>>',
                        'KEEP': 'v'}}})
        cmd = r['run_cmd_string']
        self.assertTrue(cmd.startswith('mlca '))
        self.assertNotIn('mlc_run_cmd', cmd)
        self.assertNotIn('<<<', cmd)
        self.assertIn('--env.KEEP=v', cmd)


class ApptainerBindTest(unittest.TestCase):
    def test_build_binds_include_user_and_local_dir(self):
        from script.apptainer import get_apptainer_bind_mounts
        with tempfile.TemporaryDirectory() as d:
            binds = get_apptainer_bind_mounts(
                {'apptainer_bind': '/scratch',
                 'apptainer_host_mlc_repos': 'yes',
                 'apptainer_mlc_local_dir': d},
                {}, {}, {})
            self.assertEqual(
                binds, ['/scratch', f'{d}:/opt/mlc_host_repos/local'])

    def test_local_dir_needs_host_repos(self):
        from script.apptainer import get_mlc_local_bind
        self.assertEqual(
            get_mlc_local_bind({'apptainer_mlc_local_dir': '/tmp/x'}), '')


class IndexMissingEntryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.rp = self.tmp.name
        self.repo_path = os.path.join(self.rp, 'repo')
        for name in ['index_script.json', 'index_cache.json',
                     'index_experiment.json']:
            with open(os.path.join(self.rp, name), 'w') as f:
                json.dump([], f)

    def _make_script(self, name, uid):
        d = os.path.join(self.repo_path, 'script', name)
        os.makedirs(d)
        meta = os.path.join(d, 'meta.yaml')
        with open(meta, 'w') as f:
            json.dump({'uid': uid, 'alias': name, 'tags': [name],
                       'automation_alias': 'script',
                       'automation_uid': '5b4e0237da074764'}, f)
        return meta

    def _seed_mtimes(self, metas):
        with open(os.path.join(self.rp, 'modified_times.json'), 'w') as f:
            json.dump({m: {'mtime': os.path.getmtime(m)} for m in metas}, f)

    def _indexed(self):
        with open(os.path.join(self.rp, 'index_script.json')) as f:
            return sorted(e['alias'] for e in json.load(f))

    def _repo(self):
        from mlc.repo import Repo
        return Repo(path=self.repo_path, meta={'alias': 'repo'})

    def test_reindexes_entry_tracked_in_mtimes_but_missing(self):
        from mlc.index import Index
        meta = self._make_script('benchmark-hpc', 'a' * 16)
        self._seed_mtimes([meta])
        Index(self.rp, [self._repo()])
        self.assertEqual(self._indexed(), ['benchmark-hpc'])

    def test_duplicate_uid_not_reindexed(self):
        from mlc.index import Index
        m1 = self._make_script('one', 'a' * 16)
        m2 = self._make_script('two', 'a' * 16)
        with open(os.path.join(self.rp, 'index_script.json'), 'w') as f:
            json.dump([{'uid': 'a' * 16, 'alias': 'one', 'tags': ['one'],
                        'path': os.path.dirname(m1), 'repo': 'repo'}], f)
        self._seed_mtimes([m1, m2])
        Index(self.rp, [self._repo()])
        self.assertEqual(self._indexed(), ['one'])


if __name__ == '__main__':
    unittest.main()
