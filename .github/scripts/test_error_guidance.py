from mlc.script_action import ScriptExecutionError
from mlc.main import _report_error, logger
from mlc.error_codes import get_error_guidance
import io
import logging
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..")))


class ErrorGuidanceTest(unittest.TestCase):

    def test_detects_disk_space_errors_from_message(self):
        guidance = get_error_guidance(
            1, "Command execution failed with error code 28. No space left on device.")

        self.assertIsNotNone(guidance)
        self.assertEqual(guidance["error_code"], 28)
        self.assertIn("disk space", guidance["error_message"].lower())
        self.assertTrue(
            any("Free disk space" in s for s in guidance["suggestions"]))

    def test_detects_segmentation_fault_errors(self):
        guidance = get_error_guidance(139, "Segmentation fault (core dumped)")

        self.assertIsNotNone(guidance)
        self.assertEqual(guidance["error_code"], 139)
        self.assertIn("segmentation fault", guidance["error_message"].lower())

    def test_report_error_logs_actionable_guidance(self):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.ERROR)
        logger.addHandler(handler)

        try:
            error = ScriptExecutionError(
                "Script run execution failed.",
                script_name="detect,cpu",
                run_args={"target": "script", "action": "run"},
                error_code=139,
                error_guidance=get_error_guidance(
                    139, "Segmentation fault (core dumped)")
            )

            _report_error(error)
        finally:
            logger.removeHandler(handler)

        output = stream.getvalue()
        self.assertIn("Detected error code: 139", output)
        self.assertIn("Likely cause:", output)
        self.assertIn("Suggestion:", output)


if __name__ == "__main__":
    unittest.main()
