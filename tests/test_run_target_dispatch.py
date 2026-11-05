"""`mlc <script-only action> run <tags>` dispatches to the script target."""
import os
import sys
import unittest
from unittest.mock import patch

_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


class RunTargetDispatchTest(unittest.TestCase):
    def test_run_target_maps_to_script_for_every_script_only_action(self):
        import mlc.main as m
        for action in m.SCRIPT_ONLY_ACTIONS:
            with self.subTest(action=action), \
                    patch(f'mlc.script_action.ScriptAction.{action}',
                          return_value={'return': 0}, create=True) as meth, \
                    patch.object(sys, 'argv', [
                        'mlc', action.replace('_', '-'), 'run', 'detect,os']):
                m.main()
                meth.assert_called_once()
                self.assertEqual(meth.call_args[0][0].get('tags'),
                                 'detect,os')

    def test_help_with_run_target(self):
        import mlc.main as m
        for action in ('slurm_run', 'remote_slurm_apptainer', 'docker_run'):
            with self.subTest(action=action), \
                    patch.object(sys, 'argv', [
                        'mlc', action.replace('_', '-'), 'run', '--help']), \
                    patch('builtins.print') as out:
                with self.assertRaises(SystemExit) as ctx:
                    m.main()
                self.assertEqual(ctx.exception.code, 0)
                self.assertIn('Action: Run', ''.join(
                    str(c.args[0]) for c in out.call_args_list if c.args))


if __name__ == '__main__':
    unittest.main()
