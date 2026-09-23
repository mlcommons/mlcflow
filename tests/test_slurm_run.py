"""
Unit tests for slurm_run.py command construction and remote_run.py mapping.
"""
import sys
import os
import shlex
import subprocess
import tempfile
import unittest

# Ensure the automation directory is on sys.path so slurm_run / remote_run
# can be imported without a full mlcflow install.
_automation_dir = os.path.join(
    os.path.dirname(__file__), '..', 'automation'
)
_automation_dir = os.path.abspath(_automation_dir)
if _automation_dir not in sys.path:
    sys.path.insert(0, _automation_dir)


# ---------------------------------------------------------------------------
# remote_run.regenerate_script_cmd — remote_action → mlc command mapping
# ---------------------------------------------------------------------------
class TestRemoteRunMapping(unittest.TestCase):
    def _regenerate(self, remote_action, run_cmd=None):
        from script.remote_run import regenerate_script_cmd
        i = {
            'remote_action': remote_action,
            'run_cmd': run_cmd or {'tags': 'detect,os'},
            'remote_run_settings': {},
            'fake_run': False,
        }
        result = regenerate_script_cmd(i)
        self.assertEqual(result['return'], 0)
        return result['run_cmd_string']

    def test_docker_maps_to_mlcd(self):
        self.assertTrue(self._regenerate('docker').startswith('mlcd'))

    def test_experiment_maps_to_mlce(self):
        self.assertTrue(self._regenerate('experiment').startswith('mlce'))

    def test_slurm_run_maps_to_mlcsr(self):
        self.assertTrue(self._regenerate('slurm-run').startswith('mlcsr'))

    def test_slurm_experiment_maps_to_mlcse(self):
        # Regression test for blocker #1: was falling through to 'mlcr'
        self.assertTrue(self._regenerate(
            'slurm-experiment').startswith('mlcse'))

    def test_slurm_docker_maps_to_mlcsd(self):
        self.assertTrue(self._regenerate('slurm-docker').startswith('mlcsd'))

    def test_slurm_apptainer_maps_to_mlcsa(self):
        self.assertTrue(self._regenerate(
            'slurm-apptainer').startswith('mlcsa'))

    def test_unknown_action_defaults_to_mlcr(self):
        self.assertTrue(self._regenerate('unknown-action').startswith('mlcr'))

    def test_run_action_defaults_to_mlcr(self):
        self.assertTrue(self._regenerate('run').startswith('mlcr'))


class TestVenvActivationCommand(unittest.TestCase):
    def _activation_fixture(self, base_dir, venv_dir):
        requested_path = os.path.join(base_dir, venv_dir)
        resolved_path = (
            f"{requested_path}_{os.uname().machine}_py"
            f"{sys.version_info[0]}.{sys.version_info[1]}"
        )
        os.makedirs(os.path.join(resolved_path, 'bin'), exist_ok=True)
        with open(os.path.join(resolved_path, 'bin', 'activate'), 'w', encoding='utf-8') as f:
            f.write(f'export ACTIVATED_TO={shlex.quote(resolved_path)}\n')
        return requested_path, resolved_path

    def _run_activation(self, activation_cmd, cwd, via_eval=False):
        quoted_cmd = shlex.quote(activation_cmd)
        command = (
            f'cmd={quoted_cmd}; eval "$cmd"; printf "%s" "$ACTIVATED_TO"'
            if via_eval else
            f'{activation_cmd}; printf "%s" "$ACTIVATED_TO"'
        )
        completed = subprocess.run(
            ['bash', '-lc', command],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        return completed.stdout

    def test_remote_command_activates_resolved_suffix_venv_through_eval(self):
        from script.script_utils import build_venv_activation_command
        with tempfile.TemporaryDirectory() as temp_dir:
            requested_path, resolved_path = self._activation_fixture(
                temp_dir, 'mlcflow')
            activation_cmd = build_venv_activation_command('mlcflow')

            activated_path = self._run_activation(
                activation_cmd,
                cwd=temp_dir,
                via_eval=True,
            )

        self.assertEqual(activated_path, resolved_path)
        self.assertNotEqual(activated_path, requested_path)

    def test_slurm_command_activates_resolved_suffix_venv_in_bash_c(self):
        from script.script_utils import build_venv_activation_command
        with tempfile.TemporaryDirectory() as temp_dir:
            requested_path, resolved_path = self._activation_fixture(
                temp_dir, 'mlcflow')
            activation_cmd = build_venv_activation_command('mlcflow')

            activated_path = self._run_activation(
                activation_cmd,
                cwd=temp_dir,
            )

        self.assertEqual(activated_path, resolved_path)
        self.assertNotEqual(activated_path, requested_path)

    def test_activation_command_parses_inside_double_quoted_export(self):
        from script.script_utils import build_venv_activation_command
        activation_cmd = build_venv_activation_command('mlcflow')
        escaped_cmd = activation_cmd.replace('"', '\\"')
        expected = f"['{activation_cmd}']"
        shell_script = (
            f'export MLC_SSH_RUN_COMMANDS="[\'{escaped_cmd}\']"\n'
            'printf "%s" "$MLC_SSH_RUN_COMMANDS"\n'
        )
        completed = subprocess.run(
            ['bash', '-lc', shell_script],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertEqual(completed.stdout, expected)


class TestRemoteRunIsolation(unittest.TestCase):
    def _invoke_remote_run(self, **run_args):
        """Return (result, captured_remote_input) from a mocked remote_run call."""
        from unittest.mock import patch, MagicMock
        from script.remote_run import remote_run

        mock_self = MagicMock()
        mock_self._select_script.return_value = {
            'return': 0,
            'script': MagicMock(
                meta={'tags': [], 'alias': 'detect-os', 'uid': '0' * 16},
                path='/fake/path'
            )
        }
        mock_self.update_run_state_for_selected_script_and_variations.return_value = {
            'return': 0}
        mock_self.run_state = {'remote_run': {}}
        mock_self.env = {}
        mock_self.state = {}
        mock_self.logger = MagicMock()

        captured_remote_input = {}

        def fake_access(input_dict):
            captured_remote_input.update(input_dict)
            return {'return': 0}

        mock_self.action_object = MagicMock()
        mock_self.action_object.access.side_effect = fake_access

        with patch('script.remote_run.call_remote_run_prepare',
                   return_value={'return': 0, 'files_to_copy': [], 'remote_env': {}}), \
                patch('script.remote_run.regenerate_script_cmd',
                      return_value={'return': 0, 'run_cmd_string': 'true'}), \
                patch('script.remote_run._get_local_installer', return_value='/bin/true'), \
                patch('script.remote_run.build_venv_activation_command',
                      return_value='true'):
            args = {
                'tags': 'detect,os',
                'mlc_run_cmd': 'mlcr detect,os',
                'env': {},
                **run_args
            }
            result = remote_run(mock_self, args)

        return result, captured_remote_input

    def _capture_remote_run_cmds(self, **run_args):
        result, captured = self._invoke_remote_run(**run_args)
        self.assertEqual(result['return'], 0)
        return captured['run_cmds']

    def test_remote_isolated_sets_tmp_mlc_repos_and_cleanup(self):
        run_cmds = self._capture_remote_run_cmds(remote_isolated=True)
        combined = " ; ".join(run_cmds)
        # The isolated temp dir is now a Python-generated UUID-based literal path
        # so there are no shell variables that would be expanded locally.
        self.assertRegex(
            combined,
            r'MLC_ISOLATED_TMP_DIR="/tmp/mlcflow-isolated-[0-9a-f]+"')
        self.assertRegex(
            combined,
            r'mkdir -p "/tmp/mlcflow-isolated-[0-9a-f]+" \|\| exit 1')
        # Workspace is created with restricted permissions so other users on a
        # shared remote host cannot read it.
        self.assertRegex(
            combined,
            r'chmod 700 "/tmp/mlcflow-isolated-[0-9a-f]+"')
        self.assertRegex(
            combined,
            r'\[ -d "/tmp/mlcflow-isolated-[0-9a-f]+" \] \|\| exit 1')
        # No cd: artifact paths stay relative so rsync can write to them before
        # the isolated dir is created by the command payload.
        self.assertNotIn('cd "/tmp/mlcflow-isolated-', combined)
        self.assertRegex(
            combined,
            r'export MLC_REPOS="/tmp/mlcflow-isolated-[0-9a-f]+/MLC"')
        # The trap body uses the literal path (no inner quoting needed — the
        # path only contains safe characters).  Inner backslash-escaped quotes
        # caused convert_env_to_script to corrupt MLC_SSH_CMD in the env file.
        self.assertRegex(
            combined,
            r'trap "rm -rf /tmp/mlcflow-isolated-[0-9a-f]+" EXIT INT TERM HUP')

    def test_remote_isolated_supports_custom_tmp_base_dir(self):
        run_cmds = self._capture_remote_run_cmds(
            remote_isolated=True,
            remote_isolated_base_dir='/scratch/mlcflow',
        )
        combined = " ; ".join(run_cmds)
        self.assertRegex(
            combined,
            r'MLC_ISOLATED_TMP_DIR="/scratch/mlcflow/mlcflow-isolated-[0-9a-f]+"')
        self.assertRegex(
            combined,
            r'mkdir -p "/scratch/mlcflow/mlcflow-isolated-[0-9a-f]+" \|\| exit 1')
        # The base directory must already exist — a typo produces a hard error.
        self.assertIn(
            '[ -d "/scratch/mlcflow" ] || {', combined)

    def test_remote_isolated_errors_when_combined_with_remote_no_internet(
            self):
        result, _ = self._invoke_remote_run(
            remote_isolated=True,
            remote_no_internet=True,
        )
        self.assertGreater(result['return'], 0)
        self.assertIn('remote_no_internet', result.get('error', ''))

    def test_remote_isolated_command_survives_remote_escaping_and_cleans_up(
            self):
        # Use a unique per-run marker file so parallel CI runs do not collide.
        with tempfile.NamedTemporaryFile(
                prefix='mlcflow_remote_iso_', suffix='.txt', delete=False) as f:
            marker_file = f.name
        os.remove(marker_file)  # we only need the path; bash will create it

        try:
            run_cmds = self._capture_remote_run_cmds(
                remote_isolated=True,
                remote_pre_run_cmds=[
                    f'printf "%s" "$MLC_ISOLATED_TMP_DIR" > {marker_file}'],
            )
            # Strip any curl/installer commands that require internet access or
            # files that don't exist locally – we only need to test isolation
            # setup and cleanup.
            run_cmds = [c for c in run_cmds if not c.startswith('curl ')]
            cmd_string = " ; ".join(run_cmds)
            # Match remote-run-commands escaping pipeline behavior.
            cmd_string = cmd_string.replace("'", "'\\''")
            safe_cmd_string = shlex.quote(cmd_string)
            completed = subprocess.run(
                ['bash', '-lc', f'cmd={safe_cmd_string}; eval "$cmd"'],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, msg=completed.stderr)
            with open(marker_file, 'r', encoding='utf-8') as f:
                isolated_tmp_dir = f.read().strip()
            self.assertTrue(isolated_tmp_dir)
            self.assertFalse(os.path.exists(isolated_tmp_dir))
        finally:
            if os.path.exists(marker_file):
                os.remove(marker_file)

    def test_remote_isolated_copy_directory_stays_relative_for_rsync(self):
        """copy_directory (rsync target) must stay relative so rsync can write to it.

        Files are rsynced before the remote command payload runs — which is the
        payload that creates the isolated dir via mkdir.  If copy_directory were
        set to the absolute isolated path, rsync would fail because the target
        does not yet exist.  Artifact paths must remain relative (home-relative);
        only MLC_REPOS is redirected to the isolated dir.
        """
        from unittest.mock import patch, MagicMock
        from script.remote_run import remote_run

        mock_self = MagicMock()
        mock_self._select_script.return_value = {
            'return': 0,
            'script': MagicMock(
                meta={'tags': [], 'alias': 'detect-os', 'uid': '0' * 16},
                path='/fake/path'
            )
        }
        mock_self.update_run_state_for_selected_script_and_variations.return_value = {
            'return': 0}
        mock_self.run_state = {'remote_run': {}}
        mock_self.env = {}
        mock_self.state = {}
        mock_self.logger = MagicMock()

        captured_remote_input = {}

        def fake_access(input_dict):
            captured_remote_input.update(input_dict)
            return {'return': 0}

        mock_self.action_object = MagicMock()
        mock_self.action_object.access.side_effect = fake_access

        with patch('script.remote_run.call_remote_run_prepare',
                   return_value={'return': 0,
                                 'files_to_copy': ['/fake/some_artifact.txt'],
                                 'remote_env': {}}), \
                patch('script.remote_run.regenerate_script_cmd',
                      return_value={'return': 0, 'run_cmd_string': 'true'}), \
                patch('script.remote_run._get_local_installer', return_value='/bin/true'), \
                patch('script.remote_run.build_venv_activation_command',
                      return_value='true'):
            result = remote_run(mock_self, {
                'tags': 'detect,os',
                'mlc_run_cmd': 'mlcr detect,os',
                'env': {},
                'remote_isolated': True,
            })

        self.assertEqual(result['return'], 0)
        copy_dir = captured_remote_input.get('copy_directory', '')
        # copy_directory must stay relative (home-dir-relative) so rsync can
        # write to it before the isolated dir is created by the command
        # payload.
        self.assertFalse(copy_dir.startswith('/'),
                         f"copy_directory should be relative (for rsync), got: {copy_dir!r}")
        # The isolated tmp dir must still appear in run_cmds (for MLC_REPOS)
        run_cmds = captured_remote_input.get('run_cmds', [])
        combined = " ; ".join(run_cmds)
        self.assertRegex(combined, r'/tmp/mlcflow-isolated-[0-9a-f]+',
                         "Isolated tmp dir not found in run_cmds")

    def test_remote_isolated_repos_copy_directory_stays_relative_for_rsync(
            self):
        """copy_directory for repo copies must stay relative so rsync can write to it."""
        from unittest.mock import patch
        with patch('script.remote_run.os.listdir', return_value=['demo-repo']), \
                patch('script.remote_run.os.path.isdir', return_value=True):
            result, captured = self._invoke_remote_run(
                remote_isolated=True,
                remote_copy_mlc_repos=['demo-repo'],
            )
        self.assertEqual(result['return'], 0)
        copy_dir = captured.get('copy_directory', '')
        # copy_directory (the rsync target) must stay relative — the isolated dir
        # does not exist yet when rsync runs.
        self.assertFalse(copy_dir.startswith('/'),
                         f"copy_directory should be relative (for rsync), got: {copy_dir!r}")
        # The run_cmds should contain a symlink step that links the relative
        # repos path into MLC_REPOS so mlcflow finds them.
        run_cmds = captured.get('run_cmds', [])
        combined = " ; ".join(run_cmds)
        self.assertIn('MLC/repos', combined)
        self.assertIn('$MLC_REPOS', combined)


# ---------------------------------------------------------------------------
# slurm_run.regenerate_script_cmd — slurm_action → mlc command mapping
# ---------------------------------------------------------------------------
class TestSlurmRunCmdGeneration(unittest.TestCase):
    def _regenerate(self, slurm_action, run_cmd=None):
        from script.slurm_run import regenerate_script_cmd
        i = {
            'slurm_action': slurm_action,
            'run_cmd': run_cmd or {'tags': 'detect,os'},
        }
        result = regenerate_script_cmd(i)
        self.assertEqual(result['return'], 0)
        return result['run_cmd_string']

    def test_run_maps_to_mlcr(self):
        self.assertTrue(self._regenerate('run').startswith('mlcr'))

    def test_docker_maps_to_mlcd(self):
        self.assertTrue(self._regenerate('docker').startswith('mlcd'))

    def test_apptainer_maps_to_mlca(self):
        self.assertTrue(self._regenerate('apptainer').startswith('mlca'))

    def test_experiment_maps_to_mlce(self):
        self.assertTrue(self._regenerate('experiment').startswith('mlce'))

    def test_unknown_defaults_to_mlcr(self):
        self.assertTrue(self._regenerate('unknown').startswith('mlcr'))

    def test_tags_included_in_output(self):
        cmd = self._regenerate('run', run_cmd={'tags': 'detect,os'})
        self.assertIn('detect,os', cmd)

    def test_flag_included_in_output(self):
        cmd = self._regenerate(
            'run',
            run_cmd={
                'tags': 'detect,os',
                'verbose': True})
        self.assertIn('--verbose', cmd)


# ---------------------------------------------------------------------------
# slurm_run string normalization (pre/post run cmds)
# ---------------------------------------------------------------------------
class TestSlurmRunInputNormalization(unittest.TestCase):
    """
    Test that str slurm_pre_run_cmds / slurm_post_run_cmds are wrapped in a
    list instead of being iterated character-by-character.
    The easiest way to test this is to call slurm_run with a mock that
    immediately returns, and inspect the srun_args built.
    """

    def test_pre_run_cmds_str_is_normalized(self):
        """A single str command must not be extended char-by-char."""
        import shutil
        from unittest.mock import patch, MagicMock

        mock_self = MagicMock()
        mock_self._select_script.return_value = {
            'return': 0,
            'script': MagicMock(
                meta={'tags': [], 'alias': 'detect-os', 'uid': '0' * 16},
                path='/fake/path'
            )
        }
        mock_self.update_run_state_for_selected_script_and_variations.return_value = {
            'return': 0}
        mock_self.run_state = {}
        mock_self.env = {}
        mock_self.state = {}
        mock_self.logger = MagicMock()

        captured_args = []

        def fake_call(args):
            captured_args.extend(args)
            return 0

        with patch('script.slurm_run.shutil.which', return_value='/usr/bin/srun'), \
                patch('script.slurm_run.subprocess.call', side_effect=fake_call):
            from script.slurm_run import slurm_run
            result = slurm_run(mock_self, {
                'tags': 'detect,os',
                'slurm_pre_run_cmds': 'module load cuda',
                'env': {},
            })

        # The bash -c combined_cmd should contain 'module load cuda' as a
        # complete token, not individual characters.
        bash_c_cmd = captured_args[-1]  # last element after 'bash', '-c'
        self.assertIn('module load cuda', bash_c_cmd,
                      "Pre-run command string was expanded char-by-char instead of as a whole")

    def test_slurm_isolated_sets_tmp_mlc_repos_and_cleanup(self):
        from unittest.mock import patch, MagicMock

        mock_self = MagicMock()
        mock_self._select_script.return_value = {
            'return': 0,
            'script': MagicMock(
                meta={'tags': [], 'alias': 'detect-os', 'uid': '0' * 16},
                path='/fake/path'
            )
        }
        mock_self.update_run_state_for_selected_script_and_variations.return_value = {
            'return': 0}
        mock_self.run_state = {}
        mock_self.env = {}
        mock_self.state = {}
        mock_self.logger = MagicMock()

        captured_args = []

        def fake_call(args):
            captured_args.extend(args)
            return 0

        with patch('script.slurm_run.shutil.which', return_value='/usr/bin/srun'), \
                patch('script.slurm_run.subprocess.call', side_effect=fake_call):
            from script.slurm_run import slurm_run
            result = slurm_run(mock_self, {
                'tags': 'detect,os',
                'slurm_isolated': True,
                'env': {},
            })

        self.assertEqual(result['return'], 0)
        bash_c_cmd = captured_args[-1]  # last element after 'bash', '-c'
        self.assertIn(
            'MLC_ISOLATED_TMP_DIR="$(mktemp -d)" || exit 1',
            bash_c_cmd)
        self.assertIn(
            '[ -n "$MLC_ISOLATED_TMP_DIR" ] && [ -d "$MLC_ISOLATED_TMP_DIR" ] || exit 1', bash_c_cmd)
        self.assertIn('cd "$MLC_ISOLATED_TMP_DIR" || exit 1', bash_c_cmd)
        self.assertIn('export MLC_REPOS="$PWD/MLC"', bash_c_cmd)
        self.assertIn(
            'trap "rm -rf \\"$MLC_REPOS\\" \\"$MLC_ISOLATED_TMP_DIR\\"" EXIT INT TERM HUP', bash_c_cmd)

    def test_slurm_isolated_supports_custom_tmp_base_dir(self):
        from unittest.mock import patch, MagicMock

        mock_self = MagicMock()
        mock_self._select_script.return_value = {
            'return': 0,
            'script': MagicMock(
                meta={'tags': [], 'alias': 'detect-os', 'uid': '0' * 16},
                path='/fake/path'
            )
        }
        mock_self.update_run_state_for_selected_script_and_variations.return_value = {
            'return': 0}
        mock_self.run_state = {}
        mock_self.env = {}
        mock_self.state = {}
        mock_self.logger = MagicMock()

        captured_args = []

        def fake_call(args):
            captured_args.extend(args)
            return 0

        with patch('script.slurm_run.shutil.which', return_value='/usr/bin/srun'), \
                patch('script.slurm_run.subprocess.call', side_effect=fake_call):
            from script.slurm_run import slurm_run
            result = slurm_run(mock_self, {
                'tags': 'detect,os',
                'slurm_isolated': True,
                'slurm_isolated_base_dir': '/scratch/mlcflow',
                'env': {},
            })

        self.assertEqual(result['return'], 0)
        bash_c_cmd = captured_args[-1]
        self.assertIn(
            'MLC_ISOLATED_TMP_BASE_DIR="/scratch/mlcflow"',
            bash_c_cmd)
        self.assertIn(
            '[ -d "$MLC_ISOLATED_TMP_BASE_DIR" ] || exit 1',
            bash_c_cmd)
        self.assertIn(
            'MLC_ISOLATED_TMP_DIR="$(mktemp -d -p "$MLC_ISOLATED_TMP_BASE_DIR" mlcflow-isolated.XXXXXX)" || exit 1',
            bash_c_cmd)


# ---------------------------------------------------------------------------
# mlcflow upgrade flag tests
# ---------------------------------------------------------------------------
class TestMlcflowUpgradeFlag(unittest.TestCase):
    """Tests for --remote_mlcflow_upgrade and --slurm_mlcflow_upgrade flags."""

    def _make_mock(self):
        from unittest.mock import MagicMock
        mock_self = MagicMock()
        mock_self._select_script.return_value = {
            'return': 0,
            'script': MagicMock(
                meta={'tags': [], 'alias': 'detect-os', 'uid': '0' * 16},
                path='/fake/path'
            )
        }
        mock_self.update_run_state_for_selected_script_and_variations.return_value = {
            'return': 0}
        mock_self.run_state = {}
        mock_self.env = {}
        mock_self.state = {}
        mock_self.logger = MagicMock()
        return mock_self

    def _run_slurm(self, upgrade=False, no_internet=False):
        from unittest.mock import patch
        from script.slurm_run import slurm_run
        captured = []

        def fake_call(args):
            captured.extend(args)
            return 0

        mock_self = self._make_mock()
        with patch('script.slurm_run.shutil.which', return_value='/usr/bin/srun'), \
                patch('script.slurm_run.subprocess.call', side_effect=fake_call):
            result = slurm_run(mock_self, {
                'tags': 'detect,os',
                'env': {},
                'slurm_mlcflow_upgrade': upgrade,
                'slurm_no_internet': no_internet,
            })
        return result, captured

    def test_slurm_upgrade_flag_adds_upgrade_to_installer_cmd(self):
        result, captured = self._run_slurm(upgrade=True)
        bash_c_cmd = captured[-1]
        self.assertIn('--upgrade', bash_c_cmd,
                      "--upgrade should be passed to installer when slurm_mlcflow_upgrade=True")

    def test_slurm_upgrade_flag_absent_by_default(self):
        result, captured = self._run_slurm(upgrade=False)
        bash_c_cmd = captured[-1]
        # The activation/venv path may include 'activate' but --upgrade should not appear
        # in the installer curl command when the flag is off.
        self.assertNotIn('--upgrade', bash_c_cmd,
                         "--upgrade should not appear when slurm_mlcflow_upgrade=False")

    def test_slurm_upgrade_not_standalone_pip(self):
        """The upgrade should go through the installer, not a standalone pip call."""
        result, captured = self._run_slurm(upgrade=True)
        bash_c_cmd = captured[-1]
        self.assertNotIn('pip install --upgrade mlcflow', bash_c_cmd,
                         "Upgrade must go through the installer, not a standalone pip invocation")

    def test_slurm_upgrade_incompatible_with_no_internet(self):
        result, _ = self._run_slurm(upgrade=True, no_internet=True)
        self.assertGreater(result['return'], 0)
        self.assertIn('no_internet', result.get('error', '').lower())

    def test_remote_upgrade_incompatible_with_no_internet(self):
        from script.remote_run import remote_run
        mock_self = self._make_mock()
        result = remote_run(mock_self, {
            'tags': 'detect,os',
            'remote_mlcflow_upgrade': True,
            'remote_no_internet': True,
        })
        self.assertGreater(result['return'], 0)
        self.assertIn('no_internet', result.get('error', '').lower())

    def _run_remote(self, upgrade=False):
        """Call remote_run with mocks; return (result, captured_run_cmds)."""
        from unittest.mock import patch, MagicMock
        from script.remote_run import remote_run

        mock_self = self._make_mock()
        mock_self.action_object = MagicMock()
        captured_run_cmds = []

        def fake_access(inp):
            captured_run_cmds.extend(inp.get('run_cmds', []))
            return {'return': 0}

        mock_self.action_object.access.side_effect = fake_access

        with patch('script.remote_run.regenerate_script_cmd',
                   return_value={'return': 0, 'run_cmd_string': 'mlcr detect,os'}):
            result = remote_run(mock_self, {
                'tags': 'detect,os',
                'mlc_run_cmd': 'mlcr detect,os',
                'env': {},
                'remote_mlcflow_upgrade': upgrade,
            })
        return result, captured_run_cmds

    def test_remote_upgrade_flag_adds_upgrade_to_installer_cmd(self):
        result, run_cmds = self._run_remote(upgrade=True)
        installer_cmd = next(
            (c for c in run_cmds if 'mlcflow_unix_installer' in c), '')
        self.assertIn('--upgrade', installer_cmd,
                      "--upgrade should be passed to installer when remote_mlcflow_upgrade=True")

    def test_remote_upgrade_flag_absent_by_default(self):
        result, run_cmds = self._run_remote(upgrade=False)
        installer_cmd = next(
            (c for c in run_cmds if 'mlcflow_unix_installer' in c), '')
        self.assertNotIn('--upgrade', installer_cmd,
                         "--upgrade should not appear when remote_mlcflow_upgrade=False")

    def test_remote_upgrade_not_standalone_pip(self):
        """The upgrade should go through the installer, not a standalone pip call."""
        result, run_cmds = self._run_remote(upgrade=True)
        self.assertFalse(
            any('pip install --upgrade mlcflow' in c for c in run_cmds),
            "Upgrade must go through the installer, not a standalone pip invocation"
        )


# ---------------------------------------------------------------------------
# copy-back mlc cache — remote_run and slurm_run
# ---------------------------------------------------------------------------
class TestCopyBackMlcCache(unittest.TestCase):
    """Tests for --remote_copy_back_mlc_cache and --slurm_copy_back_mlc_cache."""

    # --- remote_run helpers ---

    def _invoke_remote_run(self, **run_args):
        from unittest.mock import patch, MagicMock
        from script.remote_run import remote_run

        mock_self = MagicMock()
        mock_self._select_script.return_value = {
            'return': 0,
            'script': MagicMock(
                meta={'tags': [], 'alias': 'detect-os', 'uid': '0' * 16},
                path='/fake/path'
            )
        }
        mock_self.update_run_state_for_selected_script_and_variations.return_value = {
            'return': 0}
        mock_self.run_state = {'remote_run': {}}
        mock_self.env = {}
        mock_self.state = {}
        mock_self.logger = MagicMock()

        captured = {}

        def fake_access(inp):
            captured.update(inp)
            return {'return': 0}

        mock_self.action_object = MagicMock()
        mock_self.action_object.access.side_effect = fake_access
        mock_self.action_object.repos_path = '/tmp/test-mlc-repos'

        with patch('script.remote_run.call_remote_run_prepare',
                   return_value={'return': 0, 'files_to_copy': [], 'remote_env': {}}), \
                patch('script.remote_run.regenerate_script_cmd',
                      return_value={'return': 0, 'run_cmd_string': 'true'}), \
                patch('script.remote_run._get_local_installer', return_value='/bin/true'), \
                patch('script.remote_run.build_venv_activation_command',
                      return_value='true'):
            args = {
                'tags': 'detect,os',
                'mlc_run_cmd': 'mlcr detect,os',
                'env': {},
                **run_args}
            result = remote_run(mock_self, args)

        return result, captured

    def test_remote_copy_back_mlc_cache_adds_cache_path(self):
        result, captured = self._invoke_remote_run(
            remote_copy_back_mlc_cache=True)
        self.assertEqual(result['return'], 0)
        files_to_copy_back = captured.get('files_to_copy_back', [])
        self.assertTrue(
            any('local/cache' in f or 'MLC/repos/local/cache' in f for f in files_to_copy_back),
            f"Expected cache path in files_to_copy_back, got: {files_to_copy_back}"
        )

    def test_remote_copy_back_mlc_cache_default_dest(self):
        result, captured = self._invoke_remote_run(
            remote_copy_back_mlc_cache=True)
        self.assertEqual(result['return'], 0)
        dest = captured.get('path_to_copy_back_files', '')
        expected = os.path.join('/tmp/test-mlc-repos', 'local', 'cache')
        self.assertEqual(dest, expected)

    def test_remote_copy_back_mlc_cache_custom_path(self):
        result, captured = self._invoke_remote_run(
            remote_copy_back_mlc_cache=True,
            remote_copy_back_mlc_cache_path='/data/mlc-cache',
        )
        self.assertEqual(result['return'], 0)
        self.assertEqual(
            captured.get('path_to_copy_back_files'),
            '/data/mlc-cache')

    def test_remote_copy_back_mlc_cache_custom_path_overrides_preexisting(
            self):
        """An explicit remote_copy_back_mlc_cache_path always wins."""
        result, captured = self._invoke_remote_run(
            remote_copy_back_mlc_cache=True,
            remote_copy_back_mlc_cache_path='/data/mlc-cache',
            files_to_copy_back=['/some/other/file'],
            path_to_copy_back_files='/previously/set/dest',
        )
        self.assertEqual(result['return'], 0)
        self.assertEqual(
            captured.get('path_to_copy_back_files'),
            '/data/mlc-cache')

    def test_remote_copy_back_mlc_cache_isolated_stages_cache_before_cleanup(
            self):
        result, captured = self._invoke_remote_run(
            remote_copy_back_mlc_cache=True,
            remote_isolated=True,
        )
        self.assertEqual(result['return'], 0)
        files_to_copy_back = captured.get('files_to_copy_back', [])
        self.assertIn(
            'mlc-remote-artifacts/local/cache',
            files_to_copy_back,
            f"Expected staged cache path, got: {files_to_copy_back}"
        )
        post_run_cmds = captured.get('post_run_cmds', [])
        self.assertTrue(
            any(
                'cp -a' in cmd and
                '/tmp/mlcflow-isolated-' in cmd and
                'mlc-remote-artifacts/local/cache' in cmd
                for cmd in post_run_cmds
            ),
            f"Expected isolated cache staging command, got: {post_run_cmds}"
        )

    def test_remote_no_copy_back_when_flag_absent(self):
        result, captured = self._invoke_remote_run()
        self.assertEqual(result['return'], 0)
        self.assertNotIn('files_to_copy_back', captured)
        self.assertNotIn('path_to_copy_back_files', captured)

    # --- slurm_run helpers ---

    def _invoke_slurm_run(self, **run_args):
        from unittest.mock import patch, MagicMock
        from script.slurm_run import slurm_run

        mock_self = MagicMock()
        mock_self._select_script.return_value = {
            'return': 0,
            'script': MagicMock(
                meta={'tags': [], 'alias': 'detect-os', 'uid': '0' * 16},
                path='/fake/path'
            )
        }
        mock_self.update_run_state_for_selected_script_and_variations.return_value = {
            'return': 0}
        mock_self.run_state = {}
        mock_self.env = {}
        mock_self.state = {}
        mock_self.logger = MagicMock()
        mock_self.action_object = MagicMock()
        mock_self.action_object.repos_path = '/tmp/test-mlc-repos'

        captured_args = []

        def fake_call(args):
            captured_args.extend(args)
            return 0

        with patch('script.slurm_run.shutil.which', return_value='/usr/bin/srun'), \
                patch('script.slurm_run.subprocess.call', side_effect=fake_call):
            args = {'tags': 'detect,os', 'env': {}, **run_args}
            result = slurm_run(mock_self, args)

        bash_c_cmd = captured_args[-1] if captured_args else ''
        return result, bash_c_cmd

    def test_slurm_copy_back_mlc_cache_isolated_adds_rsync(self):
        result, bash_c_cmd = self._invoke_slurm_run(
            slurm_isolated=True,
            slurm_copy_back_mlc_cache=True,
        )
        self.assertEqual(result['return'], 0)
        self.assertIn('rsync', bash_c_cmd)
        self.assertIn('$MLC_REPOS/local/cache', bash_c_cmd)
        self.assertIn('/tmp/test-mlc-repos/local/cache', bash_c_cmd)

    def test_slurm_copy_back_mlc_cache_isolated_uses_custom_path(self):
        result, bash_c_cmd = self._invoke_slurm_run(
            slurm_isolated=True,
            slurm_copy_back_mlc_cache=True,
            slurm_copy_back_mlc_cache_path='/scratch/my-cache',
        )
        self.assertEqual(result['return'], 0)
        self.assertIn('/scratch/my-cache', bash_c_cmd)

    def test_slurm_copy_back_mlc_cache_no_rsync_without_flag(self):
        result, bash_c_cmd = self._invoke_slurm_run(slurm_isolated=True)
        self.assertEqual(result['return'], 0)
        self.assertNotIn('rsync', bash_c_cmd)

    def test_slurm_copy_back_mlc_cache_non_isolated_no_explicit_path_is_noop(
            self):
        """Without a path and not isolated, no rsync command is added."""
        result, bash_c_cmd = self._invoke_slurm_run(
            slurm_copy_back_mlc_cache=True)
        self.assertEqual(result['return'], 0)
        self.assertNotIn('rsync', bash_c_cmd)

    def test_slurm_copy_back_mlc_cache_non_isolated_with_explicit_path(self):
        result, bash_c_cmd = self._invoke_slurm_run(
            slurm_copy_back_mlc_cache=True,
            slurm_copy_back_mlc_cache_path='/shared/cache',
        )
        self.assertEqual(result['return'], 0)
        self.assertIn('rsync', bash_c_cmd)
        self.assertIn('/shared/cache', bash_c_cmd)


if __name__ == '__main__':
    unittest.main()
