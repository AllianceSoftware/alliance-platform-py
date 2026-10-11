"""System checks for the static ``{% ui %}`` components."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from alliance_platform.frontend.bundler import get_bundler
from alliance_platform.frontend.bundler.base import ResolveContext
from alliance_platform.frontend.settings import ap_frontend_settings
from django.core.checks import CheckMessage
from django.core.checks import Error
from django.core.exceptions import ImproperlyConfigured

from .html_components.contract import STATIC_CONTRACT_FILE
from .html_components.contract import SUPPORTED_STATIC_CONTRACT_VERSIONS
from .html_components.runtime import STATIC_RUNTIME_MODULE_PATH
from .html_components.runtime import STATIC_RUNTIME_RESOLVE_EXTENSIONS
from .icons import STATIC_SVG_DIR

_UI_PACKAGE = "@alliancesoftware/ui"
_ICONS_PACKAGE = "@alliancesoftware/icons"

# The ids of the errors about each package's contract file: (unusable file, version mismatch)
_CONTRACT_ERROR_IDS = {
    _UI_PACKAGE: ("alliance_platform_ui.E001", "alliance_platform_ui.E002"),
    _ICONS_PACKAGE: ("alliance_platform_ui.E003", "alliance_platform_ui.E004"),
}


def check_static_contract(app_configs: Any = None, **kwargs: Any) -> list[CheckMessage]:
    """Check that the installed npm packages provide the static contract the renderers support.

    Resolves ``static-contract.json`` in ``@alliancesoftware/ui`` and ``@alliancesoftware/icons``
    through the bundler and compares each ``version`` with
    :data:`~alliance_platform.ui.html_components.contract.SUPPORTED_STATIC_CONTRACT_VERSIONS`:

    - ``alliance_platform_ui.E001`` / ``E003``: the ui / icons contract file cannot be resolved or
      read, is not valid JSON or has no integer ``version``.
    - ``alliance_platform_ui.E002`` / ``E004``: the ui / icons contract version is not the
      supported one.
    - ``alliance_platform_ui.E005``: ``@alliancesoftware/icons/static-svg`` is not a directory.
    - ``alliance_platform_ui.E006``: the static runtime entry,
      ``@alliancesoftware/ui/static-runtime.auto.ts``, is not a file.

    Registered with :data:`~alliance_platform.frontend.checks.FRONTEND_BUILD_CHECK_TAG`, so it also
    runs inside ``extract_frontend_resources`` and fails the build.

    Returns no messages, and resolves nothing, when
    ``ALLIANCE_PLATFORM["FRONTEND"]["NODE_MODULES_DIR"]`` does not exist, as in a production image
    after the build: the run inside ``extract_frontend_resources`` verified the packages the build
    used. It also returns none while the bundler is not in development mode: the bundler then
    resolves assets through the build manifest rather than ``node_modules``, and the manifest lists
    neither contract file.

    Never raises: a failure to resolve or read a file is reported as the corresponding error.
    """

    try:
        node_modules_dir = Path(ap_frontend_settings.NODE_MODULES_DIR)
    except ImproperlyConfigured:
        return []
    if not node_modules_dir.exists() or not _bundler_resolves_from_source():
        return []
    messages: list[CheckMessage] = []
    for package in SUPPORTED_STATIC_CONTRACT_VERSIONS:
        messages += _check_contract_file(package)
    messages += _check_resolves_to(
        "static SVG icon directory",
        STATIC_SVG_DIR,
        directory=True,
        error_id="alliance_platform_ui.E005",
        package=_ICONS_PACKAGE,
    )
    messages += _check_resolves_to(
        "static runtime entry",
        STATIC_RUNTIME_MODULE_PATH,
        directory=False,
        error_id="alliance_platform_ui.E006",
        package=_UI_PACKAGE,
        resolve_extensions=STATIC_RUNTIME_RESOLVE_EXTENSIONS,
    )
    return messages


def _bundler_resolves_from_source() -> bool:
    try:
        return get_bundler().is_development()
    except Exception:
        # A bundler that does not implement is_development(), or one that cannot be loaded, which
        # resolving the files then reports
        return True


def _resolve(request_path: str, resolve_extensions: list[str] | None = None) -> Path:
    bundler = get_bundler()
    return bundler.resolve_path(
        request_path, ResolveContext(bundler.root_dir, None), resolve_extensions=resolve_extensions
    )


def _install_hint(package: str) -> str:
    version = SUPPORTED_STATIC_CONTRACT_VERSIONS[package]
    return f"Install the {package} release that ships static contract version {version}."


def _check_contract_file(package: str) -> list[CheckMessage]:
    supported = SUPPORTED_STATIC_CONTRACT_VERSIONS[package]
    invalid_id, mismatch_id = _CONTRACT_ERROR_IDS[package]
    request_path = f"{package}/{STATIC_CONTRACT_FILE}"

    def invalid(problem: str) -> list[CheckMessage]:
        return [Error(problem, hint=_install_hint(package), id=invalid_id)]

    try:
        path = _resolve(request_path)
    except Exception as exc:
        return invalid(f"Cannot resolve '{request_path}': {exc}")
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        return invalid(f"Cannot read '{path}': {exc}")
    try:
        contract = json.loads(text)
    except Exception as exc:
        return invalid(f"'{path}' is not valid JSON: {exc}")
    if not isinstance(contract, dict) or "version" not in contract:
        return invalid(f"'{path}' has no 'version'.")
    version = contract["version"]
    # Not isinstance(), as bool is a subclass of int
    if type(version) is not int:
        return invalid(f"'{path}' has a 'version' that is not an integer: {json.dumps(version)}.")
    if version == supported:
        return []
    if version < supported:
        hint = f"Upgrade {package} to the release that ships static contract version {supported}."
    else:
        hint = (
            f"Downgrade {package} to the release that ships static contract version {supported}, or "
            f"upgrade alliance-platform-ui to a release that supports version {version}."
        )
    return [
        Error(
            f"Static contract mismatch for {package}: installed version {version}, "
            f"alliance-platform-ui supports {supported} (read from '{path}').",
            hint=hint,
            id=mismatch_id,
        )
    ]


def _check_resolves_to(
    description: str,
    request_path: str,
    *,
    directory: bool,
    error_id: str,
    package: str,
    resolve_extensions: list[str] | None = None,
) -> list[CheckMessage]:
    kind = "directory" if directory else "file"
    try:
        path = _resolve(request_path, resolve_extensions)
        is_kind = path.is_dir() if directory else path.is_file()
        if is_kind:
            return []
        found = f"which is not a {kind}" if path.exists() else "which does not exist"
        message = f"The {description} '{request_path}' resolved to '{path}', {found}."
    except Exception as exc:
        message = f"Cannot resolve the {description} '{request_path}': {exc}"
    return [Error(message, hint=_install_hint(package), id=error_id)]
