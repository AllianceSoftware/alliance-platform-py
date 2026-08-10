from __future__ import annotations

from copy import deepcopy
import os
from pathlib import Path
import re
import tomllib
from typing import Any

from . import invocation_name
from .errors import ConfigError
from .identity import slugify
from .models import ConfigPaths
from .models import DevConfig
from .models import ProcessConfig

CONFIG_KEYS = {
    "project_id",
    "django_port_base",
    "vite_port_base",
    "portless",
    "database_template",
    "database_template_strategy",
    "createdevdata_args",
    "db_prepare_command",
    "django_cwd",
    "vite_cwd",
    "manage_command",
    "test_command",
    "jstest_command",
    "lint_command",
    "check_command",
    "django_command",
    "vite_command",
    "startup_timeout",
    "environment",
    "extra_processes",
}

DEFAULTS: dict[str, Any] = {
    "django_port_base": 8000,
    "vite_port_base": 5173,
    "portless": "auto",
    "database_template": "",
    "database_template_strategy": "default",
    "createdevdata_args": [],
    "db_prepare_command": [],
    "django_cwd": "django-root",
    "vite_cwd": ".",
    "manage_command": ["uv", "run", "python", "manage.py"],
    "test_command": [],
    "jstest_command": [],
    "lint_command": [],
    "check_command": [],
    "django_command": ["uv", "run", "python", "manage.py", "runserver"],
    "vite_command": ["yarn", "dev"],
    "startup_timeout": 60.0,
    "environment": {},
    "extra_processes": [],
}

PROCESS_KEYS = {"name", "command", "cwd", "required"}
RESERVED_PROCESS_NAMES = {"django", "vite", "starting"}
PROJECT_ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
RESERVED_ENVIRONMENT_NAMES = {
    "DB_NAME",
    "DEV_INVOKE_PATH",
    "DEV_INVOKE_UV_RUN_RECURSION_DEPTH",
    "DEV_INVOKE_UV_RUN_RECURSION_DEPTH_SET",
    "DEV_INVOKE_VIRTUAL_ENV",
    "DEV_INVOKE_VIRTUAL_ENV_SET",
    "ALLIANCE_DEV_PROJECT_DIR",
    "ALLIANCE_DEV_INVOCATION_NAME",
    "PGDATABASE",
    "DEV_BASE_HOST",
    "DEV_PROJECT",
    "DEV_WORKTREE",
    "DEV_WORKTREE_ID",
    "DEV_DJANGO_PORT",
    "DEV_VITE_PORT",
}

CWD_KEYS = {"django_cwd", "vite_cwd"}
REQUIRED_COMMAND_KEYS = {
    "manage_command",
    "django_command",
    "vite_command",
}
OPTIONAL_COMMAND_KEYS = {
    "test_command",
    "jstest_command",
    "lint_command",
    "check_command",
}


def _read_toml(path: Path, *, required: bool = False) -> dict[str, Any]:
    if not path.exists():
        if required:
            raise ConfigError(f"Config file not found: {path}")
        return {}
    try:
        with path.open("rb") as file:
            value = tomllib.load(file)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"Invalid TOML in {path}: {error}") from error
    if not isinstance(value, dict):
        raise ConfigError(f"Config layer must be a TOML table: {path}")
    return value


def _project_name(repo: Path) -> str:
    pyproject = _read_toml(repo / "pyproject.toml", required=True)
    project = pyproject.get("project")
    name = project.get("name") if isinstance(project, dict) else None
    if not isinstance(name, str) or not name.strip():
        raise ConfigError("pyproject.toml must define a non-empty [project].name")
    return name.strip()


def _expect_exact(value: Any, expected: type[Any], label: str) -> None:
    if type(value) is not expected:
        raise ConfigError(f"{label} must be {expected.__name__}; got {type(value).__name__}")


def _validate_string_list(value: Any, label: str, *, allow_empty: bool = True) -> None:
    _expect_exact(value, list, label)
    if not allow_empty and not value:
        raise ConfigError(f"{label} must not be empty")
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise ConfigError(f"{label}[{index}] must be a string")
        if not allow_empty and not item:
            raise ConfigError(f"{label}[{index}] must not be empty")


def _validate_processes(value: Any, label: str, repo: Path) -> None:
    _expect_exact(value, list, label)
    seen: set[str] = set()
    for index, item in enumerate(value):
        item_label = f"{label}[{index}]"
        _expect_exact(item, dict, item_label)
        unknown = set(item) - PROCESS_KEYS
        if unknown:
            raise ConfigError(f"Unknown key(s) in {item_label}: {', '.join(sorted(unknown))}")
        name = item.get("name")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
            raise ConfigError(f"{item_label}.name must be a lowercase slug")
        if name in RESERVED_PROCESS_NAMES:
            raise ConfigError(f"{item_label}.name '{name}' is reserved")
        if name in seen:
            raise ConfigError(f"Duplicate process name '{name}' in {label}")
        seen.add(name)
        _validate_string_list(item.get("command"), f"{item_label}.command", allow_empty=False)
        cwd = item.get("cwd", ".")
        if not isinstance(cwd, str) or not cwd:
            raise ConfigError(f"{item_label}.cwd must be a non-empty string")
        cwd_path = (repo / cwd).resolve()
        if not cwd_path.is_relative_to(repo.resolve()):
            raise ConfigError(f"{item_label}.cwd must stay inside the repository")
        if "required" in item:
            _expect_exact(item["required"], bool, f"{item_label}.required")


def validate_layer(value: dict[str, Any], path: Path, repo: Path, *, allow_project_id: bool) -> None:
    unknown = set(value) - CONFIG_KEYS
    if unknown:
        raise ConfigError(f"Unknown config key(s) in {path}: {', '.join(sorted(unknown))}")
    if "project_id" in value:
        if not allow_project_id:
            raise ConfigError(f"project_id may only be set in the committed project config: {path}")
        project_id = value["project_id"]
        if not isinstance(project_id, str) or PROJECT_ID_PATTERN.fullmatch(project_id) is None:
            raise ConfigError(
                f"project_id in {path} must be a lowercase slug containing only letters, "
                "digits, and single hyphens"
            )
    for key in ("django_port_base", "vite_port_base"):
        if key in value:
            _expect_exact(value[key], int, f"{key} in {path}")
            if not 1 <= value[key] <= 65535:
                raise ConfigError(f"{key} in {path} must be between 1 and 65535")
    if "portless" in value:
        policy = value["portless"]
        if not isinstance(policy, str) or policy not in {"auto", "off", "required"}:
            raise ConfigError(f'portless in {path} must be "auto", "off", or "required"')
    if "database_template" in value:
        _expect_exact(value["database_template"], str, f"database_template in {path}")
    if "database_template_strategy" in value:
        strategy = value["database_template_strategy"]
        if not isinstance(strategy, str) or strategy not in {"default", "wal_log", "file_copy"}:
            raise ConfigError(
                f'database_template_strategy in {path} must be "default", "wal_log", or "file_copy"'
            )
    for key in ("createdevdata_args", "db_prepare_command"):
        if key in value:
            _validate_string_list(value[key], f"{key} in {path}")
    for key in REQUIRED_COMMAND_KEYS:
        if key in value:
            _validate_string_list(value[key], f"{key} in {path}", allow_empty=False)
    for key in OPTIONAL_COMMAND_KEYS:
        if key in value:
            _validate_string_list(value[key], f"{key} in {path}")
    for key in CWD_KEYS:
        if key in value:
            cwd = value[key]
            if not isinstance(cwd, str) or not cwd:
                raise ConfigError(f"{key} in {path} must be a non-empty string")
            cwd_path = (repo / cwd).resolve()
            if not cwd_path.is_relative_to(repo.resolve()):
                raise ConfigError(f"{key} in {path} must stay inside the repository")
    if "startup_timeout" in value:
        timeout = value["startup_timeout"]
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0:
            raise ConfigError(f"startup_timeout in {path} must be a positive number")
    if "environment" in value:
        environment = value["environment"]
        _expect_exact(environment, dict, f"environment in {path}")
        for key, item in environment.items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or not isinstance(item, str):
                raise ConfigError(f"environment in {path} must contain string environment variables")
            if key in RESERVED_ENVIRONMENT_NAMES:
                raise ConfigError(f"environment in {path} cannot set reserved variable {key}")
    if "extra_processes" in value:
        _validate_processes(value["extra_processes"], f"extra_processes in {path}", repo)


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if key == "environment" and isinstance(value, dict):
            result[key] = {**result.get(key, {}), **value}
        else:
            result[key] = deepcopy(value)
    return result


def _merge_with_provenance(
    effective: dict[str, Any],
    setting_sources: dict[str, str],
    environment_sources: dict[str, str],
    layer: dict[str, Any],
    source: str,
) -> dict[str, Any]:
    merged = _merge(effective, layer)
    for key, value in layer.items():
        if key == "environment" and isinstance(value, dict):
            environment_sources.update(dict.fromkeys(value, source))
        else:
            setting_sources[key] = source
    return merged


def ensure_private_file(path: Path) -> None:
    """Create a user-owned config file without relaxing existing permissions."""
    missing: list[Path] = []
    parent = path.parent
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
        if os.name == "posix":
            os.chmod(directory, 0o700)
    if path.exists():
        return
    try:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return
    try:
        if os.name == "posix":
            os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)


def load_config(
    repo: Path,
    environ: dict[str, str] | None = None,
) -> DevConfig:
    repo = repo.resolve()
    resolved_environ = dict(os.environ) if environ is None else environ
    project_path = repo / "config" / "dev.toml"
    project_layer = _read_toml(project_path, required=True)
    validate_layer(project_layer, project_path, repo, allow_project_id=True)

    project_name = _project_name(repo)
    project_id_value = project_layer.get("project_id")
    if project_id_value is None:
        suggested_project_id = slugify(project_name)
        if not suggested_project_id:
            raise ConfigError(f"Could not derive a project slug from {project_name!r}")
        raise ConfigError(
            f"{project_path} must define the project's operational identity. Add "
            f'project_id = "{suggested_project_id}" and commit it before using {invocation_name()}.'
        )
    project_id = str(project_id_value)

    if project_id == "template-django" and project_name != "template-django":
        existing_slug = slugify(project_name)
        raise ConfigError(
            f"{project_path} still uses the template project_id 'template-django', but "
            f"pyproject.toml identifies this project as {project_name!r}. Set project_id = "
            f'"{existing_slug}" and commit it before using {invocation_name()}.'
        )
    project_slug = project_id

    default_config_home = Path(resolved_environ.get("HOME", str(Path.home()))) / ".config"
    xdg_config = Path(resolved_environ.get("XDG_CONFIG_HOME", str(default_config_home)))
    global_path = xdg_config / "alliance" / "dev" / project_slug / "config.toml"
    worktree_path = repo / ".dev-server" / "config.toml"
    global_layer = _read_toml(global_path)
    worktree_layer = _read_toml(worktree_path)
    validate_layer(global_layer, global_path, repo, allow_project_id=False)
    validate_layer(worktree_layer, worktree_path, repo, allow_project_id=False)

    effective = deepcopy(DEFAULTS)
    setting_sources = {key: "default" for key in DEFAULTS if key != "environment"}
    environment_sources: dict[str, str] = {}
    effective = _merge_with_provenance(
        effective,
        setting_sources,
        environment_sources,
        project_layer,
        "project",
    )
    effective = _merge_with_provenance(
        effective,
        setting_sources,
        environment_sources,
        global_layer,
        "global",
    )
    effective = _merge_with_provenance(
        effective,
        setting_sources,
        environment_sources,
        worktree_layer,
        "worktree",
    )
    effective["project_id"] = project_id
    setting_sources["project_id"] = "project"
    validate_layer(effective, Path("effective config"), repo, allow_project_id=True)
    paths = ConfigPaths(
        project=project_path,
        global_=global_path,
        worktree=worktree_path,
    )
    processes = tuple(
        ProcessConfig(
            name=item["name"],
            command=tuple(item["command"]),
            cwd=item.get("cwd", "."),
            required=item.get("required", True),
        )
        for item in effective["extra_processes"]
    )
    database_template = effective["database_template"] or None
    return DevConfig(
        project_name=project_name,
        project_id=project_id,
        project_slug=project_slug,
        django_port_base=effective["django_port_base"],
        vite_port_base=effective["vite_port_base"],
        portless=effective["portless"],
        database_template=database_template,
        database_template_strategy=effective["database_template_strategy"],
        createdevdata_args=tuple(effective["createdevdata_args"]),
        db_prepare_command=tuple(effective["db_prepare_command"]),
        django_cwd=effective["django_cwd"],
        vite_cwd=effective["vite_cwd"],
        manage_command=tuple(effective["manage_command"]),
        test_command=tuple(effective["test_command"]),
        jstest_command=tuple(effective["jstest_command"]),
        lint_command=tuple(effective["lint_command"]),
        check_command=tuple(effective["check_command"]),
        django_command=tuple(effective["django_command"]),
        vite_command=tuple(effective["vite_command"]),
        startup_timeout=float(effective["startup_timeout"]),
        environment=dict(effective["environment"]),
        extra_processes=processes,
        paths=paths,
        effective=effective,
        setting_sources=setting_sources,
        environment_sources=environment_sources,
    )
