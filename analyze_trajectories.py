"""Find distinct trajectory paths per category.

A trajectory's "path" is the ordered sequence of tool names in its `steps`.
The category is taken from the order id in the file name, e.g.
`trajectory_ORD-001-MOBILE_1790261924.json` -> category "MOBILE".
Within each category we report how many unique paths exist and which files
follow each one.
"""

import json
import re
from collections import defaultdict
from pathlib import Path

TRAJECTORY_DIR = Path(__file__).parent / "trajectories"

# Matches ORD-<num>-<CATEGORY> in the file name.
CATEGORY_RE = re.compile(r"ORD-\d+-([A-Za-z]+)")


def get_category(trajectory_file: Path) -> str:
    """Return the category (e.g. MOBILE) parsed from the file name."""
    match = CATEGORY_RE.search(trajectory_file.name)
    return match.group(1).upper() if match else "UNKNOWN"


def get_path(trajectory_file: Path) -> tuple[str, ...]:
    """Return the ordered tuple of tool names for a trajectory file."""
    with trajectory_file.open(encoding="utf-8") as f:
        data = json.load(f)
    return tuple(step["tool_name"] for step in data.get("steps", []))


def main() -> None:
    # category -> path -> list of files
    categories: dict[str, dict[tuple[str, ...], list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for trajectory_file in sorted(TRAJECTORY_DIR.glob("*.json")):
        category = get_category(trajectory_file)
        path = get_path(trajectory_file)
        categories[category][path].append(trajectory_file.name)

    total_files = sum(
        len(files) for paths in categories.values() for files in paths.values()
    )
    print(f"Total trajectory files : {total_files}")
    print(f"Total categories       : {len(categories)}\n")

    for category in sorted(categories):
        paths = categories[category]
        file_count = sum(len(files) for files in paths.values())
        ordered = sorted(paths.items(), key=lambda kv: len(kv[1]), reverse=True)
        divergent = len(paths) > 1

        print(f"== Category: {category} ==")
        print(
            f"   files: {file_count}, unique paths: {len(paths)}"
            f"{'  [DIVERGENT]' if divergent else ''}"
        )

        divergence_index = first_divergence(path for path, _ in ordered) if divergent else None

        for i, (path, files) in enumerate(ordered, start=1):
            print(f"   Path #{i} (count = {len(files)}, length = {len(path)} steps)")
            print("      [" + " > ".join(path) + "]")
            if divergence_index is not None:
                print(f"      diverges at step {divergence_index}: {path[divergence_index]}")
            for name in files:
                print(f"      file: {name}")
            print()
        print()


def first_divergence(paths) -> int | None:
    """Return the first step index where the given paths stop agreeing."""
    paths = list(paths)
    for index, tools in enumerate(zip(*paths)):
        if len(set(tools)) > 1:
            return index
    # All shared prefixes match; divergence is where the shortest path ends.
    lengths = {len(p) for p in paths}
    return min(lengths) if len(lengths) > 1 else None


if __name__ == "__main__":
    main()
