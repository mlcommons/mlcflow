import os
import subprocess

def _get_version():
    """Read version from VERSION file or package metadata, and append git commit hash if available."""
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(pkg_dir)

    # Read VERSION file (works in dev/source tree)
    version = None
    for vpath in [os.path.join(root_dir, "VERSION"), os.path.join(pkg_dir, "VERSION")]:
        if os.path.isfile(vpath):
            with open(vpath) as f:
                version = f.read().strip()
            break

    # Fall back to installed package metadata
    if not version:
        try:
            from importlib.metadata import version as pkg_version
            version = pkg_version("mlcflow")
        except Exception:
            version = "0.0.0"

    # Append git short commit hash if in a git repo
    try:
        commit = subprocess.check_output(
            ["git", "-C", root_dir, "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL, text=True
        ).strip()
        if commit:
            version = f"{version}+{commit}"
    except Exception:
        pass

    return version

__version__ = _get_version()

from .action import access

__all__ = ['access']
