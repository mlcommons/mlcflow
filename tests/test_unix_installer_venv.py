import os
import platform
import shlex
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALLER_PATH = os.path.join(REPO_ROOT, "docs", "install", "mlcflow_unix_installer.sh")


def normalize_architecture(machine):
    if machine in ("x86_64", "amd64"):
        return "x86_64"
    if machine in ("aarch64", "arm64"):
        return "aarch64"
    return machine


class UnixInstallerVenvTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.sourced_installer_path = os.path.join(
            self.temp_dir.name, "mlcflow_unix_installer_for_test.sh"
        )

        with open(INSTALLER_PATH, "r", encoding="utf-8") as installer_file:
            installer_contents = installer_file.read()

        self.assertTrue(
            installer_contents.rstrip().endswith("main"),
            msg="Expected installer script to end with a standalone main call.",
        )

        installer_without_main = installer_contents.rsplit("\nmain", 1)[0] + "\n"
        with open(self.sourced_installer_path, "w", encoding="utf-8") as installer_file:
            installer_file.write(installer_without_main)

    def _expected_suffix(self):
        return "_{}_py{}.{}".format(
            normalize_architecture(platform.machine()),
            sys.version_info[0],
            sys.version_info[1],
        )

    def _run_setup_venv(self, venv_dir):
        command = """
set -euo pipefail
source {installer}
VENV_DIR={venv_dir}
setup_venv
printf '__RESULT__:%s:%s\\n' "$VENV_DIR" "${{VIRTUAL_ENV:-}}"
""".format(
            installer=shlex.quote(self.sourced_installer_path),
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

    def test_setup_venv_uses_arch_and_python_suffix_for_incompatible_dir(self):
        venv_dir = os.path.join(self.temp_dir.name, "mlcflow")
        os.makedirs(venv_dir, exist_ok=True)
        expected_path = venv_dir + self._expected_suffix()

        resolved_path, activated_path, stdout = self._run_setup_venv(venv_dir)

        self.assertEqual(resolved_path, expected_path)
        self.assertEqual(activated_path, expected_path)
        self.assertIn("is incompatible. Using", stdout)
        self.assertTrue(os.path.exists(os.path.join(expected_path, "bin", "python")))


if __name__ == "__main__":
    unittest.main()
