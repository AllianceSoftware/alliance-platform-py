from __future__ import annotations

from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime
from datetime import timezone
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Any
from uuid import uuid4

from . import DEV_PROTOCOL_VERSION
from . import package_version
from .errors import DevError
from .models import DevConfig
from .models import WorktreeIdentity

REGISTRY_SCHEMA_VERSION = 1


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def registry_root(environ: dict[str, str] | None = None) -> Path:
    environment = os.environ if environ is None else environ
    home = Path(environment.get("HOME", str(Path.home())))
    state_home = Path(environment.get("XDG_STATE_HOME", str(home / ".local" / "state")))
    return state_home / "alliance" / "dev" / "registry" / f"v{REGISTRY_SCHEMA_VERSION}"


def _git_output(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _git_common_dir(repo: Path) -> str:
    value = _git_output(repo, "rev-parse", "--git-common-dir")
    if not value:
        return ""
    path = Path(value)
    if not path.is_absolute():
        path = repo / path
    return str(path.resolve())


@dataclass(frozen=True)
class RegistryEntry:
    project_id: str
    worktree_id: str
    worktree_path: str
    branch: str | None
    git_common_dir: str
    remote_url: str
    database_name: str
    database_present: bool | None
    database_owned: bool
    database_ownership_token: str | None
    database_setup_pending: bool
    database_created_at: str | None
    session_name: str
    django_port: int
    vite_port: int
    owner_kind: str
    owner_id: str | None
    lease_expires_at: str | None
    registered_at: str
    last_seen_at: str
    last_started_at: str | None
    last_stopped_at: str | None
    last_action: str
    tool_version: str
    protocol_version: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": REGISTRY_SCHEMA_VERSION,
            "environmentId": self.worktree_id,
            "project": {
                "id": self.project_id,
                "gitCommonDir": self.git_common_dir,
                "remoteUrl": self.remote_url,
            },
            "worktree": {
                "id": self.worktree_id,
                "path": self.worktree_path,
                "branch": self.branch,
            },
            "resources": {
                "database": {
                    "name": self.database_name,
                    "present": self.database_present,
                    "owned": self.database_owned,
                    "ownershipToken": self.database_ownership_token,
                    "setupPending": self.database_setup_pending,
                    "createdAt": self.database_created_at,
                },
                "tmux": {"sessionName": self.session_name},
                "ports": {"django": self.django_port, "vite": self.vite_port},
            },
            "owner": {"kind": self.owner_kind, "id": self.owner_id},
            "lease": {"expiresAt": self.lease_expires_at} if self.lease_expires_at else None,
            "activity": {
                "registeredAt": self.registered_at,
                "lastSeenAt": self.last_seen_at,
                "lastStartedAt": self.last_started_at,
                "lastStoppedAt": self.last_stopped_at,
                "lastAction": self.last_action,
            },
            "tool": {
                "version": self.tool_version,
                "protocolVersion": self.protocol_version,
            },
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> RegistryEntry:
        try:
            if value["schemaVersion"] != REGISTRY_SCHEMA_VERSION:
                raise ValueError(f"unsupported schema version {value['schemaVersion']!r}")
            project = value["project"]
            worktree = value["worktree"]
            resources = value["resources"]
            database = resources["database"]
            ports = resources["ports"]
            owner = value["owner"]
            lease = value.get("lease")
            activity = value["activity"]
            tool = value["tool"]
            entry = cls(
                project_id=project["id"],
                worktree_id=worktree["id"],
                worktree_path=worktree["path"],
                branch=worktree["branch"],
                git_common_dir=project["gitCommonDir"],
                remote_url=project["remoteUrl"],
                database_name=database["name"],
                database_present=database["present"],
                database_owned=database["owned"],
                database_ownership_token=database["ownershipToken"],
                database_setup_pending=database["setupPending"],
                database_created_at=database["createdAt"],
                session_name=resources["tmux"]["sessionName"],
                django_port=ports["django"],
                vite_port=ports["vite"],
                owner_kind=owner["kind"],
                owner_id=owner["id"],
                lease_expires_at=lease["expiresAt"] if lease else None,
                registered_at=activity["registeredAt"],
                last_seen_at=activity["lastSeenAt"],
                last_started_at=activity["lastStartedAt"],
                last_stopped_at=activity["lastStoppedAt"],
                last_action=activity["lastAction"],
                tool_version=tool["version"],
                protocol_version=tool["protocolVersion"],
            )
        except (KeyError, TypeError) as error:
            raise ValueError(f"invalid registry entry: {error}") from error
        if value.get("environmentId") != entry.worktree_id:
            raise ValueError("environmentId does not match worktree.id")
        if not entry.project_id or not entry.worktree_id or not entry.worktree_path:
            raise ValueError("project and worktree identity must not be empty")
        if not entry.database_name or not entry.session_name:
            raise ValueError("resource identity must not be empty")
        if entry.database_owned and not entry.database_ownership_token:
            raise ValueError("owned database must have an ownership token")
        return entry


class RegistryStore:
    def __init__(
        self,
        repo: Path,
        config: DevConfig,
        identity: WorktreeIdentity,
        *,
        environ: dict[str, str] | None = None,
        root: Path | None = None,
    ) -> None:
        self.repo = repo.resolve()
        self.config = config
        self.identity = identity
        self.environment = dict(os.environ if environ is None else environ)
        self.root = root or registry_root(environ)
        self.project_directory = self.root / config.project_id
        self.path = self.project_directory / f"{identity.worktree_id}.json"

    def _new_entry(self, now: str) -> RegistryEntry:
        environment = self.environment
        return RegistryEntry(
            project_id=self.config.project_id,
            worktree_id=self.identity.worktree_id,
            worktree_path=str(self.repo),
            branch=self.identity.branch,
            git_common_dir=_git_common_dir(self.repo),
            remote_url=_git_output(self.repo, "remote", "get-url", "origin"),
            database_name=self.identity.database_name,
            database_present=None,
            database_owned=False,
            database_ownership_token=None,
            database_setup_pending=False,
            database_created_at=None,
            session_name=self.identity.session_name,
            django_port=0,
            vite_port=0,
            owner_kind=environment.get("ALLIANCE_DEV_OWNER_KIND", "human"),
            owner_id=environment.get("ALLIANCE_DEV_OWNER_ID") or None,
            lease_expires_at=environment.get("ALLIANCE_DEV_LEASE_EXPIRES_AT") or None,
            registered_at=now,
            last_seen_at=now,
            last_started_at=None,
            last_stopped_at=None,
            last_action="registered",
            tool_version=package_version(),
            protocol_version=DEV_PROTOCOL_VERSION,
        )

    def load(self) -> RegistryEntry | None:
        if not self.path.exists():
            return None
        try:
            value = json.loads(self.path.read_text())
            if not isinstance(value, dict):
                raise ValueError("entry must be a JSON object")
            entry = RegistryEntry.from_dict(value)
        except (OSError, ValueError) as error:
            raise DevError(f"Invalid dev registry entry {self.path}: {error}") from error
        if entry.project_id != self.config.project_id or entry.worktree_id != self.identity.worktree_id:
            raise DevError(f"Registry entry identity does not match this worktree: {self.path}")
        return entry

    def _entry_path(self, worktree_id: str) -> Path:
        if re.fullmatch(r"[a-z0-9][a-z0-9-]*", worktree_id) is None:
            raise DevError(f"Invalid registry environment ID: {worktree_id!r}")
        return self.project_directory / f"{worktree_id}.json"

    def load_project_entry(self, worktree_id: str) -> RegistryEntry | None:
        entry = next(
            (entry for entry in self.list_project() if entry.worktree_id == worktree_id),
            None,
        )
        return entry

    def list_project(self) -> tuple[RegistryEntry, ...]:
        if not self.project_directory.exists():
            return ()
        entries: list[RegistryEntry] = []
        for path in sorted(self.project_directory.glob("*.json")):
            try:
                value = json.loads(path.read_text())
                if not isinstance(value, dict):
                    raise ValueError("entry must be a JSON object")
                entry = RegistryEntry.from_dict(value)
            except (OSError, ValueError) as error:
                raise DevError(f"Invalid dev registry entry {path}: {error}") from error
            if entry.project_id != self.config.project_id:
                raise DevError(f"Registry entry belongs to another project: {path}")
            if path.stem != entry.worktree_id:
                raise DevError(f"Registry entry filename does not match its environment ID: {path}")
            entries.append(entry)
        return tuple(entries)

    def save(self, entry: RegistryEntry) -> None:
        if entry.project_id != self.config.project_id or entry.worktree_id != self.identity.worktree_id:
            raise DevError("Refusing to write a registry entry for another worktree")
        self.save_project_entry(entry)

    def save_project_entry(self, entry: RegistryEntry) -> None:
        if entry.project_id != self.config.project_id:
            raise DevError("Refusing to write a registry entry for another project")
        try:
            RegistryEntry.from_dict(entry.as_dict())
        except ValueError as error:
            raise DevError(f"Refusing to write invalid registry entry: {error}") from error
        path = self._entry_path(entry.worktree_id)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.parent.chmod(0o700)
        temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as file:
                json.dump(entry.as_dict(), file, indent=2, sort_keys=True)
                file.write("\n")
            temporary.replace(path)
            path.chmod(0o600)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise DevError(f"Could not write dev registry entry {path}: {error}") from error

    def update(self, **changes: Any) -> RegistryEntry:
        now = _timestamp()
        current = self.load() or self._new_entry(now)
        changes.update(
            worktree_path=str(self.repo),
            branch=self.identity.branch,
            last_seen_at=now,
            tool_version=package_version(),
            protocol_version=DEV_PROTOCOL_VERSION,
        )
        entry = replace(current, **changes)
        self.save(entry)
        return entry

    def register(self) -> RegistryEntry:
        return self.update(last_action="registered")

    def database_setup_started(self) -> RegistryEntry:
        current = self.load()
        token = (
            current.database_ownership_token
            if current is not None and current.database_owned
            else uuid4().hex
        )
        return self.update(
            database_present=None,
            database_owned=True,
            database_ownership_token=token,
            database_setup_pending=True,
            last_action="databaseSetupStarted",
        )

    def database_ready(self, *, created: bool) -> RegistryEntry:
        current = self.load()
        now = _timestamp()
        return self.update(
            database_present=True,
            database_owned=current.database_owned if current is not None else created,
            database_ownership_token=(
                current.database_ownership_token if current is not None else uuid4().hex if created else None
            ),
            database_setup_pending=False,
            database_created_at=(
                current.database_created_at
                if current is not None and current.database_created_at
                else now
                if created
                else None
            ),
            last_action="databaseReady",
        )

    def started(self, *, django_port: int, vite_port: int) -> RegistryEntry:
        now = _timestamp()
        return self.update(
            django_port=django_port,
            vite_port=vite_port,
            last_started_at=now,
            last_action="running",
        )

    def stopped(self, *, database_present: bool | None) -> RegistryEntry:
        now = _timestamp()
        return self.update(
            database_present=database_present,
            database_setup_pending=False,
            last_stopped_at=now,
            last_action="stopped",
        )

    def cleanup_started(self, entry: RegistryEntry, *, session_stopped: bool) -> RegistryEntry:
        now = _timestamp()
        updated = replace(
            entry,
            last_seen_at=now,
            last_stopped_at=now if session_stopped else entry.last_stopped_at,
            last_action="cleanupPending",
            tool_version=package_version(),
            protocol_version=DEV_PROTOCOL_VERSION,
        )
        self.save_project_entry(updated)
        return updated

    def database_removed(self, entry: RegistryEntry | None = None) -> RegistryEntry:
        current = entry or self.load()
        if current is None:
            raise DevError("Cannot record database removal without a registry entry")
        now = _timestamp()
        updated = replace(
            current,
            database_present=False,
            database_setup_pending=False,
            last_seen_at=now,
            last_action="databaseRemoved",
            tool_version=package_version(),
            protocol_version=DEV_PROTOCOL_VERSION,
        )
        self.save_project_entry(updated)
        return updated

    def remove(self) -> None:
        self.remove_project_entry(self.identity.worktree_id)

    def remove_project_entry(self, worktree_id: str) -> None:
        path = self._entry_path(worktree_id)
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            raise DevError(f"Could not remove dev registry entry {path}: {error}") from error
