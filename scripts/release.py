#!/usr/bin/env -S uv run
# /// script
# dependencies = [
#   "requests"
# ]
# ///
"""
Generate and publish a new release of the project.

Intended for use by maintainers only.

This script will:
- Read pyproject.toml to automatically determine the new version number
- Update pyproject.toml with the new version number
- Update zendriver/_version.py with the new version number
- Run `uv sync` to update the lock file
- Update CHANGELOG.md, creating a new section for the release and moving unreleased changes there
  (any text between the [Unreleased] header and the ### Fixed header is kept as a note for the release)
- Commit and push changes to pyproject.toml, uv.lock, zendriver/_version.py, and CHANGELOG.md
- Create and push a git tag for the new version
- Create a new release on GitHub ($GITHUB_TOKEN environment variable must be set)

Usage:
    uv run python release.py [--patch | --minor | --major] [--dry-run]
"""

import argparse
import datetime
import os
import re
import subprocess
import sys
from pathlib import Path

# installed via inline script metadata, but mypy doesn't know that
import requests

REPO_ROOT = Path(__file__).parent.parent

# for creating GitHub release
GITHUB_REPO_SLUG = "cdpdriver/zendriver"

PYPROJECT_TOML = Path("pyproject.toml")
PYPROJECT_VERSION_REGEX = r"^version = \"(?P<version>\d+\.\d+\.\d+)\"$"

VERSION_PY = Path("zendriver/_version.py")

CHANGELOG_MD = Path("CHANGELOG.md")
CHANGELOG_MD_UNRELEASED_REGEX = (
    r"## \[Unreleased\]\n(?P<note>[\s\S]*?)"
    r"### Fixed\n(?P<fixed>[\s\S]+?)"
    r"### Added\n(?P<added>[\s\S]+?)"
    r"### Changed\n(?P<changed>[\s\S]+?)"
    r"### Removed\n(?P<removed>[\s\S]+?)"
    r"##"
)
CHANGELOG_MD_UNRELEASED_TEMPLATE = (
    "## [Unreleased]\n\n"
    "### Fixed\n\n"
    "### Added\n\n"
    "### Changed\n\n"
    "### Removed\n\n"
)


def set_working_directory() -> None:
    print(f"Changing working directory to {REPO_ROOT}")
    os.chdir(REPO_ROOT)


def ensure_clean_working_directory(message: str | None = None) -> None:
    if subprocess.run(["git", "diff", "--quiet"]).returncode != 0:
        print(
            message
            or "Error: Working directory is not clean, please commit or stash changes"
        )
        sys.exit(1)


def ensure_on_main_branch() -> None:
    current_branch = (
        subprocess.run(["git", "branch", "--show-current"], capture_output=True)
        .stdout.decode()
        .strip()
    )
    if current_branch != "main":
        print("Error: Not on the main branch")
        sys.exit(1)


def ensure_github_token() -> str:
    github_token = os.environ.get("CDPDRIVER_GITHUB_TOKEN")
    if not github_token:
        print("Error: $CDPDRIVER_GITHUB_TOKEN environment variable must be set")
        sys.exit(1)
    return github_token


def get_current_version() -> str:
    content = PYPROJECT_TOML.read_text()
    if match := re.search(PYPROJECT_VERSION_REGEX, content, re.MULTILINE):
        return match.group("version")

    print("Error: Could not find version in pyproject.toml")
    sys.exit(1)


def get_new_version(current_version: str, patch: bool, minor: bool, major: bool) -> str:
    current_major, current_minor, current_patch = map(int, current_version.split("."))
    if major:
        return f"{current_major + 1}.0.0"
    if minor:
        return f"{current_major}.{current_minor + 1}.0"
    if patch:
        return f"{current_major}.{current_minor}.{current_patch + 1}"
    raise ValueError("No version increment specified")


def write_new_version_to_pyproject(new_version: str, dryrun: bool) -> None:
    content = PYPROJECT_TOML.read_text()
    new_content = re.sub(
        PYPROJECT_VERSION_REGEX,
        f'version = "{new_version}"',
        content,
        flags=re.MULTILINE,
    )
    assert content != new_content, "No changes made to pyproject.toml"

    if dryrun:
        print(f"Would update {PYPROJECT_TOML} with new version: {new_version}")
        return
    PYPROJECT_TOML.write_text(new_content)


def write_new_version_to_version_py(new_version: str, dryrun: bool) -> None:
    if dryrun:
        print(f"Would update {VERSION_PY} with new version: {new_version}")
        return

    VERSION_PY.write_text(f'__version__ = "{new_version}"\n')


def sync_lock_file(dryrun: bool) -> None:
    if dryrun:
        print("Would run `uv sync` to update the lock file")
        return

    subprocess.run(["uv", "sync"], check=True)


def write_changelog(new_version: str, dryrun: bool) -> str:
    changelog_content = CHANGELOG_MD.read_text()
    match = re.search(CHANGELOG_MD_UNRELEASED_REGEX, changelog_content)
    if not match:
        print("Error: Could not parse CHANGELOG.md")
        sys.exit(1)
    unreleased_changes = {
        section: match.group(section).strip() for section in match.groupdict()
    }
    if not any(content for content in unreleased_changes.values()):
        print("Error: No changes found in CHANGELOG.md")
        sys.exit(1)

    new_version_parts = [
        f"### {section.title()}\n\n{unreleased_changes[section]}"
        for section in ("fixed", "added", "changed", "removed")
        if unreleased_changes[section]
    ]
    if unreleased_changes["note"]:
        new_version_parts.insert(0, unreleased_changes["note"])
    new_version_changes = "\n\n".join(new_version_parts)

    new_version_section = (
        f"## [{new_version}] - {datetime.date.today()}\n\n{new_version_changes}"
    )
    print(f"Changelog:\n{new_version_section}")

    new_changelog_content = re.sub(
        CHANGELOG_MD_UNRELEASED_REGEX,
        f"{CHANGELOG_MD_UNRELEASED_TEMPLATE}{new_version_section}\n\n##",
        changelog_content,
    )

    if dryrun:
        print("Would update CHANGELOG.md with new version section")
    else:
        CHANGELOG_MD.write_text(new_changelog_content)

    return new_version_changes


def show_diff() -> None:
    subprocess.run(["git", "diff", "--color"])


def commit_and_push_changes(new_version: str, dryrun: bool) -> None:
    if dryrun:
        print("Would commit and push changes to the repository")
        return

    files_to_add = [
        "pyproject.toml",
        "uv.lock",
        "CHANGELOG.md",
        "zendriver/_version.py",
    ]
    subprocess.run(["git", "add"] + files_to_add)
    subprocess.run(["git", "commit", "-m", f"Bump version to {new_version}"])
    ensure_clean_working_directory("Error: Working directory is not clean after commit")
    subprocess.run(["git", "push"])


def create_and_push_tag(new_version: str, dryrun: bool) -> None:
    if dryrun:
        print(f"Would create and push tag: v{new_version}")
        return

    subprocess.run(["git", "tag", f"v{new_version}"])
    subprocess.run(["git", "push", "--tags"])


def create_github_release(new_version: str, body: str, dryrun: bool) -> None:
    if dryrun:
        print(f"Would create a new release on GitHub for tag {new_version}")
        return

    github_token = ensure_github_token()

    response = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPO_SLUG}/releases",
        headers={"Authorization": f"token {github_token}"},
        json={"tag_name": f"v{new_version}", "name": f"v{new_version}", "body": body},
    )
    response.raise_for_status()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate and publish a new release of the project."
    )
    parser.add_argument(
        "--patch",
        action="store_true",
        help="Increment the patch version number (e.g. 1.0.0 -> 1.0.1)",
    )
    parser.add_argument(
        "--minor",
        action="store_true",
        help="Increment the minor version number (e.g. 1.0.0 -> 1.1.0)",
    )
    parser.add_argument(
        "--major",
        action="store_true",
        help="Increment the major version number (e.g. 1.0.0 -> 2.0.0)",
    )
    parser.add_argument(
        "--dryrun",
        action="store_true",
        help="Perform a dry run, making no changes to the repository",
    )
    return parser.parse_args()


def main() -> None:
    set_working_directory()
    args = parse_args()
    # prechecks
    if not args.patch and not args.minor and not args.major:
        print("No version increment specified, defaulting to --patch")
        args.patch = True
    elif sum([args.patch, args.minor, args.major]) > 1:
        print("Error: Only one of --patch, --minor, or --major can be specified")
        sys.exit(1)
    if not args.dryrun:
        ensure_clean_working_directory()
        ensure_on_main_branch()
        ensure_github_token()
    if args.dryrun:
        print("Running in dry-run mode, no changes will be made to the repository")

    # calculate new version
    current_version = get_current_version()
    print(f"Detected current version: {current_version}")
    new_version = get_new_version(current_version, args.patch, args.minor, args.major)
    print(f"Calculated new version: {new_version}")

    # create and push the new release
    write_new_version_to_pyproject(new_version, args.dryrun)
    write_new_version_to_version_py(new_version, args.dryrun)
    sync_lock_file(args.dryrun)
    changelog = write_changelog(new_version, args.dryrun)

    show_diff()
    continue_prompt = input("Continue with release? [Y/n]: ")
    if continue_prompt.lower() not in ("y", "yes", ""):
        print("Aborting!")
        sys.exit(1)

    commit_and_push_changes(new_version, args.dryrun)
    create_and_push_tag(new_version, args.dryrun)
    create_github_release(new_version, changelog, args.dryrun)


if __name__ == "__main__":
    main()
