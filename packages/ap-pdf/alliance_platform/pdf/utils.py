import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from django.apps import apps
from django.conf import settings
from django.utils._os import safe_join


class StaticException(Exception):
    """An error that resulted from attempting to lookup a static asset."""


def get_static_url(static_roots: list[tuple[str | None, str]], path: str) -> Path:
    if not settings.DEBUG:
        # Check the collected static assets location first
        full_path = Path(safe_join(str(settings.STATIC_ROOT), path))
        if full_path.exists():
            return full_path

    for prefix, base_path in static_roots:
        check_path = path
        if prefix and path.startswith(prefix):
            check_path = path[len(prefix) :].lstrip("/")
        full_path = Path(safe_join(base_path, check_path))
        if full_path.exists():
            return full_path

    raise Exception(
        f"get_static_url() failed to return a meaningful url with static_roots: `{static_roots}`, path: `{path}`"
    )


def get_static_roots() -> list[tuple[str | None, str]]:
    """
    Get a list of locations to search for static roots.

    Normally the web server will translate requests under settings.STATIC_URL into a
    search of several directories.  We'll send the list of directories to the PDF
    renderer so that it can do direct filesystem lookup.

    :return: all of the places that static files can be found.
    """
    result: list[tuple[str | None, str]] = []
    static_dirs = settings.STATICFILES_DIRS
    for entry in static_dirs:
        base = None
        directory = entry
        if isinstance(entry, tuple):
            base, directory = entry
        result.append((base, str(directory)))
    for app_config in apps.get_app_configs():
        app_storage = Path(app_config.path, "static")
        if app_storage.is_dir():
            result.append((app_config.name, str(app_storage)))
    return result


def get_response_from_path(base: str, path: str) -> dict[str, Any]:
    path = str(Path(unquote(path))).lstrip("/")
    fullpath = Path(safe_join(base, path))
    return get_response_from_fullpath(fullpath, path)


def get_response_from_fullpath(fullpath: Path, path: str) -> dict[str, Any]:
    if fullpath.is_dir():
        raise StaticException("File is a directory: " + path)
    if not fullpath.exists():
        raise StaticException("File does not exist: " + path)
    stat_obj = fullpath.stat()
    content_type, encoding = mimetypes.guess_type(fullpath)
    with fullpath.open("rb") as f:
        return {
            "headers": {
                "Content-Length": stat_obj.st_size,
                "Content-Encoding": encoding,
            },
            "content_type": content_type or "application/octet-stream",
            "body": f.read(),
        }
