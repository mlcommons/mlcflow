import argparse
import pathlib
import re

from packaging.version import InvalidVersion, Version


def _validate_pep440(version, description):
    try:
        Version(version)
    except InvalidVersion as exc:
        raise ValueError(
            f"{description} '{version}' is not a valid PEP 440 version."
        ) from exc


def compute_release_version(current_version, requested_version=None):
    current_version = current_version.strip()
    _validate_pep440(current_version, "Current version")

    if requested_version:
        candidate = requested_version.strip()
    else:
        match = re.search(r"(\d+)(?!.*\d)", current_version)
        if match is None:
            raise ValueError(
                f"Current version '{current_version}' does not end with digits to increment."
            )
        start, end = match.span(1)
        candidate = (
            f"{current_version[:start]}{int(match.group(1)) + 1}{current_version[end:]}"
        )

    _validate_pep440(candidate, "Requested version")
    return candidate


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Resolve the next release version from a VERSION file and an optional explicit override."
        )
    )
    parser.add_argument("--current-version-file", required=True)
    parser.add_argument("--requested-version", default="")
    args = parser.parse_args()

    current_version = pathlib.Path(args.current_version_file).read_text(
        encoding="utf-8"
    ).strip()
    try:
        version = compute_release_version(
            current_version, args.requested_version or None
        )
    except ValueError as exc:
        parser.exit(1, f"{exc}\n")
    print(version)


if __name__ == "__main__":
    main()
