"""Deciding what a remote node should install before it runs a script.

The remote bootstrap is three commands: install mlcflow, activate the venv,
run the script. Nothing in there says *which* script content to run, so the
remote falls back to cloning ``mlcommons@mlperf-automations`` at ``dev`` -
regardless of what the machine issuing the command is running.

This module decides the one command that goes in between, so a caller can say
"give the workers what I have" or "give the workers exactly this version"
instead of getting whatever was newest that morning.

An unconfigured run resolves to no extra command at all. That is deliberate:
the feature is opt-in, and the default bootstrap has to stay byte-for-byte
what it was.

Quoting rule for everything emitted here: **double quotes only.** The ssh
layer escapes single quotes and then shlex-quotes the whole command string,
so a single quote is escaped twice and arrives mangled.
"""

import os
import re
import subprocess

import mlc.utils as utils

# The modes a caller can ask for by name. 'package' and 'repo' are also
# inferred from which pin was supplied, so most callers never type one.
MODES = ("default", "mirror", "package", "repo")

CONTENT_PACKAGE = "mlc-scripts"
DEFAULT_CONTENT_REPO = "mlcommons@mlperf-automations"

# Anything a version string can start with that means "this is already a
# constraint, not a bare version".
_OPERATOR_START = re.compile(r"^[=<>!~]")


def _err(message):
    return {"return": 1, "error": message}


def _text(i, key):
    return str(i.get(key, "") or "").strip()


def pip_spec(package, value):
    """Turn a user-supplied version into something pip understands.

    ``1.2.0a4`` becomes ``mlc-scripts==1.2.0a4``; ``>=1.2`` becomes
    ``mlc-scripts>=1.2``; anything else (a full spec, a VCS URL, a local
    path) is passed through untouched so the escape hatch stays open.
    """
    value = str(value).strip()
    if not value:
        return ""
    if value[0].isdigit():
        return f"{package}=={value}"
    if _OPERATOR_START.match(value):
        return f"{package}{value}"
    return value


def _fatal(cmd, what):
    """Make a bootstrap step abort the remote shell instead of being skipped.

    The bootstrap joins its commands with ';', so without this a failed
    install just carries on to the script - which then runs, succeeds, and
    reports a version nobody asked for. Failing here turns that into a failed
    node instead.
    """
    return f'{cmd} || {{ echo "MLC_PROVISION_FAILED: {what}"; exit 1; }}'


def _pip_install(spec):
    return _fatal(f'python3 -m pip install "{spec}"', f"pip install {spec}")


def _pull_repo(repo, ref):
    return _fatal(
        f'mlc pull repo {repo} --checkout={ref}',
        f"mlc pull repo {repo} at {ref}")


# ---------------------------------------------------------------------------
# Reading the head node
# ---------------------------------------------------------------------------

def _owning_repo(action_object, script_path):
    """The registered repo the selected script came out of.

    Longest path prefix wins, and it is path containment only - alias and uid
    are shared between a pulled checkout and the packaged copy, so they cannot
    tell the two apart, and telling them apart is the whole job here.
    """
    if not script_path:
        return None
    script_path = os.path.abspath(script_path)
    best = None
    best_len = -1
    for repo in getattr(action_object, "repos", None) or []:
        path = os.path.abspath(getattr(repo, "path", "") or "")
        if not path:
            continue
        if script_path == path or script_path.startswith(path + os.sep):
            if len(path) > best_len:
                best, best_len = path, len(path)
    return best


def _git(repo_path, *args):
    return subprocess.check_output(
        ["git", "-C", repo_path, *args],
        stderr=subprocess.DEVNULL, text=True).strip()


def _repo_id(repo_path):
    """How to name this checkout to a machine that does not have it.

    ``mlc pull repo`` accepts both ``user@repo`` and a plain URL, so an origin
    that is not GitHub still works - it just does not get shortened.
    """
    try:
        url = _git(repo_path, "remote", "get-url", "origin")
    except Exception:
        return os.path.basename(repo_path.rstrip(os.sep))
    match = re.match(
        r"(?:https?://|git@)(?:www\.)?github\.com[/:]([^/]+)/([^/.]+)",
        url)
    if match:
        return f"{match.group(1)}@{match.group(2)}"
    return url


def _commit_is_pushed(repo_path, commit):
    """Whether some remote branch contains this commit.

    A failure to answer is not a failure: a repo with no remotes configured,
    or a git that does not understand the question, should not block a run
    we cannot prove is broken.
    """
    try:
        return bool(_git(repo_path, "branch", "-r", "--contains", commit))
    except Exception:
        return True


def head_mlcflow_version():
    """The mlcflow this process is running, or '' if it cannot be determined."""
    try:
        from importlib import metadata as importlib_metadata
        return importlib_metadata.version("mlcflow")
    except Exception:
        return ""


def _mirror_git(repo_path):
    version = utils.get_repo_version(repo_path)
    commit = (version.get("commit") or "").strip()
    if not commit:
        return _err(
            f"--remote_provision=mirror found a git checkout at {repo_path} "
            f"but could not read its commit, so there is nothing to send to "
            f"the nodes. Use --remote_repo_ref to name a branch or commit "
            f"explicitly.")

    if version.get("dirty"):
        return _err(
            f"--remote_provision=mirror cannot reproduce this machine:\n"
            f"  {repo_path} is a git checkout with uncommitted tracked "
            f"changes, so commit {commit[:8]} does not describe what is "
            f"running here.\n"
            f"Pick one:\n"
            f"  * commit and push, then re-run\n"
            f"  * --remote_repo_ref=<branch or commit>   mirror a specific "
            f"point instead\n"
            f"  * --remote_copy_mlc_repos                copy this exact "
            f"tree, local edits included")

    if not _commit_is_pushed(repo_path, commit):
        return _err(
            f"--remote_provision=mirror cannot reproduce this machine: "
            f"commit {commit[:8]} in {repo_path} is not on any remote branch, "
            f"so the nodes have no way to fetch it. Push it, or use "
            f"--remote_copy_mlc_repos to copy the tree directly.")

    return {
        "return": 0,
        "mode": "repo",
        "repo": _repo_id(repo_path),
        "ref": commit,
        # A mirror is only a mirror if it covers the engine too.
        "mlcflow": head_mlcflow_version(),
    }


def _mirror(action_object, script_path):
    repo_path = _owning_repo(action_object, script_path)
    if repo_path is None:
        return _err(
            f"--remote_provision=mirror could not work out which registered "
            f"repo the script at {script_path} came from, so it cannot "
            f"describe it to the nodes. Use --remote_mlc_scripts or "
            f"--remote_repo_ref instead.")

    # Git before package, deliberately. An editable mlc-scripts install is
    # both at once, and the checkout is what this machine actually runs -
    # answering "the package version" there would send the nodes a completely
    # different tree.
    if os.path.isdir(os.path.join(repo_path, ".git")):
        return _mirror_git(repo_path)

    packaged = getattr(action_object, "package_repo_path", None)
    if packaged and os.path.abspath(packaged) == repo_path:
        version = (getattr(action_object, "package_repo_version", None) or "")
        if not version:
            return _err(
                f"--remote_provision=mirror found the packaged "
                f"{CONTENT_PACKAGE} at {repo_path} but could not read its "
                f"version. Name one with --remote_mlc_scripts=<version>.")
        return {
            "return": 0,
            "mode": "package",
            "scripts": version,
            # The package declares the mlcflow it needs; see resolve().
            "mlcflow": "",
        }

    return _err(
        f"--remote_provision=mirror cannot describe {repo_path}: it is "
        f"neither a git checkout nor an installed {CONTENT_PACKAGE}, so there "
        f"is no version a node could install. Use --remote_mlc_scripts, "
        f"--remote_repo_ref, or --remote_copy_mlc_repos to copy the tree as "
        f"it is.")


# ---------------------------------------------------------------------------
# The entry point
# ---------------------------------------------------------------------------

def resolve(i, action_object=None, script_path=None):
    """Work out the extra bootstrap commands for this run.

    Returns ``{'return': 0, 'cmds': [...], 'mode': ...}``. An empty ``cmds``
    means "do exactly what an unconfigured run has always done".
    """
    mode = _text(i, "remote_provision").lower()
    scripts = _text(i, "remote_mlc_scripts")
    repo = _text(i, "remote_repo")
    ref = _text(i, "remote_repo_ref")
    mlcflow = _text(i, "remote_mlcflow")

    if mode and mode not in MODES:
        return _err(
            f"--remote_provision={mode} is not a mode. Pick one of: "
            f"{', '.join(MODES)}.")

    if scripts and (repo or ref):
        return _err(
            f"--remote_mlc_scripts installs the packaged scripts and "
            f"--remote_repo_ref clones them from git. Pick one.")

    if not mode:
        mode = "package" if scripts else "repo" if (repo or ref) else "default"

    if mode == "mirror" and (scripts or repo or ref):
        return _err(
            f"--remote_provision=mirror works out what to install from this "
            f"machine. Drop --remote_mlc_scripts / --remote_repo / "
            f"--remote_repo_ref, or drop mirror.")

    if mode == "package" and not scripts:
        return _err(
            f"--remote_provision=package needs --remote_mlc_scripts="
            f"<version> to say which version the nodes should install.")

    if mode == "repo" and not ref:
        return _err(
            f"--remote_provision=repo needs --remote_repo_ref=<branch or "
            f"commit>. Without one it is the default behaviour with extra "
            f"steps.")

    # One thing gets to choose the mlcflow version. Where something already
    # has, an explicit pin is refused rather than silently layered on top -
    # mlc-scripts declares a floor, not an exact version, so pip would accept
    # the contradiction and the nodes would run an untested pairing.
    if mlcflow and mode == "package":
        return _err(
            f"--remote_mlcflow cannot be combined with "
            f"--remote_mlc_scripts={scripts}.\n"
            f"That package declares the mlcflow it needs, and overriding it "
            f"produces a combination that was never tested together.\n"
            f"To test a specific mlcflow against specific script content, use "
            f"--remote_repo_ref instead.")

    if mlcflow and mode == "mirror":
        return _err(
            f"--remote_mlcflow cannot be combined with "
            f"--remote_provision=mirror.\n"
            f"Mirror sends this machine's mlcflow along with its script "
            f"content; overriding half of that is not a mirror of anything.\n"
            f"Use --remote_repo_ref with --remote_mlcflow to pin both "
            f"yourself.")

    if mode == "mirror":
        resolved = _mirror(action_object, script_path)
        if resolved["return"] > 0:
            return resolved
        mode = resolved["mode"]
        scripts = resolved.get("scripts", "")
        repo = resolved.get("repo", "")
        ref = resolved.get("ref", "")
        mlcflow = resolved.get("mlcflow", "")

    cmds = []

    # mlcflow first: a pinned engine should be in place before it is asked to
    # pull anything.
    if mlcflow:
        cmds.append(_pip_install(pip_spec("mlcflow", mlcflow)))

    if mode == "package":
        cmds.append(_pip_install(pip_spec(CONTENT_PACKAGE, scripts)))
    elif mode == "repo":
        cmds.append(_pull_repo(repo or DEFAULT_CONTENT_REPO, ref))

    return {"return": 0, "cmds": cmds, "mode": mode}
