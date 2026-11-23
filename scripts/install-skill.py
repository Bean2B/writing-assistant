"""Link a selected bundled skill into a user-selected discovery directory."""
import argparse
from pathlib import Path
import re


def install(name, destination):
    available = Path(__file__).resolve().parents[1] / "skills"
    if not re.fullmatch(r"[a-z0-9-]+", name) or not (available / name / "SKILL.md").is_file():
        raise ValueError(f"Skill is not included in this edition: {name}")
    source = available / name
    destination = destination.expanduser().resolve()
    if destination == available or available in destination.parents:
        raise ValueError("Choose the harness discovery directory as the destination.")
    destination.mkdir(parents=True, exist_ok=True)
    link = destination / name
    try:
        link.symlink_to(source, target_is_directory=True)
    except FileExistsError:
        if not (link.is_symlink() and link.resolve() == source):
            raise ValueError(f"Destination is already in use: {link}") from None
    return link


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill", help="name of one directory under skills/")
    parser.add_argument("--to", required=True, type=Path, help="your harness's skill discovery directory")
    args = parser.parse_args()
    try:
        print(install(args.skill, args.to))
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f"{error}\n")
