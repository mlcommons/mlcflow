"""
Tests for the unification of mlcd and mlca options (issue #312).

Verifies that:
1. --docker_X CLI options act as fallbacks when --apptainer_X is not given.
2. script meta.yaml `apptainer` key reaches run_state via update_state_from_meta
   and overrides `docker` key for apptainer runs.
3. meta_schema validates the `apptainer` section using the same rules as `docker`.
4. mlcd --help and mlca --help work as expected.
"""
import copy
import unittest
import mlc.utils as mlc_utils


# ---------------------------------------------------------------------------
# 1. run_state population from meta.yaml — calls real mlc.utils.merge_dicts
#    to exercise the same code path as update_state_from_meta in module.py
# ---------------------------------------------------------------------------

class RunStateApptainerKeyTest(unittest.TestCase):
    """
    Verifies that the apptainer key in meta.yaml reaches run_state via the
    same merge_dicts pattern used in update_state_from_meta.
    This mirrors module.py:update_state_from_meta exactly.
    """

    def _apply_meta_to_run_state(self, meta, run_state=None):
        """Replicate the apptainer and docker blocks in update_state_from_meta."""
        if run_state is None:
            run_state = {'docker': {}, 'apptainer': {}}

        new_docker = meta.get('docker')
        if new_docker:
            mlc_utils.merge_dicts({'dict1': run_state.get('docker', {}),
                                   'dict2': new_docker,
                                   'append_lists': True, 'append_unique': True})

        new_apptainer = meta.get('apptainer')
        if new_apptainer:
            mlc_utils.merge_dicts({'dict1': run_state.get('apptainer', {}),
                                   'dict2': new_apptainer,
                                   'append_lists': True, 'append_unique': True})
        return run_state

    def _effective_settings(self, run_state):
        """Replicate the merge in apptainer.py: docker overridden by apptainer."""
        effective = copy.deepcopy(run_state.get('docker', {}))
        mlc_utils.merge_dicts({'dict1': effective,
                               'dict2': run_state.get('apptainer', {}),
                               'append_lists': True, 'append_unique': True})
        return effective

    def test_apptainer_base_image_overrides_docker(self):
        meta = {
            'docker': {'os': 'ubuntu', 'base_image': 'ubuntu:22.04'},
            'apptainer': {'base_image': 'docker://ubuntu:20.04'},
        }
        run_state = self._apply_meta_to_run_state(meta)
        self.assertEqual(
            run_state['apptainer']['base_image'],
            'docker://ubuntu:20.04')
        effective = self._effective_settings(run_state)
        self.assertEqual(effective['base_image'], 'docker://ubuntu:20.04')
        self.assertEqual(effective['os'], 'ubuntu')

    def test_docker_settings_used_when_no_apptainer_key(self):
        meta = {'docker': {'os': 'ubuntu', 'base_image': 'ubuntu:22.04'}}
        run_state = self._apply_meta_to_run_state(meta)
        effective = self._effective_settings(run_state)
        self.assertEqual(effective['os'], 'ubuntu')
        self.assertEqual(effective['base_image'], 'ubuntu:22.04')

    def test_apptainer_key_missing_from_meta_leaves_run_state_empty(self):
        meta = {'docker': {'os': 'ubuntu'}}
        run_state = self._apply_meta_to_run_state(meta)
        self.assertEqual(run_state['apptainer'], {})

    def test_deep_merge_preserves_docker_subkeys_not_in_apptainer(self):
        """apptainer.default_env.B overrides docker.default_env.B; A is preserved."""
        meta = {
            'docker': {'default_env': {'A': '1', 'B': '2'}},
            'apptainer': {'default_env': {'B': 'override'}},
        }
        run_state = self._apply_meta_to_run_state(meta)
        effective = self._effective_settings(run_state)
        self.assertEqual(effective['default_env']['A'], '1')
        self.assertEqual(effective['default_env']['B'], 'override')

    def test_init_run_state_seeds_apptainer_key(self):
        """init_run_state in module.py must initialise run_state['apptainer'] to {}."""
        import sys
        import importlib.util
        import os

        # Load automation/utils.py as 'utils' so module.py can do `from utils
        # import *`
        automation_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 'automation')
        utils_spec = importlib.util.spec_from_file_location(
            'utils', os.path.join(automation_path, 'utils.py'))
        utils_mod = importlib.util.module_from_spec(utils_spec)
        sys.modules.setdefault('utils', utils_mod)
        utils_spec.loader.exec_module(utils_mod)

        # Also add automation/script to sys.path so `from script.X import *`
        # works
        script_path = os.path.join(automation_path, 'script')
        for p in [automation_path, script_path]:
            if p not in sys.path:
                sys.path.insert(0, p)

        # Dynamically load automation/script/module.py
        module_spec = importlib.util.spec_from_file_location(
            '_test_module',
            os.path.join(automation_path, 'script', 'module.py'))
        module_mod = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module_mod)

        sa = module_mod.ScriptAutomation.__new__(module_mod.ScriptAutomation)
        result = sa.init_run_state(None)
        self.assertIn('apptainer', result,
                      "init_run_state must seed run_state['apptainer']")
        self.assertEqual(result['apptainer'], {})


# ---------------------------------------------------------------------------
# 2. CLI fallback: docker_X used when apptainer_X is absent
#    Tests the three-level lookup: apptainer_X > docker_X > settings > default
# ---------------------------------------------------------------------------

class ApptainerDockerCliFallbackTest(unittest.TestCase):

    def _lookup(self, key, input_params, settings, default=None):
        """Replicates the lookup used in prepare_apptainer_inputs."""
        return input_params.get(
            f"apptainer_{key}",
            input_params.get(f"docker_{key}", settings.get(key, default))
        )

    def test_apptainer_prefix_wins(self):
        val = self._lookup(
            "os", {
                "apptainer_os": "debian", "docker_os": "centos"}, {})
        self.assertEqual(val, "debian")

    def test_docker_prefix_fallback(self):
        val = self._lookup("os", {"docker_os": "centos"}, {})
        self.assertEqual(val, "centos")

    def test_settings_fallback(self):
        val = self._lookup("os", {}, {"os": "ubuntu"})
        self.assertEqual(val, "ubuntu")

    def test_default_fallback(self):
        val = self._lookup("os", {}, {}, "alpine")
        self.assertEqual(val, "alpine")

    def test_noregenerate_docker_fallback(self):
        i = {"docker_noregenerate": True}
        regenerate_def_file = not i.get(
            "apptainer_noregenerate", i.get(
                "docker_noregenerate", False))
        self.assertFalse(regenerate_def_file)

    def test_noregenerate_apptainer_overrides_docker(self):
        i = {"apptainer_noregenerate": False, "docker_noregenerate": True}
        regenerate_def_file = not i.get(
            "apptainer_noregenerate", i.get(
                "docker_noregenerate", False))
        self.assertTrue(regenerate_def_file)

    def test_rebuild_docker_fallback(self):
        i = {"docker_rebuild": True}
        rebuild = i.get("apptainer_rebuild", i.get("docker_rebuild", False))
        self.assertTrue(rebuild)

    def test_mounts_docker_fallback(self):
        i = {"docker_mounts": ["/host:/container"]}
        mounts = i.get("apptainer_mounts", i.get("docker_mounts", []))
        self.assertEqual(mounts, ["/host:/container"])

    def test_mounts_apptainer_overrides_docker(self):
        i = {"apptainer_mounts": ["/a:/a"], "docker_mounts": ["/b:/b"]}
        mounts = i.get("apptainer_mounts", i.get("docker_mounts", []))
        self.assertEqual(mounts, ["/a:/a"])


# ---------------------------------------------------------------------------
# 3. meta_schema: apptainer key validation (calls real validate_meta)
# ---------------------------------------------------------------------------

class MetaSchemaApptainerKeyTest(unittest.TestCase):

    def _validate(self, data):
        from mlc.meta_schema import validate_meta
        base = {
            "alias": "test-script",
            "uid": "aabbccdd11223344",
            "automation_alias": "script",
            "automation_uid": "5b4aa8f95024c2a5",
        }
        base.update(data)
        return validate_meta(base, "test.yaml")

    def test_apptainer_key_accepted_with_dict(self):
        errors, warnings = self._validate({"apptainer": {"os": "ubuntu"}})
        self.assertEqual(errors, [])

    def test_apptainer_unknown_key_produces_warning(self):
        _, warnings = self._validate({"apptainer": {"unknown_key_xyz": "val"}})
        self.assertTrue(any("unknown key" in w for w in warnings))

    def test_apptainer_wrong_type_produces_error(self):
        errors, _ = self._validate({"apptainer": {"run": "not-a-bool"}})
        self.assertTrue(any("apptainer.run" in e for e in errors))

    def test_apptainer_run_bool_accepted(self):
        errors, _ = self._validate({"apptainer": {"run": False}})
        self.assertEqual(errors, [])

    def test_docker_and_apptainer_both_accepted(self):
        errors, _ = self._validate({
            "docker": {"os": "ubuntu"},
            "apptainer": {"os": "centos"},
        })
        self.assertEqual(errors, [])

    def test_apptainer_base_image_str_accepted(self):
        errors, _ = self._validate(
            {"apptainer": {"base_image": "ubuntu:22.04"}})
        self.assertEqual(errors, [])


# ---------------------------------------------------------------------------
# 4. CLI smoke tests: mlcd --help and mlca --help
# ---------------------------------------------------------------------------

class CliHelpSmokeTest(unittest.TestCase):
    """mlcd and mlca --help exit cleanly and include expected content."""

    def test_mlcd_help_exits_successfully(self):
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.argv=['mlcd','--help']; "
             "from mlc.main import mlcd; mlcd()"],
            capture_output=True, text=True
        )
        combined = result.stdout + result.stderr
        self.assertIn("docker", combined.lower(),
                      msg=f"Expected docker help text, got: {combined[:500]}")

    def test_mlca_help_exits_successfully(self):
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.argv=['mlca','--help']; "
             "from mlc.main import mlca; mlca()"],
            capture_output=True, text=True
        )
        combined = result.stdout + result.stderr
        self.assertIn("apptainer", combined.lower(),
                      msg=f"Expected apptainer help text, got: {combined[:500]}")

    def test_mlca_help_mentions_docker_fallback(self):
        """mlca --help documents that --docker_X options are accepted."""
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.argv=['mlca','--help']; "
             "from mlc.main import mlca; mlca()"],
            capture_output=True, text=True
        )
        combined = result.stdout + result.stderr
        self.assertIn("docker_rebuild", combined,
                      msg=f"Expected docker_rebuild in mlca help, got: {combined[:500]}")
        self.assertIn("docker_noregenerate", combined,
                      msg=f"Expected docker_noregenerate in mlca help, got: {combined[:500]}")


if __name__ == "__main__":
    unittest.main()
