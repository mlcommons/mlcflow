import unittest
from unittest.mock import patch

from mlc.script_action import ScriptAction


class _Parent:
    pass


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
        call_script_module_function.assert_called_once_with("apptainer", run_args)


if __name__ == "__main__":
    unittest.main()
