"""Link a selected bundled skill into a user-selected discovery directory."""
import argparse
import os
from pathlib import Path
import re
import sys
import subprocess


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
    if link.resolve() == source:
        return link
    try:
        link.symlink_to(source, target_is_directory=True)
    except FileExistsError:
        if link.resolve() != source:
            raise ValueError(f"Destination is already in use: {link}") from None
    except OSError as error:
        if os.name != "nt" or error.winerror != 1314:
            raise
        # An NTFS directory junction works without granting symbolic-link privileges.
        powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
        subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-Command",
                        "$ErrorActionPreference='Stop'; New-Item -ItemType Junction "
                        "-Path $env:WA_SKILL_LINK -Target $env:WA_SKILL_SOURCE | Out-Null"],
                       env={**os.environ, "WA_SKILL_LINK": str(link), "WA_SKILL_SOURCE": str(source)},
                       capture_output=True)
        if link.resolve() != source:
            raise ValueError("Could not register the skill. Choose a local NTFS discovery directory.") from error
    return link


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skill", help="name of one directory under skills/")
    parser.add_argument("--to", required=True, type=Path, help="your harness's skill discovery directory")
    args = parser.parse_args()
    try:
        link = install(args.skill, args.to)
        sys.stdout.buffer.write((str(link) + "\n").encode("utf-8"))
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(1, f"{error}\n")
