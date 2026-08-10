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
HOOK_WRAPPER_PATH = Path("bin/run-with-dev-env-if-managed")
MANAGED_HUSKY_HOOKS = ("pre-commit", "pre-push")
VERIFICATION_SCRIPTS = {
    "test": Path("bin/run-tests-django.sh"),
    "jstest": Path("bin/run-tests-frontend.sh"),
    "lint": Path("bin/lint.sh"),
    "check": Path("bin/check.sh"),
}
IGNORED_DIRECTORIES = {
    ".git",
    ".mypy_cache",
    ".tox",
    ".venv",
    ".claude",
    ".codex",
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
export ALLIANCE_DEV_PROJECT_DIR="$repo_dir"
export ALLIANCE_DEV_INVOCATION_NAME="bin/dev"

if [[ -n "${{ALLIANCE_DEV_UV_CACHE_DIR:-}}" ]]; then
    uv_cache_dir="$ALLIANCE_DEV_UV_CACHE_DIR"
elif [[ -n "${{UV_CACHE_DIR:-}}" ]]; then
    uv_cache_dir="$UV_CACHE_DIR"
else
    cache_root="${{TMPDIR:-/tmp}}"
    default_uv_cache_root="${{cache_root%/}}/alliance-dev-${{UID:-$(id -u)}}"
    uv_cache_dir="$default_uv_cache_root/uv-cache"
    if ! (umask 077 && mkdir -p "$uv_cache_dir" && chmod 700 "$default_uv_cache_root" "$uv_cache_dir"); then
        echo "Cannot create the uv cache at '$uv_cache_dir'. Set ALLIANCE_DEV_UV_CACHE_DIR to a writable directory." >&2
        exit 1
    fi
fi
if ! mkdir -p "$uv_cache_dir"; then
    echo "Cannot create the uv cache at '$uv_cache_dir'. Set ALLIANCE_DEV_UV_CACHE_DIR to a writable directory." >&2
    exit 1
fi

exec uvx --cache-dir "$uv_cache_dir" --isolated --no-env-file --from "$tool_source" alliance-dev "$@"
"""


def _hook_wrapper_contents() -> str:
    return """#!/bin/bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$repo_dir"

if [[ $# -eq 0 ]]; then
    echo "Usage: bin/run-with-dev-env-if-managed <command> [args...]" >&2
    exit 2
fi

hook_environment="${BIN_DEV_HOOK_ENV:-auto}"
case "$hook_environment" in
    auto)
        if [[ -f "$repo_dir/.dev-server/state.json" ]]; then
            echo "→ Git hook environment: bin/dev state found; using the managed worktree environment." >&2
            exec "$repo_dir/bin/dev" run -- "$@"
        fi
        echo "→ Git hook environment: no bin/dev state; using the inherited environment." >&2
        exec "$@"
        ;;
    off)
        echo "→ Git hook environment: BIN_DEV_HOOK_ENV=off; using the inherited environment." >&2
        exec "$@"
        ;;
    *)
        echo "Invalid BIN_DEV_HOOK_ENV '$hook_environment'; expected 'auto' or 'off'." >&2
        exit 2
        ;;
esac
"""


def _wrap_husky_hook(contents: str) -> str | None:
    if str(HOOK_WRAPPER_PATH) in contents:
        return contents
    lines = contents.splitlines(keepends=True)
    command_end: int | None = None
    for index in range(len(lines) - 1, -1, -1):
        stripped = lines[index].strip()
        if stripped and not stripped.startswith("#"):
            command_end = index
            break
    if command_end is None:
        return None
    command_start = command_end
    while command_start > 0 and lines[command_start - 1].rstrip().endswith("\\"):
        command_start -= 1
    command = "".join(lines[command_start : command_end + 1])
    first_line = lines[command_start]
    indent = first_line[: len(first_line) - len(first_line.lstrip())]
    stripped_command = command[len(indent) :]
    if stripped_command.split(maxsplit=1)[0] in {
        ".",
        "done",
        "esac",
        "exit",
        "fi",
        "return",
        "source",
        "then",
        "}",
    }:
        return None
    if stripped_command.startswith("exec "):
        stripped_command = stripped_command[5:]
    replacement = f"{indent}exec ./{HOOK_WRAPPER_PATH} {stripped_command}"
    return "".join([*lines[:command_start], replacement, *lines[command_end + 1 :]])


def _package_scripts(repo: Path) -> dict[str, str]:
    path = repo / "package.json"
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    scripts = value.get("scripts") if isinstance(value, dict) else None
    if not isinstance(scripts, dict):
        return {}
    return {name: command for name, command in scripts.items() if isinstance(command, str)}


def _vitest_command(repo: Path) -> tuple[tuple[str, ...], str] | None:
    scripts = _package_scripts(repo)
    for name in ("test:run", "jstest", "test", "vitest"):
        script = scripts.get(name)
        if script is None:
            continue
        try:
            tokens = shlex.split(script)
        except ValueError:
            continue
        if not any(Path(token).name == "vitest" for token in tokens):
            continue
        command = ["yarn", name]
        if "run" not in tokens and "--run" not in tokens:
            command.append("--run")
        return tuple(command), f"package.json script {name}"
    return None


def _prompt_for_command(console: Console, label: str) -> tuple[str, ...]:
    while True:
        value = Prompt.ask(
            f"{label} command (leave blank to disable)",
            default="",
            show_default=False,
            console=console,
        ).strip()
        if not value:
            return ()
        try:
            command = tuple(shlex.split(value))
        except ValueError as error:
            console.print(f"[red]Invalid command: {error}[/red]")
            continue
        if command:
            return command


def _verification_commands(
    repo: Path,
    manage: Path,
    *,
    console: Console,
    assume_yes: bool,
) -> dict[str, tuple[str, ...]]:
    commands: dict[str, tuple[str, ...]] = {}
    sources: dict[str, str] = {}
    for name, relative_path in VERIFICATION_SCRIPTS.items():
        candidate = repo / relative_path
        if candidate.is_file() and os.access(candidate, os.X_OK):
            commands[name] = (relative_path.as_posix(),)
            sources[name] = f"existing {relative_path.as_posix()}"

    if "test" not in commands:
        commands["test"] = (
            "uv",
            "run",
            "python",
            manage.relative_to(repo).as_posix(),
            "test",
        )
        sources["test"] = "Django manage.py"
    if "jstest" not in commands and (vitest := _vitest_command(repo)) is not None:
        commands["jstest"], sources["jstest"] = vitest

    labels = {
        "test": "Django tests",
        "jstest": "Frontend tests",
        "lint": "Lint",
        "check": "Full check",
    }
    if not assume_yes:
        for name, label in labels.items():
            if name not in commands:
                command = _prompt_for_command(console, label)
                commands[name] = command
                sources[name] = "entered during installation" if command else "not configured"
    for name in labels:
        commands.setdefault(name, ())
        sources.setdefault(name, "not configured")

    console.print("\n[bold]Verification commands[/bold]")
    for name, label in labels.items():
        rendered = shlex.join(commands[name]) if commands[name] else "not configured"
        console.print(f"  {label + ':':<17} {rendered} [dim]({sources[name]})[/dim]")
    return commands


def _config_contents(
    project_id: str,
    django_cwd: str,
    verification_commands: dict[str, tuple[str, ...]],
) -> str:
    return f"""# Committed defaults for bin/dev. User overrides live under
# ~/.config/alliance/dev/{project_id}/ and worktree overrides under .dev-server/.

project_id = {json.dumps(project_id)}

django_port_base = 8000
vite_port_base = 5173
portless = "auto"
startup_timeout = 60.0
database_template = ""
database_template_strategy = "default"

createdevdata_args = []
db_prepare_command = []
django_cwd = {json.dumps(django_cwd)}
vite_cwd = "."
manage_command = ["uv", "run", "python", "manage.py"]
django_command = ["uv", "run", "python", "manage.py", "runserver"]
vite_command = ["yarn", "dev"]
test_command = {json.dumps(list(verification_commands["test"]))}
jstest_command = {json.dumps(list(verification_commands["jstest"]))}
lint_command = {json.dumps(list(verification_commands["lint"]))}
check_command = {json.dumps(list(verification_commands["check"]))}

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
    verification_commands = _verification_commands(
        repo,
        manage,
        console=output,
        assume_yes=assume_yes,
    )

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
                verification_commands,
            ),
            console=output,
            assume_yes=assume_yes,
            force=force,
        ),
        records,
    )

    husky_hooks = [repo / ".husky" / name for name in MANAGED_HUSKY_HOOKS]
    existing_hooks = [path for path in husky_hooks if path.is_file()]
    hook_updates = {
        path: wrapped
        for path in existing_hooks
        if (wrapped := _wrap_husky_hook(path.read_text())) is not None
    }
    unwrapped_hooks = [path for path, contents in hook_updates.items() if contents != path.read_text()]
    unsupported_hooks = [path for path in existing_hooks if path not in hook_updates]
    hook_prompt_required = bool(unwrapped_hooks or unsupported_hooks)
    update_hooks = bool(existing_hooks) and (
        not hook_prompt_required
        or assume_yes
        or Confirm.ask(
            "Update pre-commit/pre-push Husky hooks to use the managed worktree environment?",
            default=True,
            console=output,
        )
    )
    hooks_enabled = update_hooks and bool(hook_updates)
    if hooks_enabled:
        hook_wrapper = repo / HOOK_WRAPPER_PATH
        _record(
            hook_wrapper,
            _write_file(
                hook_wrapper,
                _hook_wrapper_contents(),
                console=output,
                assume_yes=assume_yes,
                force=force,
                executable=True,
            ),
            records,
        )
        for path, contents in hook_updates.items():
            _record(
                path,
                _write_file(
                    path,
                    contents,
                    console=output,
                    assume_yes=assume_yes,
                    force=True,
                    executable=True,
                ),
                records,
            )
    if update_hooks and unsupported_hooks:
        output.print(
            "[yellow]Could not safely update these Husky hooks; wrap their project command "
            f"manually with ./{HOOK_WRAPPER_PATH}: "
            f"{', '.join(str(path.relative_to(repo)) for path in unsupported_hooks)}[/yellow]"
        )

    output.print("\n[bold green]Alliance development environment installed.[/bold green]")
    output.print(f"  Project: {project_id}")
    output.print(f"  Django:  {resolved_django_cwd.relative_to(repo)}")
    output.print("  Vite:    .")
    output.print(f"  Source:  {source}")
    if hooks_enabled:
        output.print("  Git hooks: managed worktree environment enabled")
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
