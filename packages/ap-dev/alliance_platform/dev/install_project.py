from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import distribution
import json
import os
from pathlib import Path
import shlex
import stat
import tomllib
from urllib.parse import unquote
from urllib.parse import urlparse

from rich.console import Console
from rich.prompt import Confirm
from rich.prompt import IntPrompt
from rich.prompt import Prompt
from rich.syntax import Syntax

from . import package_version
from .errors import ConfigError
from .errors import DevError
from .identity import slugify

PORTLESS_DJANGO_SETTINGS = """CSRF_TRUSTED_ORIGINS = [
    "https://*.localhost",
    "http://*.localhost",
    "http://localhost",
    "http://127.0.0.1",
]

USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")"""
IGNORED_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".tox",
    ".venv",
    "migrations",
    "node_modules",
    "tests",
    "venv",
}


@dataclass(frozen=True)
class InstallResult:
    repo: Path
    launcher: Path
    config: Path
    created: tuple[Path, ...]
    updated: tuple[Path, ...]
    unchanged: tuple[Path, ...]


def resolve_install_root(
    project_dir: str | Path | None = None,
    *,
    environ: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> Path:
    environment = os.environ if environ is None else environ
    controlled = project_dir
    source = "install path"
    if controlled is None and "ALLIANCE_DEV_PROJECT_DIR" in environment:
        controlled = environment["ALLIANCE_DEV_PROJECT_DIR"]
        source = "ALLIANCE_DEV_PROJECT_DIR"
    if controlled is not None:
        candidate = Path(controlled).expanduser().resolve()
        if not (candidate / "pyproject.toml").is_file():
            raise ConfigError(f"Invalid project directory from {source}: {candidate}; missing pyproject.toml")
        return candidate

    candidate = (Path.cwd() if cwd is None else cwd).resolve()
    while True:
        if (candidate / "pyproject.toml").is_file():
            return candidate
        if candidate.parent == candidate:
            raise ConfigError(f"Could not find pyproject.toml from {cwd or Path.cwd()}")
        candidate = candidate.parent


def _project_name(repo: Path) -> str:
    try:
        with (repo / "pyproject.toml").open("rb") as file:
            value = tomllib.load(file)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"Could not read {repo / 'pyproject.toml'}: {error}") from error
    project = value.get("project")
    name = project.get("name") if isinstance(project, dict) else None
    if isinstance(name, str) and name.strip():
        return name.strip()
    tool = value.get("tool")
    poetry = tool.get("poetry") if isinstance(tool, dict) else None
    poetry_name = poetry.get("name") if isinstance(poetry, dict) else None
    if isinstance(poetry_name, str) and poetry_name.strip():
        return poetry_name.strip()
    return repo.name


def _walk_files(repo: Path, name: str) -> list[Path]:
    return sorted(
        (
            path
            for path in repo.rglob(name)
            if not any(part in IGNORED_DIRECTORIES for part in path.relative_to(repo).parts)
        ),
        key=lambda path: (len(path.relative_to(repo).parts), str(path.relative_to(repo))),
    )


def _manage_candidates(repo: Path) -> list[Path]:
    candidates = _walk_files(repo, "manage.py")
    return sorted(
        candidates,
        key=lambda path: (
            path.relative_to(repo) != Path("django-root/manage.py"),
            len(path.relative_to(repo).parts),
            str(path.relative_to(repo)),
        ),
    )


def _choose_path(
    console: Console,
    label: str,
    repo: Path,
    candidates: list[Path],
    *,
    assume_yes: bool,
    required: bool,
) -> Path | None:
    if not candidates:
        if required:
            raise DevError(f"Could not find {label}; specify it explicitly")
        return None
    if assume_yes or len(candidates) == 1:
        return candidates[0]
    console.print(f"\n[bold]{label} candidates[/bold]")
    for index, candidate in enumerate(candidates, start=1):
        console.print(f"  {index}. {candidate.relative_to(repo)}")
    choice = IntPrompt.ask("Select a file", choices=[str(index) for index in range(1, len(candidates) + 1)])
    return candidates[choice - 1]


def _default_tool_source() -> str:
    package_root = Path(__file__).resolve().parents[2]
    version = package_version()
    if (package_root / "pyproject.toml").is_file() and version.startswith("0.0.0"):
        return str(package_root)
    if version.startswith("0.0.0"):
        # uv records a local `--from PATH` source in PEP 610 metadata. Preserve
        # that source in the generated launcher so local package testing stays local.
        try:
            direct_url = distribution("alliance-platform-dev").read_text("direct_url.json")
            metadata = json.loads(direct_url) if direct_url else {}
            parsed = urlparse(metadata.get("url", ""))
            if parsed.scheme == "file":
                return unquote(parsed.path)
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            pass
    return f"alliance-platform-dev=={version}"


def _launcher_contents(tool_source: str) -> str:
    default_source = shlex.quote(tool_source)
    return f"""#!/bin/bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd -P)"

if ! command -v uv >/dev/null 2>&1; then
    echo "Missing 'uv'. Install it from https://docs.astral.sh/uv/" >&2
    exit 1
fi

export DEV_INVOKE_PATH="$PATH"
if [[ "${{VIRTUAL_ENV+x}}" == x ]]; then
    export DEV_INVOKE_VIRTUAL_ENV_SET=1
    export DEV_INVOKE_VIRTUAL_ENV="$VIRTUAL_ENV"
else
    export DEV_INVOKE_VIRTUAL_ENV_SET=0
    export DEV_INVOKE_VIRTUAL_ENV=
fi
if [[ "${{UV_RUN_RECURSION_DEPTH+x}}" == x ]]; then
    export DEV_INVOKE_UV_RUN_RECURSION_DEPTH_SET=1
    export DEV_INVOKE_UV_RUN_RECURSION_DEPTH="$UV_RUN_RECURSION_DEPTH"
else
    export DEV_INVOKE_UV_RUN_RECURSION_DEPTH_SET=0
    export DEV_INVOKE_UV_RUN_RECURSION_DEPTH=
fi

default_tool_source={default_source}
tool_source="${{ALLIANCE_DEV_TOOL_SOURCE:-$default_tool_source}}"
uvx_cache_args=()
case "$tool_source" in
    /*|./*|../*|file://*) uvx_cache_args=(--no-cache) ;;
esac
export ALLIANCE_DEV_PROJECT_DIR="$repo_dir"
export ALLIANCE_DEV_INVOCATION_NAME="bin/dev"

exec uvx --isolated --no-env-file "${{uvx_cache_args[@]}}" --from "$tool_source" alliance-dev "$@"
"""


def _config_contents(project_id: str, django_cwd: str) -> str:
    return f"""# Committed defaults for bin/dev. User overrides live under
# ~/.config/alliance/dev/{project_id}/ and worktree overrides under .dev-server/.

project_id = {json.dumps(project_id)}

django_port_base = 8000
vite_port_base = 5173
portless = "auto"
startup_timeout = 60.0
database_template = ""

createdevdata_args = []
db_prepare_command = []
django_cwd = {json.dumps(django_cwd)}
vite_cwd = "."
manage_command = ["uv", "run", "python", "manage.py"]
django_command = ["uv", "run", "python", "manage.py", "runserver"]
vite_command = ["yarn", "dev"]
test_command = ["bin/run-tests-django.sh"]
jstest_command = ["bin/run-tests-frontend.sh"]
lint_command = ["bin/lint.sh"]
check_command = ["bin/check.sh"]

# Add project-specific services as argv arrays:
# [[extra_processes]]
# name = "worker"
# command = ["uv", "run", "python", "manage.py", "run_worker"]
# cwd = {json.dumps(django_cwd)}
# required = true
"""


def _write_file(
    path: Path,
    contents: str,
    *,
    console: Console,
    assume_yes: bool,
    force: bool,
    executable: bool = False,
) -> str:
    if path.exists():
        if path.read_text() == contents:
            if executable:
                path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            return "unchanged"
        replace = force or (
            not assume_yes and Confirm.ask(f"Replace existing {path}?", default=False, console=console)
        )
        if not replace:
            raise DevError(f"Refusing to overwrite existing {path}; review it or pass --force")
        state = "updated"
    else:
        state = "created"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents)
    if executable:
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return state


def _record(path: Path, state: str, records: dict[str, list[Path]]) -> None:
    records[state].append(path)


def _confirm_project_id(console: Console, suggested: str, assume_yes: bool) -> str:
    if assume_yes:
        return suggested
    while True:
        value = Prompt.ask("Project ID", default=suggested, console=console).strip()
        if value == slugify(value) and value:
            return value
        console.print("[red]Use a lowercase slug containing letters, digits, and hyphens.[/red]")


def install_project(
    repo: Path,
    *,
    assume_yes: bool = False,
    force: bool = False,
    tool_source: str | None = None,
    django_cwd: Path | None = None,
    console: Console | None = None,
) -> InstallResult:
    repo = repo.resolve()
    output = console or Console()
    if not assume_yes and not output.is_terminal:
        raise DevError("Interactive installation requires a terminal; pass --yes to accept defaults")

    project_name = _project_name(repo)
    suggested_id = slugify(project_name)
    if not suggested_id:
        raise ConfigError(f"Could not derive a project ID from {project_name!r}")
    project_id = _confirm_project_id(output, suggested_id, assume_yes)

    manage = (
        (repo / django_cwd).resolve() / "manage.py"
        if django_cwd is not None
        else _choose_path(
            output,
            "Django manage.py",
            repo,
            _manage_candidates(repo),
            assume_yes=assume_yes,
            required=True,
        )
    )
    assert manage is not None
    if not manage.is_file() or not manage.is_relative_to(repo):
        raise DevError(f"Invalid Django working directory: {manage.parent}")
    resolved_django_cwd = manage.parent

    launcher = repo / "bin" / "dev"
    config = repo / "config" / "dev.toml"
    records: dict[str, list[Path]] = {"created": [], "updated": [], "unchanged": []}
    source = tool_source or _default_tool_source()
    _record(
        launcher,
        _write_file(
            launcher,
            _launcher_contents(source),
            console=output,
            assume_yes=assume_yes,
            force=force,
            executable=True,
        ),
        records,
    )
    _record(
        config,
        _write_file(
            config,
            _config_contents(
                project_id,
                str(resolved_django_cwd.relative_to(repo)) or ".",
            ),
            console=output,
            assume_yes=assume_yes,
            force=force,
        ),
        records,
    )

    output.print("\n[bold green]Alliance development environment installed.[/bold green]")
    output.print(f"  Project: {project_id}")
    output.print(f"  Django:  {resolved_django_cwd.relative_to(repo)}")
    output.print("  Vite:    .")
    output.print(f"  Source:  {source}")
    output.print("\n[bold]Add these settings to your development settings module (normally dev.py):[/bold]")
    output.print(Syntax(PORTLESS_DJANGO_SETTINGS, "python", theme="ansi_dark", padding=1))
    output.print(
        "CSRF_TRUSTED_ORIGINS allows Portless localhost subdomains. The forwarded-host setting "
        "preserves the browser hostname for tenant/subdomain routing, and the proxy SSL header "
        "tells Django that the original browser request used HTTPS. Keep these settings limited "
        "to development, where Portless is the trusted proxy."
    )
    output.print("\nNext: review config/dev.toml, then run bin/dev doctor and bin/dev up.")
    return InstallResult(
        repo=repo,
        launcher=launcher,
        config=config,
        created=tuple(records["created"]),
        updated=tuple(records["updated"]),
        unchanged=tuple(records["unchanged"]),
    )
