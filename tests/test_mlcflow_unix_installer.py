import platform
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALLER_SCRIPT = REPO_ROOT / "docs" / "install" / "mlcflow_unix_installer.sh"

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
        PY_ARCH="$(python3 -c 'import platform; print(platform.machine())')"
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


def test_resolve_default_venv_dir_uses_suffix_for_incompatible_default(
        tmp_path):
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
        f"{tmp_path / 'mlcflow'}_{platform.machine()}"
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
        f"{tmp_path / 'mlcflow'}_{platform.machine()}"
        f"_py{sys.version_info[0]}.{sys.version_info[1]}"
    )
    assert resolved == expected


def test_get_venv_suffix_uses_python_machine_value():
    with tempfile.TemporaryDirectory() as temp_dir:
        shim_path = Path(temp_dir) / "python-shim"
        shim_path.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env python3
                import os
                import sys

                machine = os.environ["FAKE_MACHINE"]
                major = os.environ.get("FAKE_PY_MAJOR", "3")
                minor = os.environ.get("FAKE_PY_MINOR", "12")
                code = sys.argv[2]

                if (
                    "platform.machine()" in code
                    and "sys.version_info[0]" in code
                    and "sys.version_info[1]" in code
                    and "_py" in code
                ):
                    print(f"_{machine}_py{major}.{minor}")
                elif (
                    "platform.machine()" in code
                    and "sys.version_info[0]" in code
                    and "sys.version_info[1]" in code
                    and "|" in code
                ):
                    print(f"{machine}|{major}.{minor}")
                else:
                    raise SystemExit(f"unexpected code: {code}")
                """
            ),
            encoding="utf-8",
        )
        shim_path.chmod(0o755)

        command = textwrap.dedent(
            f"""
            set -euo pipefail
            source "{INSTALLER_SCRIPT}"
            PYTHON_CMD="{shim_path}"
            export FAKE_MACHINE=arm64
            export FAKE_PY_MAJOR=3
            export FAKE_PY_MINOR=12
            printf '__RESULT__:%s:%s\\n' "$(get_venv_suffix)" "$(get_python_compatibility_signature "$PYTHON_CMD")"
            """
        )
        result = subprocess.run(
            ["bash", "-lc", command],
            text=True,
            capture_output=True,
            check=True,
        )

    assert "__RESULT__:_arm64_py3.12:arm64|3.12" in result.stdout
