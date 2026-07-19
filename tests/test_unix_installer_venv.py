import os
import platform
import shlex
import subprocess
import sys
import tempfile
import textwrap
import unittest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALLER_PATH = os.path.join(
    REPO_ROOT,
    "docs",
    "install",
    "mlcflow_unix_installer.sh")
# Keep this in sync with docs/install/mlcflow_unix_installer.sh:
# get_venv_suffix() and get_python_compatibility_signature().
COMPATIBILITY_SIGNATURE_CODE = (
    'import platform, sys; '
    'print("{}|{}.{}".format(platform.machine(), sys.version_info[0], sys.version_info[1]))'
)


class UnixInstallerVenvTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def _expected_suffix(self):
        return (
            f"_{platform.machine()}"
            f"_py{sys.version_info[0]}.{sys.version_info[1]}"
        )

    def _run_setup_venv(self, venv_dir):
        command = """
set -euo pipefail
source {installer}
VENV_DIR={venv_dir}
setup_venv
printf '__RESULT__:%s:%s\\n' "$VENV_DIR" "${{VIRTUAL_ENV:-}}"
""".format(
            installer=shlex.quote(INSTALLER_PATH),
            venv_dir=shlex.quote(venv_dir),
        )

        completed = subprocess.run(
            ["bash", "-lc", command],
            cwd=self.temp_dir.name,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, msg=completed.stderr)

        result_lines = [
            line for line in completed.stdout.splitlines()
            if line.startswith("__RESULT__:")
        ]
        self.assertTrue(result_lines, msg=completed.stdout)
        _, resolved_path, activated_path = result_lines[-1].split(":", 2)
        return resolved_path, activated_path, completed.stdout

    def _compatibility_signature(self, python_executable):
        completed = subprocess.run(
            [
                python_executable,
                "-c",
                COMPATIBILITY_SIGNATURE_CODE,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return completed.stdout.strip()

    def _write_installer_with_stubbed_main_dependencies(self):
        integration_installer_path = os.path.join(
            self.temp_dir.name, "mlcflow_unix_installer_integration_test.sh"
        )
        stubbed_functions = textwrap.dedent("""
            detect_os() {
                OS_ID="ubuntu"
                OS_VERSION="test"
                PKG_MANAGER="apt"
            }

            check_missing_dependencies() {
                MISSING_DEPS=()
            }

            ensure_python() {
                :
            }

            install_mlcflow() {
                :
            }

            prompt_repo_details() {
                :
            }

            pull_repo() {
                :
            }
            """).strip()
        with open(INSTALLER_PATH, "r", encoding="utf-8") as installer_file:
            installer_contents = installer_file.read().rstrip()
        main_guard = textwrap.dedent(
            """
            if [[ "${BASH_SOURCE[0]:-$0}" == "$0" ]]; then
                main
            fi
            """
        ).strip()
        replacement = (
            stubbed_functions
            + "\n\n"
            + main_guard
        )
        self.assertIn(main_guard, installer_contents)
        modified_contents = installer_contents.replace(main_guard, replacement)
        self.assertIn(replacement, modified_contents)
        with open(integration_installer_path, "w", encoding="utf-8") as installer_file:
            installer_file.write(modified_contents)
        return integration_installer_path

    def test_installer_main_runs_setup_venv_with_stubbed_dependencies(self):
        venv_dir = os.path.join(self.temp_dir.name, "mlcflow")
        os.makedirs(venv_dir, exist_ok=True)
        expected_path = venv_dir + self._expected_suffix()
        installer_path = self._write_installer_with_stubbed_main_dependencies()

        completed = subprocess.run(
            ["bash", installer_path, "--yes", "--venv-dir", venv_dir],
            cwd=self.temp_dir.name,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0, msg=completed.stderr)
        self.assertIn("Installation completed successfully.", completed.stdout)
        self.assertIn(expected_path, completed.stdout)
        self.assertTrue(
            os.path.exists(
                os.path.join(
                    expected_path,
                    "bin",
                    "python")))
        self.assertEqual(
            self._compatibility_signature(
                os.path.join(expected_path, "bin", "python")),
            self._compatibility_signature(sys.executable),
        )

    def test_setup_venv_creates_requested_path_from_scratch(self):
        venv_dir = os.path.join(self.temp_dir.name, "mlcflow")

        resolved_path, activated_path, stdout = self._run_setup_venv(venv_dir)

        self.assertEqual(resolved_path, venv_dir)
        self.assertEqual(activated_path, venv_dir)
        self.assertIn("Setting up virtual environment at", stdout)
        self.assertTrue(
            os.path.exists(
                os.path.join(
                    venv_dir,
                    "bin",
                    "python")))
        self.assertEqual(
            self._compatibility_signature(
                os.path.join(venv_dir, "bin", "python")),
            self._compatibility_signature(sys.executable),
        )

    def test_setup_venv_reuses_compatible_existing_venv(self):
        venv_dir = os.path.join(self.temp_dir.name, "mlcflow")
        subprocess.run(
            [sys.executable, "-m", "venv", venv_dir],
            check=True,
            cwd=self.temp_dir.name,
        )

        resolved_path, activated_path, stdout = self._run_setup_venv(venv_dir)

        self.assertEqual(resolved_path, venv_dir)
        self.assertEqual(activated_path, venv_dir)
        self.assertIn("Reusing existing virtual environment.", stdout)
        self.assertEqual(
            self._compatibility_signature(
                os.path.join(venv_dir, "bin", "python")),
            self._compatibility_signature(sys.executable),
        )

    def test_setup_venv_uses_arch_and_python_suffix_for_incompatible_dir(self):
        venv_dir = os.path.join(self.temp_dir.name, "mlcflow")
        os.makedirs(venv_dir, exist_ok=True)
        expected_path = venv_dir + self._expected_suffix()

        resolved_path, activated_path, stdout = self._run_setup_venv(venv_dir)

        self.assertEqual(resolved_path, expected_path)
        self.assertEqual(activated_path, expected_path)
        self.assertIn(
            "is incompatible with current Python/platform. Using",
            stdout)
        self.assertTrue(
            os.path.exists(
                os.path.join(
                    expected_path,
                    "bin",
                    "python")))
        self.assertEqual(
            self._compatibility_signature(
                os.path.join(expected_path, "bin", "python")),
            self._compatibility_signature(sys.executable),
        )


if __name__ == "__main__":
    unittest.main()
