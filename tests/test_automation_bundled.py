import os
import tempfile
import unittest
from unittest.mock import patch

from mlc.action import Action
from mlc.repo import Repo
from mlc.script_action import ScriptAction


class BundledAutomationTest(unittest.TestCase):
    """automation/ now ships inside mlcflow itself (migrated from
    mlperf-automations). These tests guard the loader path that resolves and
    dynamically imports it, independent of any registered/pulled repo.
    """

    def test_bundled_automation_path_resolves_script_dir(self):
        action = Action()
        script_dir = action.bundled_automation_path("script")

        self.assertIsNotNone(script_dir)
        self.assertTrue(os.path.isdir(script_dir))
        self.assertTrue(os.path.isfile(os.path.join(script_dir, "module.py")))

    def test_find_target_folder_prefers_bundled_with_no_registered_repos(self):
        action = Action()
        action.repos = []  # no repos registered at all

        script_dir = action.find_target_folder("script")

        self.assertIsNotNone(script_dir)
        self.assertEqual(script_dir, action.bundled_automation_path("script"))

    def test_find_target_folder_falls_back_to_registered_repo_when_bundled_missing(self):
        # Guards the dev-override escape hatch: if the bundled engine is
        # ever absent, find_target_folder must still fall back to scanning
        # registered repos (the pre-migration behavior) instead of returning
        # None outright.
        with tempfile.TemporaryDirectory() as tmp_repo:
            custom_script_dir = os.path.join(tmp_repo, "automation", "script")
            os.makedirs(custom_script_dir)

            action = Action()
            # non-empty meta avoids Repo._load_meta() (falsy `meta={}` would
            # trigger it, and there's no meta.yaml/meta.json in tmp_repo)
            action.repos = [Repo(tmp_repo, meta={"alias": "tmp-repo"})]

            with patch.object(Action, "bundled_automation_path", return_value=None):
                script_dir = action.find_target_folder("script")

            self.assertEqual(script_dir, custom_script_dir)

    def test_dynamic_import_module_loads_script_automation(self):
        action = Action()
        module_path = os.path.join(
            action.bundled_automation_path("script"), "module.py")

        script_action = ScriptAction(action)
        module = script_action.dynamic_import_module(module_path)

        self.assertTrue(hasattr(module, "ScriptAutomation"))


if __name__ == "__main__":
    unittest.main()
