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

_VENDOR_PREFIX_MAPPING = {
    "webkit": "Webkit",
    "moz": "Moz",
    "o": "O",
    "ms": "ms",
}


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
    transformed = {}
    for key, value in attrs.items():
        transformed_key = possible_standard_names.get(key, key)
        if transformed_key == "style" and isinstance(value, str):
            transformed[transformed_key] = _convert_inline_style_string(value)
        else:
            transformed[transformed_key] = value
    return transformed


def _split_css_declarations(style: str) -> list[str]:
    declarations = []
    current = []
    quote: str | None = None
    escaped = False
    paren_depth = 0

    for char in style:
        if quote:
            current.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue

        if char in {"'", '"'}:
            quote = char
            current.append(char)
            continue
        if char == "(":
            paren_depth += 1
            current.append(char)
            continue
        if char == ")" and paren_depth > 0:
            paren_depth -= 1
            current.append(char)
            continue
        if char == ";" and paren_depth == 0:
            declarations.append("".join(current))
            current = []
            continue
        current.append(char)

    declarations.append("".join(current))
    return declarations


def _split_css_property_and_value(declaration: str) -> tuple[str, str] | None:
    quote: str | None = None
    escaped = False
    paren_depth = 0
    split_index: int | None = None

    for index, char in enumerate(declaration):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue

        if char in {"'", '"'}:
            quote = char
            continue
        if char == "(":
            paren_depth += 1
            continue
        if char == ")" and paren_depth > 0:
            paren_depth -= 1
            continue
        if char == ":" and paren_depth == 0 and split_index is None:
            split_index = index

    if split_index is None:
        return None
    if quote is not None or paren_depth != 0:
        return None
    return declaration[:split_index], declaration[split_index + 1 :]


def _to_react_style_property_name(name: str) -> str:
    name = name.strip()
    if not name:
        return ""
    if name.startswith("--"):
        return name
    if "-" not in name:
        return name

    parts = [part for part in name.split("-") if part]
    if not parts:
        return ""

    first = parts[0].lower()
    if name.startswith("-"):
        first = _VENDOR_PREFIX_MAPPING.get(first, first)
    others = [part[:1].upper() + part[1:] for part in parts[1:]]
    camel_name = first + "".join(others)
    return camel_name


def _convert_inline_style_string(style: str) -> dict[str, str]:
    """Convert CSS inline style string to the object shape React expects.

    The returned values are plain strings, and will be escaped by normal codegen.
    """
    declarations = _split_css_declarations(style)
    output: dict[str, str] = {}
    for declaration in declarations:
        declaration = declaration.strip()
        if not declaration:
            continue
        split = _split_css_property_and_value(declaration)
        if not split:
            continue
        key, value = split
        normalized_key = _to_react_style_property_name(key)
        if not normalized_key:
            continue
        output[normalized_key] = value.strip()
    return output


class SSRExclusionMarker:
    """
    Marker base class for props that must be excluded from
    server-side rendering. Extend this class to ensure that
    any property referencing it (or a subclass) is recognised
    and omitted during SSR serialization.

    The base class should not be used directly as a prop key, to
    avoid accidentally overwriting existing properties by using
    the same dictionary key for both.
    """

    pass
