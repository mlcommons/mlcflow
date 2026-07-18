import platform
import subprocess
import sys
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER_SCRIPT = REPO_ROOT / "docs" / "install" / "mlcflow_unix_installer.sh"


def _normalize_architecture(machine):
    if machine in ("x86_64", "amd64"):
        return "x86_64"
    if machine in ("aarch64", "arm64"):
        return "aarch64"
    return machine


def _resolve_venv_dir(tmp_path, setup_snippet):
    default_dir = tmp_path / "mlcflow"
    marker = "__RESULT__"
    command = textwrap.dedent(
        f"""
        set -euo pipefail
        source "{INSTALLER_SCRIPT}"
        DEFAULT_VENV_DIR="{default_dir}"
        VENV_DIR="$DEFAULT_VENV_DIR"
        PY_MAJOR_MINOR="$(python3 -c 'import sys; print("{{}}.{{}}".format(*sys.version_info[:2]))')"
        PY_ARCH="$(python3 -c 'import platform; machine = platform.machine(); print("x86_64" if machine in ("x86_64", "amd64") else "aarch64" if machine in ("aarch64", "arm64") else machine)')"
        {setup_snippet}
        resolve_default_venv_dir
        echo "{marker}$VENV_DIR"
        """
    )
    result = subprocess.run(
        ["bash", "-lc", command],
        text=True,
        capture_output=True,
        check=True,
    )

    for line in reversed(result.stdout.splitlines()):
        if line.startswith(marker):
            return line[len(marker):]

    raise AssertionError(
        f"Could not parse resolved venv path from output:\n{result.stdout}"
    )


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


def test_resolve_default_venv_dir_removes_stale_shared_env_when_default_incompatible(
    tmp_path,
):
    """Broken suffixed envs should be removed so setup_venv recreates them."""
    setup_snippet = """
    mkdir -p "$DEFAULT_VENV_DIR"
    SHARED_VENV_DIR="${DEFAULT_VENV_DIR}_${PY_ARCH}_py${PY_MAJOR_MINOR}"
    mkdir -p "$SHARED_VENV_DIR"
    """
    resolved = _resolve_venv_dir(tmp_path, setup_snippet)
    expected_suffix = (
        f"{tmp_path / 'mlcflow'}_{_normalize_architecture(platform.machine())}"
        f"_py{sys.version_info[0]}.{sys.version_info[1]}"
    )
    assert resolved == expected_suffix
    assert not Path(expected_suffix).exists()


def test_resolve_default_venv_dir_reuses_compatible_suffixed_env(tmp_path):
    setup_snippet = """
    SHARED_VENV_DIR="${DEFAULT_VENV_DIR}_${PY_ARCH}_py${PY_MAJOR_MINOR}"
    python3 -m venv "$SHARED_VENV_DIR"
    """
    resolved = _resolve_venv_dir(tmp_path, setup_snippet)
    expected = (
        f"{tmp_path / 'mlcflow'}_{_normalize_architecture(platform.machine())}"
        f"_py{sys.version_info[0]}.{sys.version_info[1]}"
    )
    assert resolved == expected
