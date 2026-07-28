"""
mlc_compat: version-compatibility enforcement for mlcflow scripts.

Scripts in mlperf-automations can declare minimum mlcflow version requirements
via the `mlc_compat` field in their meta.yaml.  This module provides the
helpers used by ScriptAction and RepoAction to evaluate those requirements.
"""
import os

from .logger import logger


def get_installed_version():
    """Return the installed mlcflow version string, or None if unavailable."""
    try:
        from importlib.metadata import version
        return version("mlcflow")
    except Exception:
        pass
    # Fallback: read the VERSION file bundled with this package
    try:
        version_file = os.path.join(os.path.dirname(__file__), "..", "VERSION")
        with open(version_file) as f:
            return f.read().strip()
    except Exception:
        return None


def check_mlc_compat(compat_entries, installed_version_str):
    """
    Evaluate mlc_compat entries against installed_version_str.

    Args:
        compat_entries (list[dict]): List of mlc_compat dicts from meta.yaml.
        installed_version_str (str | None): Installed mlcflow version.

    Returns:
        (unmet_warnings, unmet_blockers): Two lists of dicts, each with keys
        'min_version' and 'message'.  Blockers have fail=true in the source.
    """
    if not compat_entries or not installed_version_str:
        return [], []

    try:
        from packaging.version import Version
        installed = Version(installed_version_str)
    except Exception:
        logger.debug("mlc_compat: could not parse installed version, skipping check")
        return [], []

    unmet_warnings = []
    unmet_blockers = []
    for entry in compat_entries:
        if not isinstance(entry, dict):
            continue
        min_version_str = entry.get("min_version", "")
        message = entry.get("message", "")
        fail = bool(entry.get("fail", False))
        try:
            min_ver = Version(min_version_str)
        except Exception:
            logger.debug(f"mlc_compat: could not parse min_version '{min_version_str}', skipping entry")
            continue
        if installed < min_ver:
            item = {"min_version": min_version_str, "message": message}
            if fail:
                unmet_blockers.append(item)
            else:
                unmet_warnings.append(item)

    return unmet_warnings, unmet_blockers


def format_compat_notice(script_name, unmet_warnings, unmet_blockers, installed_version_str):
    """
    Build a multi-line human-readable notice for unmet mlc_compat requirements.

    Returns a tuple (notice_str, is_blocking).
    """
    all_unmet = unmet_warnings + unmet_blockers
    if not all_unmet:
        return "", False

    is_blocking = bool(unmet_blockers)
    header = (
        f"mlc_compat: script '{script_name}' has version requirements "
        f"not met by the installed mlcflow "
        f"{installed_version_str or '(unknown)'}:"
    )
    lines = [header]
    for entry in unmet_warnings:
        lines.append(f"  [warn ] min_version {entry['min_version']}: {entry['message']}")
    for entry in unmet_blockers:
        lines.append(f"  [ERROR] min_version {entry['min_version']}: {entry['message']}")
    if is_blocking:
        lines.append("  -> Run `pip install --upgrade mlcflow` to satisfy blocking requirements.")
    else:
        lines.append("  -> Consider upgrading: `pip install --upgrade mlcflow`")
    return "\n".join(lines), is_blocking


def scan_repo_for_compat(repo_path, installed_version_str):
    """
    Scan all script/*/meta.yaml files in repo_path for unmet mlc_compat entries.

    Returns a list of dicts with keys: script_alias, unmet_warnings, unmet_blockers.
    Only returns entries for scripts that have at least one unmet requirement.
    """
    import yaml

    results = []
    scripts_dir = os.path.join(repo_path, "script")
    if not os.path.isdir(scripts_dir):
        return results

    for entry in os.scandir(scripts_dir):
        if not entry.is_dir():
            continue
        meta_file = os.path.join(entry.path, "meta.yaml")
        if not os.path.isfile(meta_file):
            continue
        try:
            with open(meta_file) as f:
                meta = yaml.safe_load(f)
        except Exception:
            continue
        if not isinstance(meta, dict):
            continue
        compat_entries = meta.get("mlc_compat")
        if not compat_entries:
            continue
        warnings, blockers = check_mlc_compat(compat_entries, installed_version_str)
        if warnings or blockers:
            results.append({
                "script_alias": meta.get("alias", entry.name),
                "unmet_warnings": warnings,
                "unmet_blockers": blockers,
            })

    return results


def print_repo_compat_summary(repo_path, installed_version_str):
    """
    Print a consolidated mlc_compat summary for a repo after it is pulled.
    Emits nothing if all requirements are satisfied.
    """
    results = scan_repo_for_compat(repo_path, installed_version_str)
    if not results:
        return

    warn_scripts = [r for r in results if r["unmet_warnings"] and not r["unmet_blockers"]]
    block_scripts = [r for r in results if r["unmet_blockers"]]

    lines = [
        f"\nmlc_compat summary for repo '{os.path.basename(repo_path)}' "
        f"(installed mlcflow {installed_version_str or '(unknown)'}):"
    ]

    if block_scripts:
        lines.append("  Scripts that REQUIRE a newer mlcflow (will block execution):")
        for r in block_scripts:
            lines.append(f"    - {r['script_alias']}")
            for e in r["unmet_blockers"]:
                lines.append(f"        [ERROR] min_version {e['min_version']}: {e['message']}")
        lines.append("  -> Run `pip install --upgrade mlcflow` to fix blocking requirements.")

    if warn_scripts:
        lines.append("  Scripts that recommend a newer mlcflow (will warn at run time):")
        for r in warn_scripts:
            lines.append(f"    - {r['script_alias']}")
            for e in r["unmet_warnings"]:
                lines.append(f"        [warn ] min_version {e['min_version']}: {e['message']}")

    notice = "\n".join(lines)
    if block_scripts:
        logger.warning(notice)
    else:
        logger.info(notice)
