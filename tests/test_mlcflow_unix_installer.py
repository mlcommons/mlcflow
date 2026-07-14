import subprocess
import platform
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER_SCRIPT = REPO_ROOT / "docs" / "install" / "mlcflow_unix_installer.sh"


def _resolve_venv_dir(tmp_path, setup_snippet):
    default_dir = tmp_path / "mlcflow"
    marker = "__RESULT__"
    command = f"""
set -euo pipefail
source "{INSTALLER_SCRIPT}"
DEFAULT_VENV_DIR="{default_dir}"
VENV_DIR="$DEFAULT_VENV_DIR"
PY_MAJOR_MINOR="$(python3 -c 'import sys; print("{{}}.{{}}".format(*sys.version_info[:2]))')"
PY_ARCH="$(python3 -c 'import platform; print(platform.machine())')"
{setup_snippet}
resolve_default_venv_dir
echo "{marker}$VENV_DIR"
"""
    result = subprocess.run(
        ["bash", "-lc", command],
        text=True,
        capture_output=True,
        check=True,
    )

    for line in reversed(result.stdout.splitlines()):
        if line.startswith(marker):
            return line[len(marker) :]

    raise AssertionError(f"Could not parse resolved venv path from output:\n{result.stdout}")


def test_resolve_default_venv_dir_prefers_compatible_default(tmp_path):
    setup_snippet = """
python3 -m venv "$DEFAULT_VENV_DIR"
"""
    resolved = _resolve_venv_dir(tmp_path, setup_snippet)
    assert resolved == str(tmp_path / "mlcflow")


def test_resolve_default_venv_dir_uses_suffix_for_incompatible_default(tmp_path):
    setup_snippet = """
mkdir -p "$DEFAULT_VENV_DIR"
"""
    resolved = _resolve_venv_dir(tmp_path, setup_snippet)
    assert resolved.startswith(str(tmp_path / "mlcflow_"))
    assert "_py" in resolved


def test_resolve_default_venv_dir_reuses_compatible_suffixed_env(tmp_path):
    setup_snippet = """
SHARED_VENV_DIR="${DEFAULT_VENV_DIR}_${PY_ARCH}_py${PY_MAJOR_MINOR}"
python3 -m venv "$SHARED_VENV_DIR"
"""
    resolved = _resolve_venv_dir(tmp_path, setup_snippet)
    expected = f"{tmp_path / 'mlcflow'}_{platform.machine()}_py{sys.version_info[0]}.{sys.version_info[1]}"
    assert resolved == expected
