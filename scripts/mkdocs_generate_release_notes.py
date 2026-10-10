#!/usr/bin/env -S uv run
"""
Generate release notes from CHANGELOG.md and write them to docs/release-notes.md.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
CHANGELOG_MD = REPO_ROOT / "CHANGELOG.md"
RELEASE_NOTES_MD = REPO_ROOT / "docs" / "release-notes.md"


def get_releases() -> str:
    with CHANGELOG_MD.open() as f:
        changelog_md = f.read()

    sections = re.split(r"\n## (?=\[)", changelog_md)[1:]
    unreleased = sections.pop(0)
    # small sanity check
    if not unreleased.startswith("[Unreleased]"):
        raise ValueError("Unexpected CHANGELOG.md format, aborting!")

    return "\n\n".join(f"## {section.strip()}" for section in sections)


def main() -> None:
    releases = get_releases()

    release_notes_md = f"# Release Notes\n\n{releases}\n"

    with RELEASE_NOTES_MD.open("w") as f:
        f.write(release_notes_md)

    print("Successfully generated release notes!")


if __name__ == "__main__":
    main()
