import tempfile
import unittest
from unittest.mock import patch

from mlc.script_action import ScriptAction


class _Parent:
    def __init__(self):
        self.repos_path = tempfile.gettempdir()


class ScriptActionApptainerTest(unittest.TestCase):
    def test_apptainer_delegates_to_script_module(self):
        action = ScriptAction(_Parent())
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
        action = ScriptAction(_Parent())

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
        access.assert_called_once_with({
            "automation": "repo",
            "action": "pull",
            "repo": "mlcommons@mlperf-automations",
            "branch": "dev",
            "fast_forward_only": True
        })


if __name__ == "__main__":
    unittest.main()
