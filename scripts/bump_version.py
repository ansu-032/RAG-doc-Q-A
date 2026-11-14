#!/usr/bin/env python3
"""Semantic version bumper for Citely.

Usage:
    python scripts/bump_version.py patch   # 1.0.0 -> 1.0.1
    python scripts/bump_version.py minor   # 1.0.0 -> 1.1.0
    python scripts/bump_version.py major   # 1.0.0 -> 2.0.0
    python scripts/bump_version.py 1.2.3   # Set explicit version
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INIT_FILE = ROOT / "src" / "__init__.py"
CONFIG_FILE = ROOT / ".bumpversion.cfg"


def get_current_version() -> str:
    content = INIT_FILE.read_text(encoding="utf-8")
    match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    if not match:
        raise ValueError(f"Could not find __version__ in {INIT_FILE}")
    return match.group(1)


def bump(current: str, part: str) -> str:
    parts = current.split(".")
    if len(parts) != 3:
        raise ValueError(f"Current version '{current}' is not standard semver (X.Y.Z)")
    major, minor, patch = map(int, parts)

    if part == "major":
        return f"{major + 1}.0.0"
    elif part == "minor":
        return f"{major}.{minor + 1}.0"
    elif part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    elif re.match(r"^\d+\.\d+\.\d+$", part):
        return part
    else:
        print("Usage: python scripts/bump_version.py [patch|minor|major|<x.y.z>]")
        sys.exit(1)


def update_file(path: Path, pattern: str, replacement: str) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text)
    if count > 0:
        path.write_text(updated, encoding="utf-8")
        print(f"Updated {path.relative_to(ROOT)}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/bump_version.py [patch|minor|major|<x.y.z>]")
        sys.exit(1)

    part = sys.argv[1].lower()
    current = get_current_version()
    new_version = bump(current, part)

    print(f"Bumping version: {current} -> {new_version}")

    # Update src/__init__.py
    update_file(
        INIT_FILE,
        r'__version__\s*=\s*["\'][^"\']+["\']',
        f'__version__ = "{new_version}"',
    )

    # Update .bumpversion.cfg
    update_file(
        CONFIG_FILE,
        r'current_version\s*=\s*[^\n]+',
        f'current_version = {new_version}',
    )

    print(f"\nSuccessfully bumped version to v{new_version}!")
    print("\nTo commit and tag this release:")
    print(f"  git add src/__init__.py .bumpversion.cfg")
    print(f'  git commit -m "chore(release): bump version to {new_version}"')
    print(f'  git tag -a v{new_version} -m "Release v{new_version}"')
    print(f"  git push origin main --tags")


if __name__ == "__main__":
    main()

