from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess

from dotenv import dotenv_values

from .errors import DevError
from .models import DevConfig
from .models import WorktreeIdentity

PANE_EXCLUDED_ENVIRONMENT = {"TERM", "TMUX", "TMUX_PANE", "TMUX_TMPDIR"}
DATABASE_ENVIRONMENT_MAPPINGS = {
    "DB_HOST": "PGHOST",
    "DB_PORT": "PGPORT",
    "DB_USER": "PGUSER",
    "DB_PASSWORD": "PGPASSWORD",
}
LAUNCHER_ENVIRONMENT_MARKERS = {
    "DEV_INVOKE_PATH",
    "DEV_INVOKE_VIRTUAL_ENV",
    "DEV_INVOKE_VIRTUAL_ENV_SET",
    "DEV_INVOKE_UV_RUN_RECURSION_DEPTH",
    "DEV_INVOKE_UV_RUN_RECURSION_DEPTH_SET",
    "ALLIANCE_DEV_PROJECT_DIR",
    "ALLIANCE_DEV_INVOCATION_NAME",
    "ALLIANCE_DEV_UV_CACHE_DIR",
}


@dataclass(frozen=True)
class VerificationVirtualenv:
    path: Path
    source: str
    activate: bool


def _restore_invoking_environment(environment: dict[str, str]) -> dict[str, str]:
    result = dict(environment)
    invoked_path = result.get("DEV_INVOKE_PATH")
    virtual_environment = result.get("DEV_INVOKE_VIRTUAL_ENV", "")
    virtual_environment_was_set = result.get("DEV_INVOKE_VIRTUAL_ENV_SET") == "1"
    recursion_depth = result.get("DEV_INVOKE_UV_RUN_RECURSION_DEPTH", "")
    recursion_depth_was_set = result.get("DEV_INVOKE_UV_RUN_RECURSION_DEPTH_SET") == "1"
    for marker in LAUNCHER_ENVIRONMENT_MARKERS:
        result.pop(marker, None)
    if invoked_path is None:
        return result

    result["PATH"] = invoked_path
    if virtual_environment_was_set:
        result["VIRTUAL_ENV"] = virtual_environment
    else:
        result.pop("VIRTUAL_ENV", None)
    if recursion_depth_was_set:
        result["UV_RUN_RECURSION_DEPTH"] = recursion_depth
    else:
        result.pop("UV_RUN_RECURSION_DEPTH", None)
    return result


def build_process_environment(
    config: DevConfig,
    inherited: dict[str, str] | None = None,
) -> dict[str, str]:
    original = _restore_invoking_environment(dict(os.environ if inherited is None else inherited))
    result = dict(config.environment)
    result.update(original)
    for marker in LAUNCHER_ENVIRONMENT_MARKERS:
        result.pop(marker, None)
    return result


def build_control_environment(
    repo: Path,
    config: DevConfig,
    inherited: dict[str, str] | None = None,
) -> dict[str, str]:
    path = repo / ".env"
    try:
        parsed = dotenv_values(path, interpolate=False) if path.exists() else {}
    except (OSError, UnicodeError) as error:
        raise DevError(f"Could not read application env file {path}: {error}") from error
    result = {key: value if value is not None else "" for key, value in parsed.items()}
    result.update(config.environment)
    original = _restore_invoking_environment(dict(os.environ if inherited is None else inherited))
    result.update(original)
    for marker in LAUNCHER_ENVIRONMENT_MARKERS:
        result.pop(marker, None)
    for source, target in DATABASE_ENVIRONMENT_MAPPINGS.items():
        if source in result and target not in result:
            result[target] = result[source]
    return result


def pane_environment(environment: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in environment.items() if key not in PANE_EXCLUDED_ENVIRONMENT}


def build_managed_environment(
    repo: Path,
    project_slug: str,
    identity: WorktreeIdentity,
    environment: dict[str, str],
    *,
    dev_base_host: str = "",
    django_port: int | None = None,
    vite_port: int | None = None,
    for_pane: bool = False,
) -> dict[str, str]:
    """Add generated worktree identity without importing the control environment."""
    result = pane_environment(environment) if for_pane else dict(environment)
    python_path = result.get("PYTHONPATH")
    result.update(
        {
            "DB_NAME": identity.database_name,
            "PGDATABASE": identity.database_name,
            "DEV_BASE_HOST": dev_base_host,
            "DEV_PROJECT": project_slug,
            "DEV_WORKTREE": str(repo),
            "DEV_WORKTREE_ID": identity.worktree_id,
            "PYTHONPATH": f"{repo}{os.pathsep}{python_path}" if python_path else str(repo),
        }
    )
    for key, value in (
        ("DEV_DJANGO_PORT", django_port),
        ("DEV_VITE_PORT", vite_port),
    ):
        if value is None:
            result.pop(key, None)
        else:
            result[key] = str(value)
    return result


def resolve_verification_virtualenv(
    repo: Path,
    configured: str,
    environment: dict[str, str],
) -> VerificationVirtualenv | None:
    active = environment.get("VIRTUAL_ENV")
    if active:
        path = Path(active).expanduser()
        if not path.is_absolute():
            path = repo / path
        resolution = VerificationVirtualenv(path.resolve(), "active caller virtualenv", False)
    elif configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = repo / path
        resolution = VerificationVirtualenv(path.resolve(), "configured project virtualenv", True)
    else:
        return None

    python = resolution.path / "bin" / "python"
    if not resolution.path.is_dir() or not python.is_file() or not os.access(python, os.X_OK):
        setting = (
            "Activate a provisioned environment before invoking bin/dev."
            if not resolution.activate
            else "Provision it with 'uv sync', activate another environment, or set "
            'verification_virtualenv = "" to disable automatic activation.'
        )
        raise DevError(
            f"The {resolution.source} is not provisioned at {resolution.path}; "
            f"expected executable {python}. {setting}"
        )
    return resolution


def build_verification_environment(
    repo: Path,
    configured: str,
    environment: dict[str, str],
) -> dict[str, str]:
    result = dict(environment)
    resolution = resolve_verification_virtualenv(repo, configured, result)
    if resolution is None or not resolution.activate:
        return result
    result["VIRTUAL_ENV"] = str(resolution.path)
    result["PATH"] = f"{resolution.path / 'bin'}{os.pathsep}{result.get('PATH', '')}"
    result.pop("PYTHONHOME", None)
    return result


def _required_node_major(repo: Path) -> str | None:
    nvmrc = repo / ".nvmrc"
    if not nvmrc.exists():
        return None
    value = nvmrc.read_text().strip().lstrip("v")
    match = re.match(r"([0-9]+)", value)
    return match.group(1) if match else None


def _node_major(environment: dict[str, str]) -> str | None:
    try:
        result = subprocess.run(
            ["node", "--version"],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )
    except FileNotFoundError:
        return None
    match = re.match(r"v([0-9]+)", result.stdout.strip())
    return match.group(1) if result.returncode == 0 and match else None


def prepare_node_environment(repo: Path, environment: dict[str, str]) -> dict[str, str]:
    required = _required_node_major(repo)
    if not required or _node_major(environment) == required:
        return environment

    candidates = [
        Path(environment.get("NVM_DIR", str(Path.home() / ".nvm"))) / "nvm.sh",
        Path("/usr/local/opt/nvm/nvm.sh"),
        Path("/opt/homebrew/opt/nvm/nvm.sh"),
    ]
    nvm_script = next((path for path in candidates if path.is_file()), None)
    if nvm_script is None:
        raise DevError(f"Node {required} is required, but it is not active and nvm could not be found")
    script = f'. "{nvm_script}" >/dev/null && nvm which {required}'
    result = subprocess.run(
        ["/bin/bash", "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )
    node = Path(result.stdout.strip())
    if result.returncode != 0 or not node.is_file():
        raise DevError(f"Node {required} is required; install it with: nvm install {required}")
    adjusted = dict(environment)
    adjusted["PATH"] = f"{node.parent}:{adjusted.get('PATH', '')}"
    return adjusted
