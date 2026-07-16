"""Worktree-aware development environment tooling for Alliance Platform projects."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version
import os

from .errors import DevError

DEV_PROTOCOL_VERSION = 1
STATE_SCHEMA_VERSION = 3
TMUX_PROTOCOL_VERSION = 1


def package_version() -> str:
    try:
        return version("alliance-platform-dev")
    except PackageNotFoundError:
        return "0.0.0+source"


def invocation_name() -> str:
    return os.environ.get("ALLIANCE_DEV_INVOCATION_NAME", "alliance-dev")


__all__ = [
    "DEV_PROTOCOL_VERSION",
    "DevError",
    "STATE_SCHEMA_VERSION",
    "TMUX_PROTOCOL_VERSION",
    "invocation_name",
    "package_version",
]
