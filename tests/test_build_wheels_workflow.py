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
        cls.steps = cls.workflow["jobs"]["build_wheels"]["steps"]
        cls.steps_by_name = {
            step["name"]: step
            for step in cls.steps
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
        publish_step = next(
            step for step in self.steps
            if step.get("name") == "Publish to PyPI"
        )

        self.assertIn(
            'gh release view "$RELEASE_REF_NAME"',
            release_step["run"])
        self.assertIn(
            'gh release upload "$RELEASE_REF_NAME" dist/* --clobber',
            release_step["run"],
        )
        self.assertEqual(publish_step["with"]["skip-existing"], "true")

    def test_checkout_uses_app_token_for_protected_branch_pushes(self):
        token_step = self.steps_by_name["Generate GitHub App token"]
        checkout_step = next(
            step for step in self.steps if step.get("uses", "").startswith("actions/checkout@")
        )

        self.assertEqual(token_step["uses"], "actions/create-github-app-token@v1")
        self.assertEqual(
            token_step["with"]["app-id"],
            "${{ secrets.MLC_AUTOMATIONS_APP_ID }}",
        )
        self.assertEqual(
            checkout_step["with"]["token"],
            "${{ steps.app-token.outputs.token }}",
        )

    def test_prepare_release_from_main_updates_main_before_tagging(self):
        prepare_step = self.steps_by_name["Prepare release from main"]
        run_script = prepare_step["run"]

        self.assertIn(
            "A previous attempt already created ${current_release_tag} from main.",
            run_script)
        self.assertIn(
            "Re-run this workflow against tag ${current_release_tag}, or dispatch from main with an explicit version override to cut a different release.",
            run_script)
        self.assertIn(
            "printf '%s\\n' \"${new_version}\" > VERSION",
            run_script)
        self.assertIn(
            "Reusing unreleased VERSION ${new_version} from main.",
            run_script)
        self.assertIn(
            "git commit -m \"Bump VERSION to ${new_version}\"",
            run_script)
        self.assertIn(
            "git push origin HEAD:main",
            run_script)
        self.assertIn(
            "git tag \"${release_tag}\" \"${release_commit}\"",
            run_script)
        self.assertIn(
            "git push origin \"refs/tags/${release_tag}\"",
            run_script)
        self.assertLess(
            run_script.index("git push origin HEAD:main"),
            run_script.index("git tag \"${release_tag}\" \"${release_commit}\""),
        )
        self.assertIn(
            'echo "RELEASE_REF_TYPE=tag" >> "$GITHUB_ENV"',
            run_script)
        self.assertIn(
            'echo "RELEASE_REF_NAME=${release_tag}" >> "$GITHUB_ENV"',
            run_script)

    def test_release_step_uses_app_token_for_github_release_mutations(self):
        release_step = self.steps_by_name["Create GitHub Release"]

        self.assertEqual(
            release_step["env"]["GH_TOKEN"],
            "${{ steps.app-token.outputs.token }}",
        )

    def test_workflow_serializes_release_runs(self):
        concurrency = self.workflow["concurrency"]

        self.assertEqual(concurrency["group"], "build-wheels-release")
        self.assertEqual(concurrency["cancel-in-progress"], "false")


if __name__ == "__main__":
    unittest.main()
