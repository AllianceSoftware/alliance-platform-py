import logging
from pathlib import Path
import re
import subprocess
from typing import Any

from packaging.specifiers import InvalidSpecifier
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion
from packaging.version import Version

from .dom_possible_standard_names import possible_standard_names

logger = logging.getLogger("alliance_platform.frontend")


def get_node_ver(node_path: str) -> Version | None:
    """
    Get the node version from a given path

    if raise_errors is not True then exceptions will be swallowed and None will be returned on error

    Args:
        node_path: The path to the node executable
    """
    try:
        proc = subprocess.Popen(
            [node_path, "--version"],
            stdout=subprocess.PIPE,
        )
        stdout, _ = proc.communicate()
        stdout_str = stdout.decode("utf-8").strip()
        returncode = proc.returncode
        if returncode != 0:
            raise ChildProcessError("Non-zero exit code")
        return Version(stdout_str.lstrip("v"))
    except (OSError, InvalidVersion, ChildProcessError):
        return None


def guess_node_path(nvmrc_path: Path) -> str | None:
    """Attempt to guess the node path based on the .nvmrc file

    Args:
        nvmrc_path: Path to the .nvmrc file
    """

    # nvm's version strings aren't quite the same as those
    # used by python but the overlap makes it good enough

    nvm_ver = (nvmrc_path).read_text().strip().lstrip("v")
    nvm_ver_re = re.compile(r"^v?" + re.escape(nvm_ver) + r"\b")
    try:
        nvm_specifier = SpecifierSet("==" + nvm_ver + ".*")
    except InvalidSpecifier as invalid_spec:
        raise ValueError(f"Cannot understand .nvmrc version specifier {nvm_ver}") from invalid_spec

    default_ver = get_node_ver("node")
    if default_ver is not None and default_ver in nvm_specifier:
        return "node"

    # default didn't work; try other options
    candidate_paths: list[str | Path] = [
        "/usr/local/bin/node",
        "/usr/bin/node",
    ]

    # add nvm node versions
    paths = Path.home() / ".nvm/versions/node"
    try:
        for p in paths.iterdir():
            if re.match(nvm_ver_re, p.name):
                candidate_paths.append(p / "bin/node")
    except IOError as ioe:
        logger.info(f"Error scanning nvm versions: {ioe}")

    # get version for each node candidate
    candidate_path_vers = {p: get_node_ver(str(p)) for p in candidate_paths}

    # look for the highest version that still matches
    matched_path_vers = [
        (ver, p) for p, ver in candidate_path_vers.items() if ver is not None and ver in nvm_specifier
    ]
    matched_path_vers.sort(reverse=True)

    try:
        return str(matched_path_vers[0][1])
    except IndexError:
        logger.error(f"Can't find node version {nvm_ver}")
        return None

    # TODO: if we can't find an exact match then do we want to fall back to
    # the closest version? (eg can't find v12 so use v13 instead)
    # if not re.match(, default_ver):
    #     warning(f"Wrong node version (expected {expected_ver}, got {default_ver}")


def transform_attribute_names(attrs: dict[str, Any]) -> dict[str, Any]:
    """Transform HTML attributes to use proper cased names for passing to JSX

    Example::

        >>> transform_attribute_names({ "class": "item" })

        { "className": "item" }
    """
    return {possible_standard_names.get(k, k): v for k, v in attrs.items()}
