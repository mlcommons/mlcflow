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

        self.assertIn(
            'gh release view "$RELEASE_REF_NAME"',
            release_step["run"])
        self.assertIn(
            'gh release upload "$RELEASE_REF_NAME" dist/* --clobber',
            release_step["run"],
        )

    def test_prepare_release_from_main_keeps_release_state_for_later_steps(self):
        prepare_step = self.steps_by_name["Prepare release from main"]

        self.assertIn("printf '%s\\n' \"${new_version}\" > VERSION", prepare_step["run"])
        self.assertIn("git commit -m \"Bump VERSION to ${new_version}\"", prepare_step["run"])
        self.assertIn("git tag \"${release_tag}\"", prepare_step["run"])
        self.assertIn("git push origin \"${release_tag}\"", prepare_step["run"])
        self.assertIn('echo "RELEASE_COMMIT=${release_commit}" >> "$GITHUB_ENV"', prepare_step["run"])
        self.assertIn('echo "RELEASE_REF_TYPE=tag" >> "$GITHUB_ENV"', prepare_step["run"])
        self.assertIn('echo "RELEASE_REF_NAME=${release_tag}" >> "$GITHUB_ENV"', prepare_step["run"])

    def test_successful_manual_release_updates_main_after_publish(self):
        finalize_step = self.steps_by_name["Update main to released VERSION"]

        self.assertIn('git fetch origin main', finalize_step["run"])
        self.assertIn('git push origin "${RELEASE_COMMIT}:main"', finalize_step["run"])
        self.assertIn(
            "The release tag was published, but the VERSION bump commit was not pushed to main.",
            finalize_step["run"],
        )

    def test_workflow_serializes_release_runs(self):
        concurrency = self.workflow["concurrency"]

        self.assertEqual(concurrency["group"], "build-wheels-release")
        self.assertEqual(concurrency["cancel-in-progress"], "false")


if __name__ == "__main__":
    unittest.main()
