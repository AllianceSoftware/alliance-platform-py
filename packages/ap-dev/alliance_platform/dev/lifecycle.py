from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import errno
import http.client
import json
from json import JSONDecodeError
import os
from pathlib import Path
import signal
import socket
import ssl
import time
from typing import Callable
from typing import Iterable
from typing import Iterator
from urllib.parse import urlparse

from . import DEV_PROTOCOL_VERSION
from . import invocation_name
from . import package_version
from .database import DatabaseManager
from .database import DatabasePreparationResult
from .environment import build_managed_environment
from .errors import DevError
from .identity import current_branch
from .identity import database_name
from .models import DevConfig
from .models import DoctorCheck
from .models import DoctorReport
from .models import DoctorStateRecord
from .models import EnvironmentRecord
from .models import EnvironmentRemovalResult
from .models import EnvironmentSummary
from .models import LogRecord
from .models import ManagedSession
from .models import PersistedState
from .models import ProcessRestartResult
from .models import ProcessSpec
from .models import RestartResult
from .models import RuntimeView
from .models import StartResult
from .models import StatusProcessRecord
from .models import StatusRecord
from .models import StopResult
from .models import ToolRecord
from .models import WorktreeIdentity
from .portless import PortlessAdapter
from .portless import PortlessSelection
from .registry import RegistryStore
from .runner import Runner
from .runner import require_success
from .state import StateStore
from .state import allocation_lock
from .state import worktree_lock
from .tmux import TmuxClient


@contextmanager
def interrupt_on_termination() -> Iterator[None]:
    """Turn terminal/job termination into the same cleanup path as Ctrl-C."""
    signals = (signal.SIGHUP, signal.SIGTERM)
    previous = {signum: signal.getsignal(signum) for signum in signals}
    interrupted = False

    def interrupt(_signum: int, _frame: object) -> None:
        nonlocal interrupted
        if interrupted:
            return
        interrupted = True
        raise KeyboardInterrupt

    for signum in signals:
        signal.signal(signum, interrupt)
    try:
        yield
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def port_available(port: int) -> bool:
    addresses = ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1"))
    ipv6_unavailable = {errno.EAFNOSUPPORT, errno.EADDRNOTAVAIL, errno.EPROTONOSUPPORT}
    for family, address in addresses:
        try:
            with socket.socket(family, socket.SOCK_STREAM) as sock:
                sock.bind((address, port))
        except OSError as error:
            if family == socket.AF_INET6 and error.errno in ipv6_unavailable:
                continue
            return False
    return True


def find_free_port(start: int, reserved: set[int]) -> int:
    for port in range(start, 65536):
        if port not in reserved and port_available(port):
            return port
    raise DevError(f"Could not find a free port starting from {start}")


def tcp_ready(port: int) -> bool:
    try:
        # Vite's default localhost binding may resolve to either 127.0.0.1 or
        # ::1. create_connection tries every address returned for localhost.
        with socket.create_connection(("localhost", port), timeout=0.25):
            return True
    except (OSError, http.client.HTTPException):
        return False


def vite_ready(port: int, expected_project_dir: Path) -> bool:
    """Return whether the allocated port belongs to this worktree's Vite server."""
    connection = http.client.HTTPConnection("localhost", port, timeout=0.5)
    try:
        connection.request("GET", "/check")
        response = connection.getresponse()
        if response.status != 200:
            return False
        payload = json.loads(response.read().decode())
        if not isinstance(payload, dict) or payload.get("check") != "ok":
            return False
        project_dir = payload.get("projectDir")
        return isinstance(project_dir, str) and Path(project_dir).resolve() == expected_project_dir.resolve()
    except (OSError, http.client.HTTPException, JSONDecodeError, UnicodeDecodeError):
        return False
    finally:
        connection.close()


def url_ready(url: str) -> bool:
    parsed = urlparse(url)
    if not parsed.hostname:
        return False
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if parsed.scheme == "https":
        connection: http.client.HTTPConnection = http.client.HTTPSConnection(
            parsed.hostname,
            port,
            timeout=0.5,
            context=ssl._create_unverified_context(),  # noqa: S323 - local dev proxy probe
        )
    else:
        connection = http.client.HTTPConnection(parsed.hostname, port, timeout=0.5)
    try:
        connection.request("GET", parsed.path or "/")
        response = connection.getresponse()
        response.read(1)
        return response.status < 500
    except OSError:
        return False
    finally:
        connection.close()


@dataclass(frozen=True)
class _FrontendPreparation:
    installed: bool
    removed_symlink: bool


class DevEnvironment:
    def __init__(
        self,
        runner: Runner,
        repo: Path,
        config: DevConfig,
        identity: WorktreeIdentity,
        process_environment: dict[str, str],
        control_environment: dict[str, str],
        registry: RegistryStore | None = None,
    ):
        self.runner = runner
        self.repo = repo
        self.config = config
        self.identity = identity
        self.environment = process_environment
        self.store = StateStore(repo)
        self.registry = registry or RegistryStore(
            repo,
            config,
            identity,
            environ={**process_environment, **control_environment},
        )
        self.tmux = TmuxClient(runner, repo, process_environment)
        self.portless = PortlessAdapter(
            runner,
            repo,
            process_environment,
            identity.portless_app_name,
        )
        self.database = DatabaseManager(
            runner,
            repo,
            config,
            identity,
            process_environment,
            control_environment,
        )

    @property
    def expected_processes(self) -> tuple[str, ...]:
        return ("django", "vite", *(process.name for process in self.config.extra_processes))

    @property
    def required_processes(self) -> tuple[str, ...]:
        return (
            "django",
            "vite",
            *(process.name for process in self.config.extra_processes if process.required),
        )

    def _worktree_sessions(self) -> list[str]:
        return [
            session.name
            for session in self.tmux.list_managed_sessions()
            if session.name == self.identity.session_name
            or (
                session.project_slug == self.config.project_slug
                and (
                    session.worktree_id == self.identity.worktree_id
                    or session.worktree_path == str(self.repo)
                )
            )
        ]

    def _require_no_other_worktree_sessions(
        self,
        operation: str,
        *,
        current_session: str | None = None,
    ) -> None:
        active = [session for session in self._worktree_sessions() if session != current_session]
        if active:
            sessions = ", ".join(sorted(active))
            raise DevError(
                f"Cannot {operation} while another dev session is active for this worktree: "
                f"{sessions}. Stop it first."
            )

    def _runtime_view(self, state: PersistedState) -> RuntimeView:
        django_url = ""
        if state.use_portless:
            django_url = self.portless.resolve_url()
        elif state.django_port:
            django_url = f"http://localhost:{state.django_port}"
        vite_url = f"http://localhost:{state.vite_port}" if state.vite_port else ""
        parsed = urlparse(django_url)
        return RuntimeView(
            persisted=state,
            worktree_id=self.identity.worktree_id,
            worktree_path=str(self.identity.repo),
            branch=self.identity.branch,
            session_name=self.identity.session_name,
            database_name=self.identity.database_name,
            django_url=django_url,
            vite_url=vite_url,
            dev_base_host=(parsed.hostname or "") if state.use_portless else "",
        )

    def _save_state(self, state: RuntimeView) -> None:
        self.store.save(state.persisted)

    def _environment_summary(self, state: RuntimeView) -> EnvironmentSummary:
        return EnvironmentSummary(
            branch=state.branch,
            worktree_id=state.worktree_id,
            session_name=state.session_name,
            database_name=state.database_name,
            django_url=state.django_url,
            vite_url=state.vite_url,
            use_portless=state.use_portless,
        )

    def _allocate_state(self, use_portless: bool) -> RuntimeView:
        existing = self.store.load()
        reserved = {
            port
            for session in self.tmux.list_managed_sessions()
            for port in (session.django_port, session.vite_port)
            if port > 0
        }
        django_port = 0
        if not use_portless:
            candidate = existing.django_port if existing else 0
            if not candidate or candidate in reserved or not port_available(candidate):
                candidate = find_free_port(self.config.django_port_base, reserved)
            django_port = candidate
            reserved.add(django_port)
        vite_port = existing.vite_port if existing else 0
        if not vite_port or vite_port in reserved or not port_available(vite_port):
            vite_port = find_free_port(self.config.vite_port_base, reserved)
        return self._runtime_view(
            PersistedState(
                django_port=django_port,
                vite_port=vite_port,
                use_portless=use_portless,
            )
        )

    def _metadata(self, state: RuntimeView) -> dict[str, str]:
        return {
            "DEV_PROJECT": self.config.project_slug,
            "DEV_WORKTREE_ID": self.identity.worktree_id,
            "DEV_WORKTREE": str(self.repo),
            "DEV_DJANGO_PORT": str(state.django_port),
            "DEV_VITE_PORT": str(state.vite_port),
            "DEV_PROTOCOL_VERSION": str(DEV_PROTOCOL_VERSION),
        }

    def _managed_environment(
        self,
        state: RuntimeView,
        *,
        for_pane: bool = True,
    ) -> dict[str, str]:
        return build_managed_environment(
            self.repo,
            self.config.project_slug,
            self.identity,
            self.environment,
            dev_base_host=state.dev_base_host,
            django_port=state.django_port,
            vite_port=state.vite_port,
            for_pane=for_pane,
        )

    def command_environment(self) -> dict[str, str]:
        """Return the worktree environment for a foreground one-off command."""
        persisted = self.store.load()
        if persisted is not None and self.tmux.session_exists(self.identity.session_name):
            return self._managed_environment(self._runtime_view(persisted), for_pane=False)
        return build_managed_environment(
            self.repo,
            self.config.project_slug,
            self.identity,
            self.environment,
        )

    def _ensure_frontend_dependencies(self) -> _FrontendPreparation:
        if self.runner.which("yarn", self.environment) is None:
            raise DevError("Missing 'yarn'. Activate the Node version from .nvmrc and enable Corepack")
        frontend_dir = (self.repo / self.config.vite_cwd).resolve()
        if not frontend_dir.is_dir():
            raise DevError(f"Configured vite_cwd does not exist: {self.config.vite_cwd}")
        node_modules = frontend_dir / "node_modules"
        install_state = frontend_dir / ".yarn" / "install-state.gz"
        inputs = [frontend_dir / "package.json", frontend_dir / "yarn.lock", frontend_dir / ".yarnrc.yml"]
        needed = not node_modules.exists() or not install_state.exists()
        removed_symlink = False
        if node_modules.is_symlink():
            node_modules.unlink()
            needed = True
            removed_symlink = True
        if install_state.exists() and any(
            path.exists() and path.stat().st_mtime > install_state.stat().st_mtime for path in inputs
        ):
            needed = True
        if not needed:
            return _FrontendPreparation(False, removed_symlink)
        install_command = ["yarn", "install"]
        if (frontend_dir / "yarn.lock").exists():
            install_command.append("--immutable")
        require_success(
            self.runner.run(install_command, cwd=frontend_dir, env=self.environment),
            "Installing frontend dependencies",
        )
        return _FrontendPreparation(True, removed_symlink)

    def _django_process_command(self, state: RuntimeView) -> list[str]:
        if not state.use_portless:
            return [*self.config.django_command, f"127.0.0.1:{state.django_port}"]
        return self.portless.django_command(
            (self.repo / self.config.django_cwd).resolve(), self.config.django_command
        )

    def _process_specs(self, state: RuntimeView) -> tuple[ProcessSpec, ...]:
        django_cwd = (self.repo / self.config.django_cwd).resolve()
        vite_cwd = (self.repo / self.config.vite_cwd).resolve()
        for label, path in (("django_cwd", django_cwd), ("vite_cwd", vite_cwd)):
            if not path.is_dir():
                raise DevError(f"Configured {label} does not exist: {getattr(self.config, label)}")
        for process in self.config.extra_processes:
            process_cwd = (self.repo / process.cwd).resolve()
            if not process_cwd.is_dir():
                raise DevError(f"Configured cwd for process {process.name} does not exist: {process.cwd}")
        processes = [
            ProcessSpec(
                "django",
                tuple(self._django_process_command(state)),
                self.repo if state.use_portless else django_cwd,
            ),
            ProcessSpec(
                "vite",
                (*self.config.vite_command, "--port", str(state.vite_port), "--strictPort"),
                vite_cwd,
            ),
        ]
        processes.extend(
            ProcessSpec(
                process.name,
                process.command,
                (self.repo / process.cwd).resolve(),
                process.required,
            )
            for process in self.config.extra_processes
        )
        return tuple(processes)

    def _launch_processes(self, state: RuntimeView, environment: dict[str, str]) -> None:
        self.tmux.start_session(
            state.session_name,
            self._process_specs(state),
            environment,
            self._metadata(state),
        )

    def _process_failures(
        self,
        session: str,
        expected: Iterable[str],
    ) -> dict[str, int | None]:
        statuses = self.tmux.process_statuses(session)
        failures: dict[str, int | None] = {}
        for name in expected:
            status = statuses.get(name)
            if status is None:
                failures[name] = None
            elif not status.alive:
                failures[name] = status.exit_code
        return failures

    def _save_output_snapshots(
        self,
        session: str,
        *,
        names: Iterable[str] | None = None,
        lines: int = 1000,
    ) -> tuple[str, ...]:
        warnings: list[str] = []
        try:
            self.store.log_directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            return (f"could not create output snapshot directory: {error}",)
        for name in names or self.expected_processes:
            try:
                output = self.tmux.capture_output(session, name, lines=lines)
            except DevError:
                continue
            path = self.store.snapshot_path(name)
            temporary = path.with_suffix(".log.tmp")
            try:
                temporary.write_text(output + ("\n" if output else ""))
                temporary.replace(path)
            except OSError as error:
                temporary.unlink(missing_ok=True)
                warnings.append(f"could not save {name} output snapshot: {error}")
        return tuple(warnings)

    def _tail(self, name: str, lines: int = 40) -> str:
        if self.tmux.session_exists(self.identity.session_name):
            try:
                return self.tmux.capture_output(
                    self.identity.session_name,
                    name,
                    lines=lines,
                )
            except DevError:
                pass
        path = self.store.snapshot_path(name)
        if not path.exists():
            return ""
        return "\n".join(path.read_text(errors="replace").splitlines()[-lines:])

    def _raise_process_failure(self, failures: dict[str, int | None]) -> None:
        details = []
        for name, status in failures.items():
            label = f"{name} (exit {status})" if status is not None else f"{name} (missing)"
            tail = self._tail(name)
            details.append(f"{label}\n{tail}" if tail else label)
        raise DevError("Required dev process failed:\n" + "\n\n".join(details))

    def _wait_until_ready(self, state: RuntimeView) -> None:
        deadline = time.monotonic() + self.config.startup_timeout
        while True:
            failures = self._process_failures(state.session_name, self.required_processes)
            if failures:
                self._raise_process_failure(failures)
            vite_is_ready = vite_ready(state.vite_port, self.repo)
            django_ready = vite_is_ready and url_ready(state.django_url)
            if django_ready:
                failures = self._process_failures(state.session_name, self.required_processes)
                if failures:
                    self._raise_process_failure(failures)
                return
            if time.monotonic() >= deadline:
                raise DevError(
                    f"Dev environment did not become ready within {self.config.startup_timeout:g}s. "
                    f"Inspect it with: {invocation_name()} logs"
                )
            time.sleep(0.2)

    def start(
        self,
        *,
        no_portless: bool = False,
        on_progress: Callable[[str], None] | None = None,
    ) -> StartResult:
        timeout = max(600.0, self.config.startup_timeout * 2)
        with interrupt_on_termination():
            with worktree_lock(self.config.project_slug, self.identity.worktree_id, timeout):
                return self._start_locked(
                    no_portless=no_portless,
                    on_progress=on_progress,
                )

    def _recover_interrupted_database(self) -> bool:
        state = self.store.load()
        if state is None or not state.database_setup_pending:
            return False
        self._require_no_other_worktree_sessions(
            "recover the incomplete database",
            current_session=self.identity.session_name,
        )
        if self.tmux.session_exists(self.identity.session_name):
            return False
        registry_entry = self.registry.load()
        self.database.drop()

        self._clear_database_setup_marker(state)
        if registry_entry is not None:
            self.registry.database_removed(registry_entry)
        self.registry.remove()
        return True

    def _clear_database_setup_marker(self, state: PersistedState) -> None:
        state.database_setup_pending = False
        if state.vite_port == 0:
            self.store.clear()
        else:
            self.store.save(state)

    def environment_records(self) -> tuple[EnvironmentRecord, ...]:
        managed_sessions = {session.name: session for session in self.tmux.list_managed_sessions()}
        records: list[EnvironmentRecord] = []
        for entry in self.registry.list_project():
            worktree_exists = Path(entry.worktree_path).is_dir()
            session = managed_sessions.get(entry.session_name)
            session_exists = session is not None or self.tmux.session_exists(entry.session_name)
            session_matches = session is not None and (
                session.project_slug == self.config.project_slug
                and session.worktree_id == entry.worktree_id
                and session.worktree_path == entry.worktree_path
            )
            if session_exists and not session_matches:
                session_state = "conflict"
                state = "conflict"
            elif session_matches:
                session_state = "running"
                state = "running" if worktree_exists else "running-orphaned"
            else:
                session_state = "absent"
                state = "stopped" if worktree_exists else "orphaned"
            if entry.database_setup_pending and state != "conflict":
                state = "incomplete"
            records.append(
                EnvironmentRecord(
                    project_id=entry.project_id,
                    environment_id=entry.worktree_id,
                    state=state,
                    worktree_path=entry.worktree_path,
                    worktree_branch=entry.branch,
                    worktree_exists=worktree_exists,
                    session_name=entry.session_name,
                    session_state=session_state,
                    database_name=entry.database_name,
                    database_present=entry.database_present,
                    database_owned=entry.database_owned,
                    database_setup_pending=entry.database_setup_pending,
                    owner_kind=entry.owner_kind,
                    owner_id=entry.owner_id,
                    lease_expires_at=entry.lease_expires_at,
                    registered_at=entry.registered_at,
                    last_seen_at=entry.last_seen_at,
                    last_started_at=entry.last_started_at,
                    last_stopped_at=entry.last_stopped_at,
                )
            )
        return tuple(records)

    def environment_record(self, worktree_id: str) -> EnvironmentRecord:
        record = next(
            (record for record in self.environment_records() if record.environment_id == worktree_id),
            None,
        )
        if record is None:
            raise DevError(f"Unknown registered environment: {worktree_id}")
        return record

    def remove_environment(self, worktree_id: str) -> EnvironmentRemovalResult:
        timeout = max(600.0, self.config.startup_timeout * 2)
        with worktree_lock(self.config.project_slug, worktree_id, timeout):
            entry = self.registry.load_project_entry(worktree_id)
            if entry is None:
                raise DevError(f"Unknown registered environment: {worktree_id}")

            stem, separator, path_hash = entry.worktree_id.rpartition("-")
            expected_database = database_name(self.config.project_slug, stem, path_hash)
            expected_session = f"{self.config.project_slug}-wt-{entry.worktree_id}"
            if not separator or entry.database_name != expected_database:
                raise DevError(
                    f"Refusing to remove {entry.worktree_id}: registered database identity is invalid"
                )
            if entry.session_name != expected_session:
                raise DevError(
                    f"Refusing to remove {entry.worktree_id}: registered tmux session identity is invalid"
                )

            session_exists = self.tmux.session_exists(entry.session_name)
            if session_exists:
                session = next(
                    (
                        session
                        for session in self.tmux.list_managed_sessions()
                        if session.name == entry.session_name
                    ),
                    None,
                )
                if session is None or (
                    session.project_slug != self.config.project_slug
                    or session.worktree_id != entry.worktree_id
                    or session.worktree_path != entry.worktree_path
                ):
                    raise DevError(
                        f"Refusing to stop tmux session {entry.session_name}: metadata does not match "
                        "the registry entry"
                    )

            pending = self.registry.cleanup_started(entry, session_stopped=False)
            session_stopped = False
            if session_exists:
                self.tmux.stop_session(entry.session_name)
                session_stopped = True
                pending = self.registry.cleanup_started(pending, session_stopped=True)

            database_dropped = False
            database_was_absent = False
            database_retained = False
            if entry.database_owned:
                database_dropped = self.database.drop(entry.database_name)
                database_was_absent = not database_dropped
                pending = self.registry.database_removed(pending)
            else:
                database_retained = entry.database_present is not False

            self.registry.remove_project_entry(entry.worktree_id)
            return EnvironmentRemovalResult(
                environment_id=entry.worktree_id,
                session_stopped=session_stopped,
                database_dropped=database_dropped,
                database_was_absent=database_was_absent,
                database_retained=database_retained,
            )

    def _start_locked(
        self,
        *,
        no_portless: bool = False,
        on_progress: Callable[[str], None] | None = None,
    ) -> StartResult:
        # Reject incompatible or corrupt state before starting an otherwise
        # empty dedicated tmux server or performing any other mutation.
        self.store.load()
        self.tmux.ensure_server()
        existing_registry_entry = self.registry.load()
        self.registry.register()
        state: RuntimeView | None = None
        setup_state: PersistedState | None = None
        portless_selection: PortlessSelection | None = None
        preparation: DatabasePreparationResult | None = None
        process_environment = self.environment
        recovered_database = False
        frontend = _FrontendPreparation(False, False)
        try:
            self._require_no_other_worktree_sessions(
                "start the development environment",
                current_session=self.identity.session_name,
            )
            if self.tmux.session_exists(self.identity.session_name):
                failures = self._process_failures(
                    self.identity.session_name,
                    self.required_processes,
                )
                if failures:
                    self._raise_process_failure(failures)
                persisted = self.store.load()
                if persisted is None:
                    raise DevError("Dev session is running without a state file")
                current = self._runtime_view(persisted)
                if not vite_ready(current.vite_port, self.repo) or not url_ready(current.django_url):
                    raise DevError(
                        f"Dev processes are alive but not ready; inspect: {invocation_name()} logs"
                    )
                self.registry.database_ready(created=False)
                self.registry.started(
                    django_port=current.django_port,
                    vite_port=current.vite_port,
                )
                return StartResult(
                    environment=self._environment_summary(current),
                    already_running=True,
                    frontend_dependencies_installed=False,
                    frontend_symlink_removed=False,
                    database_created=False,
                    recovered_incomplete_database=False,
                    portless_reason=None,
                )

            recovered_database = self._recover_interrupted_database()
            self.database.require_tools()
            frontend = self._ensure_frontend_dependencies()
            setup_state = self.store.load()
            portless_selection = self.portless.select(
                self.config.portless,
                force_off=no_portless,
            )
            dev_base_host = ""
            if portless_selection.enabled:
                parsed_portless_url = urlparse(self.portless.resolve_url())
                dev_base_host = parsed_portless_url.hostname or ""

            def database_creation_started() -> None:
                nonlocal setup_state
                if setup_state is None:
                    setup_state = PersistedState(
                        django_port=0,
                        vite_port=0,
                        use_portless=False,
                        database_setup_pending=True,
                    )
                else:
                    setup_state.database_setup_pending = True
                self.store.save(setup_state)
                self.registry.database_setup_started()

            preparation = self.database.ensure(
                on_database_creation=database_creation_started,
                on_progress=on_progress,
                dev_base_host=dev_base_host,
            )
            self.registry.database_ready(created=preparation.created)
            if setup_state is not None and setup_state.vite_port > 0:
                self._clear_database_setup_marker(setup_state)

            with allocation_lock():
                state = self._allocate_state(portless_selection.enabled)
                state.database_setup_pending = False
                self._save_state(state)
                process_environment = self._managed_environment(state)
                self._launch_processes(state, process_environment)
            assert state is not None
            self._wait_until_ready(state)
            self.registry.started(
                django_port=state.django_port,
                vite_port=state.vite_port,
            )
        except BaseException as error:
            if state is not None and self.tmux.session_exists(state.session_name):
                for warning in self._save_output_snapshots(state.session_name):
                    error.add_note(warning)
                try:
                    self.tmux.stop_session(state.session_name)
                except DevError as cleanup_error:
                    error.add_note(f"could not stop the failed dev session: {cleanup_error}")

            owns_database = preparation is not None and preparation.created
            owns_database = owns_database or (setup_state is not None and setup_state.database_setup_pending)
            database_cleaned_up = False
            if owns_database:
                marker = state.persisted if state is not None else setup_state
                assert marker is not None
                marker.database_setup_pending = True
                try:
                    self.registry.database_setup_started()
                except DevError as cleanup_error:
                    error.add_note(
                        f"could not save failed database ownership in the registry: {cleanup_error}"
                    )
                try:
                    self.store.save(marker)
                except (DevError, OSError) as cleanup_error:
                    error.add_note(f"could not save failed dev state: {cleanup_error}")
                else:
                    try:
                        self._require_no_other_worktree_sessions(
                            "clean up the new database after failed startup"
                        )
                        self.database.drop()
                    except DevError as cleanup_error:
                        error.add_note(f"could not clean up the new database: {cleanup_error}")
                    else:
                        try:
                            self._clear_database_setup_marker(marker)
                        except (DevError, OSError) as cleanup_error:
                            error.add_note(f"could not save database cleanup state: {cleanup_error}")
                        else:
                            try:
                                self.registry.database_removed()
                            except DevError as cleanup_error:
                                error.add_note(
                                    f"could not record the failed startup database cleanup: {cleanup_error}"
                                )
                            else:
                                database_cleaned_up = True
            try:
                session_remains = self.tmux.session_exists(self.identity.session_name)
                if not session_remains and database_cleaned_up:
                    self.registry.remove()
                elif not session_remains and not owns_database and preparation is not None:
                    self.registry.stopped(database_present=True)
                elif not session_remains and preparation is None:
                    if existing_registry_entry is None:
                        self.registry.remove()
                    else:
                        self.registry.stopped(
                            database_present=existing_registry_entry.database_present,
                        )
            except DevError as cleanup_error:
                error.add_note(f"could not update the dev registry after failed startup: {cleanup_error}")
            raise
        assert portless_selection is not None
        return StartResult(
            environment=self._environment_summary(state),
            already_running=False,
            frontend_dependencies_installed=frontend.installed,
            frontend_symlink_removed=frontend.removed_symlink,
            database_created=preparation.created if preparation is not None else False,
            recovered_incomplete_database=recovered_database,
            portless_reason=None if state.use_portless else portless_selection.reason,
        )

    def stop(self, *, drop_database: bool = False) -> StopResult:
        timeout = max(600.0, self.config.startup_timeout * 2)
        with worktree_lock(self.config.project_slug, self.identity.worktree_id, timeout):
            return self._stop_locked(drop_database=drop_database)

    def _stop_processes_locked(self) -> tuple[bool, tuple[str, ...]]:
        if not self.tmux.session_exists(self.identity.session_name):
            return False, ()
        warnings = self._save_output_snapshots(self.identity.session_name)
        try:
            self.tmux.stop_session(self.identity.session_name)
        except BaseException as error:
            for warning in warnings:
                error.add_note(warning)
            raise
        return True, warnings

    def _stop_locked(self, *, drop_database: bool = False) -> StopResult:
        state = self.store.load()
        existing_registry_entry = self.registry.load()
        interrupted_setup = state is not None and state.database_setup_pending
        if drop_database or interrupted_setup:
            self._require_no_other_worktree_sessions(
                "drop the worktree database",
                current_session=self.identity.session_name,
            )
        was_running, warnings = self._stop_processes_locked()
        database_dropped = False
        if drop_database or interrupted_setup:
            self._require_no_other_worktree_sessions("drop the worktree database")
            database_dropped = self.database.drop()
        if state:
            self._clear_database_setup_marker(state)
        if drop_database or interrupted_setup:
            if existing_registry_entry is not None:
                self.registry.database_removed(existing_registry_entry)
            self.registry.remove()
        elif existing_registry_entry is not None or state is not None or was_running:
            registry_entry = self.registry.register()
            self.registry.stopped(
                database_present=registry_entry.database_present,
            )
        return StopResult(
            was_running=was_running,
            database_drop_requested=drop_database,
            database_dropped=database_dropped,
            recovered_incomplete_database=interrupted_setup,
            warnings=warnings,
        )

    def restart(self, *, no_portless: bool = False) -> RestartResult:
        timeout = max(600.0, self.config.startup_timeout * 2)
        with interrupt_on_termination():
            with worktree_lock(self.config.project_slug, self.identity.worktree_id, timeout):
                return self._restart_locked(no_portless=no_portless)

    def _restart_locked(self, *, no_portless: bool = False) -> RestartResult:
        persisted = self.store.load()
        self._require_no_other_worktree_sessions(
            "restart the development environment",
            current_session=self.identity.session_name,
        )
        if persisted is None or not self.tmux.session_exists(self.identity.session_name):
            raise DevError(f"Dev environment is not running. Start it with: {invocation_name()} up")
        if persisted.database_setup_pending:
            raise DevError(f"Database setup is incomplete. Recover it with: {invocation_name()} up")
        self.registry.register()

        _was_running, warnings = self._stop_processes_locked()
        state: RuntimeView | None = None
        process_environment = self.environment
        portless_selection: PortlessSelection | None = None
        try:
            portless_selection = self.portless.select(
                self.config.portless,
                force_off=no_portless,
            )
            with allocation_lock():
                state = self._allocate_state(portless_selection.enabled)
                self._save_state(state)
                process_environment = self._managed_environment(state)
                self._launch_processes(state, process_environment)
            self._wait_until_ready(state)
            self.registry.database_ready(created=False)
            self.registry.started(
                django_port=state.django_port,
                vite_port=state.vite_port,
            )
        except BaseException as error:
            for warning in warnings:
                error.add_note(warning)
            if state is not None and self.tmux.session_exists(state.session_name):
                for warning in self._save_output_snapshots(state.session_name):
                    error.add_note(warning)
                try:
                    self.tmux.stop_session(state.session_name)
                except DevError as cleanup_error:
                    error.add_note(f"could not stop the failed replacement session: {cleanup_error}")
            try:
                if not self.tmux.session_exists(self.identity.session_name):
                    self.registry.stopped(database_present=True)
            except DevError as cleanup_error:
                error.add_note(f"could not update the dev registry after failed restart: {cleanup_error}")
            raise

        assert portless_selection is not None
        return RestartResult(
            environment=self._environment_summary(state),
            portless_reason=None if state.use_portless else portless_selection.reason,
            warnings=warnings,
        )

    def restart_process(self, name: str) -> ProcessRestartResult:
        timeout = max(600.0, self.config.startup_timeout * 2)
        with worktree_lock(self.config.project_slug, self.identity.worktree_id, timeout):
            return self._restart_process_locked(name)

    def _restart_process_locked(self, name: str) -> ProcessRestartResult:
        if name not in self.expected_processes:
            raise DevError(f"Unknown process '{name}'. Expected: {', '.join(self.expected_processes)}")
        self._require_no_other_worktree_sessions(
            f"restart {name}",
            current_session=self.identity.session_name,
        )
        state = self._live_state()
        other_required = [process for process in self.required_processes if process != name]
        failures = self._process_failures(state.session_name, other_required)
        if failures:
            self._raise_process_failure(failures)
        warnings = self._save_output_snapshots(state.session_name, names=(name,))
        try:
            self.tmux.restart_process(state.session_name, name)
            if name in {"django", "vite"}:
                self._wait_until_ready(state)
            else:
                time.sleep(0.5)
                failures = self._process_failures(state.session_name, [name])
                if failures:
                    self._raise_process_failure(failures)
        except BaseException as error:
            for warning in warnings:
                error.add_note(warning)
            raise
        return ProcessRestartResult(name, warnings)

    def _live_state(self, *, require_ready: bool = False) -> RuntimeView:
        persisted = self.store.load()
        if persisted is None or not self.tmux.session_exists(self.identity.session_name):
            raise DevError(f"Dev environment is not running. Start it with: {invocation_name()} up")
        state = self._runtime_view(persisted)
        if require_ready:
            failures = self._process_failures(
                state.session_name,
                self.required_processes,
            )
            if failures:
                self._raise_process_failure(failures)
            if not vite_ready(state.vite_port, self.repo) or not url_ready(state.django_url):
                raise DevError(f"Dev processes are alive but not ready; inspect: {invocation_name()} logs")
        return state

    def live_environment(self, *, require_ready: bool = False) -> EnvironmentSummary:
        return self._environment_summary(self._live_state(require_ready=require_ready))

    def status_records(self, *, all_worktrees: bool = False) -> tuple[StatusRecord, ...]:
        sessions = [
            session
            for session in self.tmux.list_managed_sessions()
            if session.project_slug == self.config.project_slug
        ]
        if all_worktrees:
            return tuple(self._status_record(session, probe_readiness=False) for session in sessions)
        current = next((session for session in sessions if session.name == self.identity.session_name), None)
        return (self._status_record(current, probe_readiness=True),)

    def _status_record(
        self,
        session: ManagedSession | None,
        *,
        probe_readiness: bool,
    ) -> StatusRecord:
        is_current = session is None or (
            session.worktree_id == self.identity.worktree_id and session.worktree_path == str(self.repo)
        )
        statuses = self.tmux.process_statuses(session.name) if session is not None else {}
        required: dict[str, bool | None]
        if is_current:
            required = {
                "django": True,
                "vite": True,
                **{process.name: process.required for process in self.config.extra_processes},
            }
            names = [*self.expected_processes, *(sorted(set(statuses) - set(self.expected_processes)))]
        else:
            required = {name: True if name in {"django", "vite"} else None for name in statuses}
            names = sorted(statuses, key=lambda name: (name not in {"django", "vite"}, name))

        processes: list[StatusProcessRecord] = []
        for name in names:
            status = statuses.get(name)
            if status is None:
                state = "missing"
            elif status.alive:
                state = "running"
            else:
                state = "exited"
            processes.append(
                StatusProcessRecord(
                    name=name,
                    required=required.get(name),
                    state=state,
                    exit_code=status.exit_code if status is not None else None,
                    signal=status.signal if status is not None else None,
                )
            )

        django_url = f"http://localhost:{session.django_port}" if session and session.django_port else None
        vite_url = f"http://localhost:{session.vite_port}" if session and session.vite_port else None
        vite_port = session.vite_port if session is not None else 0
        worktree = session.worktree_path if session is not None else str(self.repo)
        worktree_id = session.worktree_id if session is not None else self.identity.worktree_id
        session_name = session.name if session is not None else self.identity.session_name
        project_id = session.project_slug if session is not None else self.config.project_id
        branch = current_branch(Path(worktree))
        if is_current:
            persisted = self.store.load()
            if persisted is not None:
                current = self._runtime_view(persisted)
                django_url = current.django_url or None
                vite_url = current.vite_url or None
                vite_port = current.vite_port
            database = self.identity.database_name
        else:
            stem, _, path_hash = worktree_id.rpartition("-")
            database = database_name(project_id, stem or worktree_id, path_hash)

        session_state = (
            "absent"
            if session is None
            else ("degraded" if any(process.state != "running" for process in processes) else "running")
        )
        if not probe_readiness:
            readiness = "notProbed"
        elif (
            session_state == "absent"
            or any(process.required is True and process.state != "running" for process in processes)
            or django_url is None
            or vite_url is None
        ):
            readiness = "notReady"
        else:
            readiness = (
                "ready" if vite_ready(vite_port, Path(worktree)) and url_ready(django_url) else "notReady"
            )
        return StatusRecord(
            project_id=project_id,
            worktree=worktree,
            worktree_id=worktree_id,
            branch=branch,
            session_name=session_name,
            session_state=session_state,
            readiness=readiness,
            django_url=django_url,
            vite_url=vite_url,
            database_name=database,
            processes=tuple(processes),
        )

    def log_records(self, target: str | None = None, *, lines: int | None = None) -> tuple[LogRecord, ...]:
        if target is not None and target not in self.expected_processes:
            raise DevError(f"Unknown log target '{target}'. Expected: {', '.join(self.expected_processes)}")
        line_count = lines if lines is not None else (200 if target else 50)
        if line_count <= 0:
            raise DevError("Log line count must be positive")
        names = (target,) if target else self.expected_processes
        state = self.store.load()
        running = state is not None and self.tmux.session_exists(self.identity.session_name)
        records: list[LogRecord] = []
        for name in names:
            output: str | None = None
            if running:
                try:
                    output = self.tmux.capture_output(
                        self.identity.session_name,
                        name,
                        lines=line_count,
                    )
                except DevError:
                    pass
            if output is None:
                path = self.store.snapshot_path(name)
                if path.exists():
                    output = "\n".join(path.read_text(errors="replace").splitlines()[-line_count:])
            if output is None:
                continue
            records.append(LogRecord(name=name, output=output, lines=line_count))
        if not records:
            raise DevError(f"No dev output is available. Start the environment with: {invocation_name()} up")
        return tuple(records)

    def attach(self, target: str | None = None) -> None:
        if target is not None and target not in self.expected_processes:
            raise DevError(f"Unknown process '{target}'. Expected: {', '.join(self.expected_processes)}")
        state = self._live_state()
        self.tmux.attach(state.session_name, target)

    def manage(self, args: list[str]) -> int:
        if not args:
            raise DevError(f"Usage: {invocation_name()} manage <command> [args...]")
        if not self.database.exists(self.identity.database_name):
            raise DevError(
                f"Database '{self.identity.database_name}' does not exist; run: {invocation_name()} up"
            )
        state = self.store.load()
        base_host = ""
        if state and self.tmux.session_exists(self.identity.session_name):
            base_host = self._runtime_view(state).dev_base_host
        return self.database.run_manage(args, dev_base_host=base_host).returncode

    def _verification_command_check(
        self,
        name: str,
        configured: tuple[str, ...],
    ) -> DoctorCheck:
        setting = f"{name}_command"
        if not configured:
            return DoctorCheck(
                f"command:{name}",
                "warning",
                f"not configured; set {setting} in config/dev.toml",
            )
        executable = configured[0]
        if Path(executable).is_absolute() or "/" in executable:
            path = Path(executable)
            if not path.is_absolute():
                path = self.repo / path
            path = path.resolve()
            if not path.is_file():
                return DoctorCheck(
                    f"command:{name}",
                    "error",
                    f"configured entry point does not exist: {path}",
                )
            if not os.access(path, os.X_OK):
                return DoctorCheck(
                    f"command:{name}",
                    "error",
                    f"configured entry point is not executable: {path}",
                )
            detail = str(path)
        else:
            resolved = self.runner.which(executable, self.environment)
            if resolved is None:
                return DoctorCheck(
                    f"command:{name}",
                    "error",
                    f"configured entry point is not on PATH: {executable}",
                )
            detail = resolved
        return DoctorCheck(f"command:{name}", "ok", detail)

    def doctor_report(self) -> DoctorReport:
        tools = tuple(
            ToolRecord(command, self.runner.which(command, self.environment))
            for command in ("uv", "node", "yarn", "tmux", "psql", "createdb", "dropdb", "portless")
        )
        tool_paths = {tool.name: tool.path for tool in tools}
        dropdb_force_supported = self.database.supports_force_drop() if tool_paths["dropdb"] else False
        if not self.store.state_path.exists():
            state = DoctorStateRecord(self.store.state_path, "missing", None)
        else:
            try:
                persisted = self.store.load()
            except DevError:
                state = DoctorStateRecord(self.store.state_path, "invalid", None)
            else:
                assert persisted is not None
                state = DoctorStateRecord(
                    self.store.state_path,
                    "valid",
                    persisted.database_setup_pending,
                )

        checks: list[DoctorCheck] = []
        for tool in tools:
            optional = tool.name == "portless"
            checks.append(
                DoctorCheck(
                    name=f"tool:{tool.name}",
                    status="ok" if tool.path else ("warning" if optional else "error"),
                    detail=tool.path or ("optional; not installed" if optional else "not found on PATH"),
                )
            )
        checks.extend(
            self._verification_command_check(name, command)
            for name, command in (
                ("test", self.config.test_command),
                ("jstest", self.config.jstest_command),
                ("lint", self.config.lint_command),
                ("check", self.config.check_command),
            )
        )
        checks.append(
            DoctorCheck(
                name="dropdb:force",
                status="ok" if dropdb_force_supported else "error",
                detail=(
                    "supported"
                    if dropdb_force_supported
                    else "installed dropdb must support forced connection termination"
                ),
            )
        )
        managed_sessions = len(self.tmux.list_managed_sessions())
        checks.append(
            DoctorCheck(
                name="tmux:backend",
                status="ok" if tool_paths["tmux"] else "error",
                detail=f"socket {self.tmux.socket_name}; {managed_sessions} managed session(s)",
            )
        )
        if tool_paths["psql"]:
            try:
                self.database.exists(self.identity.database_name)
            except DevError as error:
                postgres_status = "error"
                postgres_detail = str(error)
            else:
                postgres_status = "ok"
                postgres_detail = "connection succeeded without changing databases"
        else:
            postgres_status = "error"
            postgres_detail = "psql is not available"
        checks.append(DoctorCheck("postgres:connectivity", postgres_status, postgres_detail))
        portless = self.portless.diagnostics(self.config.portless)
        portless_status = "ok"
        if self.config.portless == "required" and not portless.selected:
            portless_status = "error"
        elif self.config.portless == "auto" and not portless.selected:
            portless_status = "warning"
        checks.append(DoctorCheck("portless", portless_status, portless.reason))
        return DoctorReport(
            package_version=package_version(),
            protocol_version=DEV_PROTOCOL_VERSION,
            project_id=self.config.project_id,
            branch=self.identity.branch,
            worktree_id=self.identity.worktree_id,
            worktree_path=str(self.repo),
            session_name=self.identity.session_name,
            database_name=self.identity.database_name,
            config_paths=self.config.paths,
            state=state,
            checks=tuple(checks),
        )
