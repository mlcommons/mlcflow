import tempfile
import unittest
from unittest.mock import patch

from mlc.script_action import ScriptAction


class _Parent:
    def __init__(self, repos_path=None):
        self.repos_path = repos_path


class ScriptActionApptainerTest(unittest.TestCase):
    def test_apptainer_delegates_to_script_module(self):
        action = ScriptAction(_Parent(tempfile.gettempdir()))
        run_args = {"tags": "detect,os"}
        expected = {"return": 0}

        with patch.object(
                ScriptAction,
                "call_script_module_function",
                return_value=expected) as call_script_module_function:
            result = action.apptainer(run_args)

        self.assertEqual(result, expected)
        call_script_module_function.assert_called_once_with(
            "apptainer", run_args)

    def test_auto_pull_uses_fast_forward_only_for_mlperf_automations(self):
        with tempfile.TemporaryDirectory() as repos_path:
            action = ScriptAction(_Parent(repos_path))

            with patch.object(
                    ScriptAction,
                    "find_target_folder",
                    return_value=None), \
                    patch.object(
                        ScriptAction,
                        "access",
                        return_value={"return": 1, "error": "pull failed"}) as access:
                result = action.call_script_module_function("run", {})

            self.assertEqual(result["return"], 1)
            # ignore_on_conflict is part of the contract: the auto-pull is not
            # an explicit `mlc pull repo`, so it must never displace a
            # registered same-uid repo (a version-pinned mlc-scripts, say)
            # with whatever dev HEAD happens to be.
            access.assert_called_once_with({
                "automation": "repo",
                "action": "pull",
                "repo": "mlcommons@mlperf-automations",
                "branch": "dev",
                "ignore_on_conflict": True,
                "fast_forward_only": True
            })


if __name__ == "__main__":
    unittest.main()
