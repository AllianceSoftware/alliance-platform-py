#!/usr/bin/env python3
from pathlib import Path
import re
import subprocess

from pkg_resources import parse_version

# taken from https://www.python.org/dev/peps/pep-0440/#appendix-b-parsing-version-strings-with-regular-expressions
RE_VER = r"([1-9][0-9]*!)?(0|[1-9][0-9]*)(\.(0|[1-9][0-9]*))*((a|b|rc)(0|[1-9][0-9]*))?(\.post(0|[1-9][0-9]*))?(\.dev(0|[1-9][0-9]*))?"

version_header_re = re.compile(r"^##\s*(?P<ver>" + RE_VER + r")\s")
# automatically detect the current version from the highest version in the changelog section of the README
with (Path(__file__).parent.parent / "CHANGELOG.md").open("r") as f:
    file_contents = f.read()
    # get rid of html comments
    file_contents = re.sub("<!--.*?-->", "", file_contents, flags=re.MULTILINE | re.DOTALL)

    highest_ver = parse_version("0")
    ver_string = "0"
    for line in file_contents.split("\n"):
        if line.startswith("## "):
            match = version_header_re.match(line)
            if not match:
                raise ValueError(f"!!Cannot interpret header in {repr(line)}")
            try:
                cur_ver = parse_version(match.group("ver"))
            except ValueError as e:
                raise ValueError(f"Cannot interpret version in {repr(line)}") from e
            if cur_ver >= highest_ver:
                highest_ver = cur_ver
                ver_string = match.group("ver")

# Update version file
version_file = Path(__file__).parent.parent / "alliance_platform.frontend" / "__init__.py"
subprocess.run(
    [
        "sed",
        "-i",
        ".tmp",
        f's/__version__ *=.*/__version__ = "{ver_string}"/',
        str(version_file),
    ]
)
version_file.with_suffix(version_file.suffix + ".tmp").unlink()
# Update version in pyproject.toml
subprocess.run(["poetry", "version", ver_string], check=True)
# Generate build for distribution
subprocess.run("poetry build".split(), check=True)
