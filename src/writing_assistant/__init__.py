"""Writing Assistant core. Optional modules are never loaded on import."""

def _package_version():
    from importlib.metadata import version
    from pathlib import Path

    source = Path(__file__).resolve().parent.parent
    project_file = source.parent / "pyproject.toml"
    # A source checkout must not inherit an older installed distribution's version.
    if source.name == "src" and project_file.is_file():
        import tomllib

        with project_file.open("rb") as stream:
            return tomllib.load(stream)["project"]["version"]
    return version("writing-assistant")


__version__ = _package_version()
