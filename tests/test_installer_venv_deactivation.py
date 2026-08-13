import os
import subprocess
import tempfile
import unittest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSTALLER_PATH = os.path.join(
    REPO_ROOT,
    "docs",
    "install",
    "mlcflow_unix_installer.sh")


class InstallerVenvDeactivationTest(unittest.TestCase):
    def test_sourcing_installer_deactivates_active_venv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            venv_dir = os.path.join(temp_dir, "testvenv")
            script = f"""
set -euo pipefail
python3 -m venv "{venv_dir}"
source "{venv_dir}/bin/activate"
[ -n "${{VIRTUAL_ENV:-}}" ]
source "{INSTALLER_PATH}"
[ -z "${{VIRTUAL_ENV:-}}" ]
case ":$PATH:" in
  *":{venv_dir}/bin:"*) exit 1 ;;
esac
"""
            result = subprocess.run(
                ["bash", "-c", script],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)


if __name__ == "__main__":
    unittest.main()
