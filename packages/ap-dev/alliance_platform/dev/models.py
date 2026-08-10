from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import DEV_PROTOCOL_VERSION
from . import STATE_SCHEMA_VERSION


@dataclass(frozen=True)
class ProcessConfig:
    name: str
    command: tuple[str, ...]
    cwd: str = "."
    required: bool = True


@dataclass(frozen=True)
class ProcessSpec:
    name: str
    argv: tuple[str, ...]
    cwd: Path
    required: bool = True


@dataclass(frozen=True)
class ProcessStatus:
    name: str
    alive: bool
    exit_code: int | None
    signal: str | None = None


@dataclass(frozen=True)
class ManagedSession:
    name: str
    project_slug: str
    worktree_path: str
    worktree_id: str
    django_port: int
    vite_port: int


@dataclass(frozen=True)
class EnvironmentSummary:
    branch: str | None
    worktree_id: str
    session_name: str
    database_name: str
    django_url: str
    vite_url: str
    use_portless: bool


@dataclass(frozen=True)
class StartResult:
    environment: EnvironmentSummary
    already_running: bool
    frontend_dependencies_installed: bool
    frontend_symlink_removed: bool
    database_created: bool
    recovered_incomplete_database: bool
    portless_reason: str | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class StopResult:
    was_running: bool
    database_drop_requested: bool
    database_dropped: bool
    recovered_incomplete_database: bool
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class RestartResult:
    environment: EnvironmentSummary
    portless_reason: str | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProcessRestartResult:
    name: str
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class StatusProcessRecord:
    name: str
    required: bool | None
    state: str
    exit_code: int | None
    signal: str | None


@dataclass(frozen=True)
class StatusRecord:
    project_id: str
    worktree: str
    worktree_id: str
    branch: str | None
    session_name: str
    session_state: str
    readiness: str
    django_url: str | None
    vite_url: str | None
    database_name: str
    processes: tuple[StatusProcessRecord, ...]


@dataclass(frozen=True)
class EnvironmentRecord:
    project_id: str
    environment_id: str
    state: str
    worktree_path: str
    worktree_branch: str | None
    worktree_exists: bool
    session_name: str
    session_state: str
    database_name: str
    database_present: bool | None
    database_owned: bool
    database_setup_pending: bool
    owner_kind: str
    owner_id: str | None
    lease_expires_at: str | None
    registered_at: str
    last_seen_at: str
    last_started_at: str | None
    last_stopped_at: str | None


@dataclass(frozen=True)
class EnvironmentRemovalResult:
    environment_id: str
    session_stopped: bool
    database_dropped: bool
    database_was_absent: bool
    database_retained: bool


@dataclass(frozen=True)
class LogRecord:
    name: str
    output: str
    lines: int


@dataclass(frozen=True)
class ToolRecord:
    name: str
    path: str | None


@dataclass(frozen=True)
class PortlessDiagnostics:
    policy: str
    cli: str | None
    proxy_availability_capability: str
    selected: bool
    reason: str


@dataclass(frozen=True)
class DoctorStateRecord:
    path: Path
    status: str
    database_setup_pending: bool | None


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class DoctorReport:
    package_version: str
    protocol_version: int
    project_id: str
    branch: str | None
    worktree_id: str
    worktree_path: str
    session_name: str
    database_name: str
    config_paths: ConfigPaths
    state: DoctorStateRecord
    checks: tuple[DoctorCheck, ...]


@dataclass(frozen=True)
class ConfigPaths:
    project: Path
    global_: Path
    worktree: Path


@dataclass(frozen=True)
class DevConfig:
    project_name: str
    project_id: str
    project_slug: str
    django_port_base: int
    vite_port_base: int
    portless: str
    database_template: str | None
    database_template_strategy: str
    createdevdata_args: tuple[str, ...]
    db_prepare_command: tuple[str, ...]
    django_cwd: str
    vite_cwd: str
    verification_virtualenv: str
    manage_command: tuple[str, ...]
    test_command: tuple[str, ...]
    jstest_command: tuple[str, ...]
    lint_command: tuple[str, ...]
    check_command: tuple[str, ...]
    django_command: tuple[str, ...]
    vite_command: tuple[str, ...]
    startup_timeout: float
    environment: dict[str, str]
    extra_processes: tuple[ProcessConfig, ...]
    paths: ConfigPaths
    effective: dict[str, Any]
    setting_sources: dict[str, str]
    environment_sources: dict[str, str]


@dataclass(frozen=True)
class WorktreeIdentity:
    repo: Path
    branch: str | None
    worktree_id: str
    session_name: str
    database_name: str
    portless_app_name: str


@dataclass
class PersistedState:
    django_port: int
    vite_port: int
    use_portless: bool
    database_setup_pending: bool = False
    version: int = STATE_SCHEMA_VERSION
    protocol_version: int = DEV_PROTOCOL_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "protocolVersion": self.protocol_version,
            "djangoPort": self.django_port,
            "vitePort": self.vite_port,
            "usePortless": self.use_portless,
            "databaseSetupPending": self.database_setup_pending,
        }

    @classmethod
    def from_dict(cls, value: Any) -> PersistedState:
        if type(value) is not dict:
            raise ValueError("state must be a JSON object")
        version = value.get("version")
        if type(version) is not int:
            raise ValueError("version must be an integer")
        if version != STATE_SCHEMA_VERSION:
            raise ValueError(f"unsupported schema version {version}; expected version {STATE_SCHEMA_VERSION}")
        expected = {
            "version",
            "protocolVersion",
            "djangoPort",
            "vitePort",
            "usePortless",
            "databaseSetupPending",
        }
        missing = expected - set(value)
        unknown = set(value) - expected
        if missing:
            raise ValueError(f"missing field(s): {', '.join(sorted(missing))}")
        if unknown:
            raise ValueError(f"unknown field(s): {', '.join(sorted(unknown))}")
        protocol_version = value["protocolVersion"]
        if type(protocol_version) is not int:
            raise ValueError("protocolVersion must be an integer")
        if protocol_version != DEV_PROTOCOL_VERSION:
            raise ValueError(
                f"unsupported protocol version {protocol_version}; expected version {DEV_PROTOCOL_VERSION}"
            )
        for key in ("djangoPort", "vitePort"):
            port = value[key]
            if type(port) is not int:
                raise ValueError(f"{key} must be an integer")
            if not 0 <= port <= 65535:
                raise ValueError(f"{key} must be between 0 and 65535")
        for key in ("usePortless", "databaseSetupPending"):
            if type(value[key]) is not bool:
                raise ValueError(f"{key} must be a boolean")
        if value["usePortless"] and value["djangoPort"] != 0:
            raise ValueError("djangoPort must be 0 when usePortless is true")
        if not value["databaseSetupPending"]:
            if value["vitePort"] == 0:
                raise ValueError("vitePort may be 0 only while databaseSetupPending is true")
            if not value["usePortless"] and value["djangoPort"] == 0:
                raise ValueError("djangoPort may be 0 only while databaseSetupPending or usePortless is true")
        return cls(
            version=version,
            protocol_version=protocol_version,
            django_port=value["djangoPort"],
            vite_port=value["vitePort"],
            use_portless=value["usePortless"],
            database_setup_pending=value["databaseSetupPending"],
        )

    def validate(self) -> None:
        self.from_dict(self.as_dict())


@dataclass
class RuntimeView:
    persisted: PersistedState
    worktree_id: str
    worktree_path: str
    branch: str | None
    session_name: str
    database_name: str
    django_url: str
    vite_url: str
    dev_base_host: str

    @property
    def django_port(self) -> int:
        return self.persisted.django_port

    @property
    def vite_port(self) -> int:
        return self.persisted.vite_port

    @property
    def use_portless(self) -> bool:
        return self.persisted.use_portless

    @property
    def database_setup_pending(self) -> bool:
        return self.persisted.database_setup_pending

    @database_setup_pending.setter
    def database_setup_pending(self, value: bool) -> None:
        self.persisted.database_setup_pending = value
