#!/usr/bin/env python3
"""Resolve the version for an mlcflow release, and refuse the impossible ones.

Used by ``.github/workflows/build_wheels.yml``.

A published version is final — PyPI rejects re-uploads — so every path that
resolves to an already-released version is refused before anything is built,
committed, tagged, or uploaded, with no override. The way forward is always a
new version.

``resolve`` (the ``prepare`` job) reads ``VERSION``, applies ``BUMP``, and
writes the bumped value back. ``verify`` (the ``publish`` job) re-checks
``VERSION`` against PyPI from the tagged commit.

Environment:
    MODE            resolve | verify                      (default: resolve)
    BUMP            none | patch | minor | major          (resolve only)
    VERSION_FILE    path to the VERSION file              (default: VERSION)
    PACKAGE_NAME    PyPI project to check against         (default: mlcflow)
    GITHUB_OUTPUT   step-output file to append to         (optional)

Outputs (``$GITHUB_OUTPUT``):
    version     the resolved version, e.g. 1.3.4
    tag         the matching tag name, e.g. v1.3.4
    bumped      true if VERSION was rewritten (resolve only)

Exit status is 0 when the release may proceed, 1 when it is refused. Every
refusal prints a ``::error::`` line explaining the way forward.
"""

import json
import os
import re
import sys
import tempfile
import time
import urllib.error
import urllib.request

SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
BUMP_KINDS = ("none", "patch", "minor", "major")
PYPI_TIMEOUT = 15
PYPI_ATTEMPTS = 3
# PyPI asks API consumers to identify themselves, not share a default UA.
USER_AGENT = "mlcflow-release-workflow (+https://github.com/mlcommons/mlcflow)"


def fail(message, *hints):
    """Emit a GitHub Actions error annotation and exit non-zero."""
    print(f"::error::{message}")
    for hint in hints:
        print(f"  {hint}")
    sys.exit(1)


def parse(version):
    match = SEMVER.match(version.strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def bump(parts, kind):
    major, minor, patch = parts
    if kind == "major":
        return (major + 1, 0, 0)
    if kind == "minor":
        return (major, minor + 1, 0)
    if kind == "patch":
        return (major, minor, patch + 1)
    return parts


def render(parts):
    return ".".join(str(part) for part in parts)


def released_versions(package):
    """Every version already on PyPI, as a {text: parsed} map.

    A 404 means nothing is published yet, which is legitimate. Any other failure
    is fatal: the guards below mean nothing if we do not know what is on PyPI.
    """
    request = urllib.request.Request(
        f"https://pypi.org/pypi/{package}/json",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    last_error = None
    for attempt in range(1, PYPI_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=PYPI_TIMEOUT) as response:
                payload = json.load(response)
            break
        except urllib.error.HTTPError as error:
            if error.code == 404:
                print(f"{package} is not on PyPI yet; treating as no releases.")
                return {}
            last_error = error
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error
        if attempt < PYPI_ATTEMPTS:
            time.sleep(2 * attempt)
    else:
        fail(
            f"Could not read release metadata for {package} from PyPI: {last_error}",
            "Refusing to release without knowing which versions already exist.",
            "Re-run the workflow once PyPI is reachable again.",
        )

    versions = {}
    for text in payload.get("releases", {}):
        parts = parse(text)
        if parts is not None:
            versions[text.strip()] = parts
    return versions


def write_output(**values):
    target = os.environ.get("GITHUB_OUTPUT")
    for key, value in values.items():
        print(f"{key}={value}")
    if not target:
        return
    with open(target, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def write_version_file(path, text):
    """Replace ``path`` with ``text`` atomically, then read it back.

    Renamed over the target from a sibling temp file, so a failed write leaves
    the original intact instead of handing a truncated VERSION to the commit
    that follows in `prepare`.
    """
    directory = os.path.dirname(os.path.abspath(path))
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=directory,
            prefix=".VERSION.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_name = handle.name
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except OSError as error:
        if temp_name:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
        fail(f"Could not write {path}: {error}")

    written, _ = read_version_file(path)
    back, meant = render(written), text.strip()
    if back != meant:
        fail(
            f"{path} reads back as {back} after writing {meant}.",
            "Refusing to release from a VERSION file that did not persist.",
        )


def read_version_file(path):
    try:
        raw = open(path, encoding="utf-8").read()
    except OSError as error:
        fail(f"Could not read {path}: {error}")
    parts = parse(raw)
    if parts is None:
        found = raw.strip()
        fail(
            f"{path} contains {found!r}, not a MAJOR.MINOR.PATCH version.",
            "Fix VERSION on the default branch before releasing.",
        )
    return parts, raw.endswith("\n")


def do_resolve(version_file, package):
    kind = os.environ.get("BUMP", "none").strip() or "none"
    if kind not in BUMP_KINDS:
        fail(f"BUMP must be one of {', '.join(BUMP_KINDS)} (got {kind!r}).")

    current, trailing_newline = read_version_file(version_file)
    released = released_versions(package)
    latest = max(released.values()) if released else None
    now, top = render(current), render(latest) if latest else "(none)"

    print(f"VERSION file:    {now}")
    print(f"Latest on PyPI:  {top}")
    print(f"Requested bump:  {kind}")

    if kind == "none":
        # VERSION already holds the version to ship.
        if current in released.values():
            fail(
                f"Version {now} is already published on PyPI.",
                "PyPI versions are immutable, so this cannot be re-released.",
                "Re-run this workflow with bump=patch, bump=minor, or bump=major",
                "to increment VERSION automatically, or bump VERSION on the",
                "default branch via a PR and re-run with bump=none.",
            )
        target = current
    else:
        # VERSION should still hold the released version for us to increment.
        # Any other state gets named rather than silently picking a number.
        if latest is None:
            fail(
                f"Nothing is published for {package} yet — no version to bump from.",
                f"Re-run with bump=none to release VERSION ({now}) as-is.",
            )
        if current > latest:
            fail(
                f"VERSION ({now}) is already ahead of the latest release ({top}).",
                "Bumping it again would skip a version number.",
                f"Re-run with bump=none to release {now} as-is.",
            )
        if current < latest:
            fail(
                f"VERSION ({now}) is behind the latest release ({top}).",
                "The default branch is out of sync with PyPI; bumping from here",
                "would produce an already-published version.",
                f"Set VERSION to {top} on the default branch via a PR, then re-run.",
            )
        target = bump(current, kind)
        new = render(target)
        if target in released.values():
            fail(
                f"A {kind} bump of {now} gives {new}, which is already on PyPI.",
                "Choose a different bump level.",
            )
        write_version_file(version_file,
                           new + ("\n" if trailing_newline else ""))
        print(f"Rewrote {version_file}: {now} -> {new}")

    out = render(target)
    print(f"Releasing version {out}")
    write_output(
        version=out,
        tag=f"v{out}",
        bumped="true" if target != current else "false",
    )


def do_verify(version_file, package):
    current, _ = read_version_file(version_file)
    released = released_versions(package)
    now = render(current)

    if current in released.values():
        fail(
            f"Version {now} is already published on PyPI.",
            "A released version is final: PyPI would reject the upload, and the",
            "same version is never re-cut under a different build.",
            "Release a new version instead — dispatch this workflow against the",
            "default branch with bump=patch, bump=minor, or bump=major.",
        )

    print(f"Version {now} is not on PyPI yet; publishing it.")
    write_output(version=now, tag=f"v{now}")


def main():
    mode = os.environ.get("MODE", "resolve").strip() or "resolve"
    version_file = os.environ.get("VERSION_FILE", "VERSION")
    package = os.environ.get("PACKAGE_NAME", "mlcflow")

    if mode == "resolve":
        do_resolve(version_file, package)
    elif mode == "verify":
        do_verify(version_file, package)
    else:
        fail(f"MODE must be 'resolve' or 'verify' (got {mode!r}).")


if __name__ == "__main__":
    main()
