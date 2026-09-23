import pathlib
import unittest

import yaml


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "build_wheels.yml"


class BuildWheelsWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with WORKFLOW_PATH.open("r", encoding="utf-8") as file:
            cls.workflow = yaml.load(file, Loader=yaml.BaseLoader)
        cls.steps_by_name = {
            step["name"]: step
            for step in cls.workflow["jobs"]["build_wheels"]["steps"]
            if "name" in step
        }

    def test_workflow_dispatch_accepts_optional_version_input(self):
        version_input = self.workflow["on"]["workflow_dispatch"]["inputs"]["version"]

        self.assertEqual(version_input["required"], "false")
        self.assertEqual(version_input["type"], "string")

    def test_tag_reruns_reject_version_override(self):
        validate_step = self.steps_by_name["Validate workflow_dispatch source"]

        self.assertIn(
            "Version overrides are only supported when dispatching from main.",
            validate_step["run"],
        )

    def test_release_step_is_safe_to_rerun_for_existing_tag(self):
        release_step = self.steps_by_name["Create GitHub Release"]

        self.assertIn('gh release view "$RELEASE_REF_NAME"', release_step["run"])
        self.assertIn(
            'gh release upload "$RELEASE_REF_NAME" dist/* --clobber',
            release_step["run"],
        )

    def test_workflow_serializes_release_runs(self):
        concurrency = self.workflow["concurrency"]

        self.assertEqual(concurrency["group"], "build-wheels-release")
        self.assertEqual(concurrency["cancel-in-progress"], "false")


if __name__ == "__main__":
    unittest.main()
