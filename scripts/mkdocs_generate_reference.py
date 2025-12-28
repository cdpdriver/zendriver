#!/usr/bin/env -S uv run
"""
Automatically generate code reference pages under docs/reference.
"""

import shutil
from pathlib import Path
from typing import Any

import yaml

PACKAGE_NAME = "zendriver"
REPO_ROOT = Path(__file__).parent.parent
PACKAGE_ROOT = REPO_ROOT / PACKAGE_NAME
REFERENCE_DOCS_ROOT = REPO_ROOT / "docs" / "reference"
MKDOCS_YML = REPO_ROOT / "mkdocs.yml"


def clean_reference_docs_dir() -> None:
    if not REFERENCE_DOCS_ROOT.exists():
        return

    for path in REFERENCE_DOCS_ROOT.glob("*"):
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()


def get_documented_modules() -> list[Path]:
    return [
        path.relative_to(PACKAGE_ROOT)
        for path in (
            sorted(PACKAGE_ROOT.rglob("core/*.py"))
            + sorted(PACKAGE_ROOT.rglob("cdp/*.py"))
        )
        if not path.stem.startswith("_")
    ]


def load_mkdocs_yml() -> dict[str, Any]:
    mkdocs_yml_path = MKDOCS_YML
    with mkdocs_yml_path.open() as f:
        return yaml.safe_load(f)  # type: ignore


def write_mkdocs_yml(mkdocs_yml: dict[str, Any]) -> None:
    mkdocs_yml_path = MKDOCS_YML
    with mkdocs_yml_path.open("w") as f:
        yaml.safe_dump(mkdocs_yml, f)


def get_nav_item_by_title(
    nav_section: list[dict[str, Any]], title: str
) -> list[dict[str, Any]]:
    for item in nav_section:
        if title in item:
            return item[title]  # type: ignore

    raise ValueError(f"Title '{title}' not found in nav section")


def write_doc_md(doc_path: Path, module: str) -> None:
    doc_path.parent.mkdir(parents=True, exist_ok=True)

    with doc_path.open("w") as f:
        f.write(f"::: {PACKAGE_NAME}.{module}\n")


def add_nav_items(reference_docs: list[Path]) -> None:
    mkdocs_yml = load_mkdocs_yml()
    current_section = mkdocs_yml["nav"]
    reference_section = get_nav_item_by_title(current_section, "Reference")
    reference_section.clear()

    for doc_path in reference_docs:
        path_parts = list(doc_path.relative_to(REFERENCE_DOCS_ROOT).parts)
        current_section = reference_section
        while len(path_parts) > 1:
            current_part = path_parts[0]
            try:
                current_section = get_nav_item_by_title(current_section, current_part)
            except ValueError:
                current_section.append({current_part: []})
                current_section = current_section[-1][current_part]

            path_parts = path_parts[1:]

        current_section.append(
            {
                path_parts[0].removesuffix(".md"): doc_path.relative_to(
                    REPO_ROOT / "docs"
                ).as_posix()
            }
        )

    write_mkdocs_yml(mkdocs_yml)


def main() -> None:
    clean_reference_docs_dir()

    reference_docs: list[Path] = []
    for module_path in get_documented_modules():
        doc_path = REFERENCE_DOCS_ROOT / module_path.with_suffix(".md")
        module = ".".join(module_path.with_suffix("").parts)

        print(f"Generating {doc_path}...")
        write_doc_md(doc_path, module)
        reference_docs.append(doc_path)

    add_nav_items(reference_docs)


if __name__ == "__main__":
    main()
