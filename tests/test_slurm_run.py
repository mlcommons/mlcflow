"""
Unit tests for slurm_run.py command construction and remote_run.py mapping.
"""
import sys
import os
import subprocess
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
    def test_command_defers_marker_expansion_until_runtime(self):
        from script.script_utils import build_venv_activation_command

        activation_cmd = build_venv_activation_command('mlcflow')

        completed = subprocess.run(
            [
                'bash',
                '-lc',
                (
                    'unset MLCFLOW_VENV; '
                    'cmd=' + repr(activation_cmd) + '; '
                    'printf "__CMD__:%s\\n" "$cmd"'
                ),
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        self.assertIn(
            '__CMD__:MLCFLOW_VENV=$(cat mlcflow/.mlcflow_venv_path 2>/dev/null || echo mlcflow) && . "$MLCFLOW_VENV/bin/activate"',
            completed.stdout,
        )


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


if __name__ == '__main__':
    unittest.main()
