from __future__ import annotations

from contextlib import redirect_stderr
from contextlib import redirect_stdout
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import signal
import socket
from tempfile import TemporaryDirectory
from typing import Callable
from typing import Sequence
import unittest
from unittest.mock import patch

from alliance_platform.dev.config import load_config
from alliance_platform.dev.errors import DevError
from alliance_platform.dev.identity import database_name
from alliance_platform.dev.identity import resolve_identity
from alliance_platform.dev.lifecycle import DevEnvironment
from alliance_platform.dev.lifecycle import find_free_port
from alliance_platform.dev.lifecycle import interrupt_on_termination
from alliance_platform.dev.lifecycle import port_available
from alliance_platform.dev.lifecycle import tcp_ready
from alliance_platform.dev.lifecycle import vite_ready
from alliance_platform.dev.models import DevConfig
from alliance_platform.dev.models import PersistedState
from alliance_platform.dev.models import WorktreeIdentity
from alliance_platform.dev.registry import RegistryStore
from alliance_platform.dev.runner import CommandResult
from alliance_platform.dev.runner import Runner
from alliance_platform.dev.state import StateStore
from alliance_platform.dev.state import allocation_lock
from alliance_platform.dev.state import worktree_lock

from tests.helpers import RecordedCall
from tests.helpers import RecordingRunner
from tests.helpers import make_repo


def persisted_state() -> PersistedState:
    return PersistedState(
        django_port=8000,
        vite_port=5173,
        use_portless=False,
    )


def make_dev_environment(
    runner: Runner,
    repo: Path,
    config: DevConfig,
    identity: WorktreeIdentity,
    process_environment: dict[str, str],
    control_environment: dict[str, str],
) -> DevEnvironment:
    return DevEnvironment(
        runner,
        repo,
        config,
        identity,
        process_environment,
        control_environment,
        registry=RegistryStore(
            repo,
            config,
            identity,
            environ={**process_environment, **control_environment},
            root=repo / ".test-dev-registry",
        ),
    )


def register_environment(
    dev: DevEnvironment,
    *,
    worktree_id: str = "agent-cleanup-0123456789",
    worktree_path: str = "/missing/agent-cleanup",
    database_owned: bool = True,
    database_present: bool | None = True,
    setup_pending: bool = False,
):
    current = dev.registry.register()
    dev.registry.remove()
    stem, _, path_hash = worktree_id.rpartition("-")
    entry = replace(
        current,
        worktree_id=worktree_id,
        worktree_path=worktree_path,
        branch="codex/cleanup",
        database_name=database_name(dev.config.project_slug, stem, path_hash),
        database_present=database_present,
        database_owned=database_owned,
        database_ownership_token="owned-token" if database_owned else None,
        database_setup_pending=setup_pending,
        session_name=f"{dev.config.project_slug}-wt-{worktree_id}",
    )
    dev.registry.save_project_entry(entry)
    return entry


def destructive_drop_calls(runner: RecordingRunner) -> list[RecordedCall]:
    return [
        call for call in runner.calls if call.args[0] == "dropdb" and call.args[:2] != ("dropdb", "--help")
    ]


def add_managed_session(
    runner: LifecycleRunner,
    name: str,
    *,
    project: str,
    worktree_path: str,
    worktree_id: str,
    django_port: int = 8000,
    vite_port: int = 5173,
) -> None:
    runner.sessions.add(name)
    runner.session_environment[name] = {
        "DEV_PROJECT": project,
        "DEV_WORKTREE": worktree_path,
        "DEV_WORKTREE_ID": worktree_id,
        "DEV_DJANGO_PORT": str(django_port),
        "DEV_VITE_PORT": str(vite_port),
        "DEV_PROTOCOL_VERSION": "1",
    }


class LifecycleRunner(RecordingRunner):
    """Boundary fake for tmux and PostgreSQL used by a public lifecycle test."""

    def __init__(self) -> None:
        super().__init__()
        self.sessions: set[str] = set()
        self.session_environment: dict[str, dict[str, str]] = {}
        self.panes: dict[str, set[str]] = {}
        self.pane_output: dict[str, str] = {}
        self.database_exists = True
        self.interrupt_on_migrate = False
        self.fail_migrate = False
        self.fail_createdb_uncertain = False
        self.fail_drop = False
        self.fail_new_window = False
        self.supports_force_drop = True
        self.failed_pane: str | None = None
        self.createdb_observer: Callable[[], None] | None = None

    def which(self, command: str, env: dict[str, str] | None = None) -> str | None:
        del env
        return None if command == "portless" else f"/fake/{command}"

    def run(
        self,
        args: Sequence[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        capture: bool = False,
        input_text: str | None = None,
    ) -> CommandResult:
        argv = tuple(args)
        self.calls.append(
            RecordedCall(argv, cwd, dict(env) if env is not None else None, capture, input_text)
        )
        if argv[0] == "psql":
            return CommandResult(0, "1\n" if self.database_exists else "")
        if argv[0] == "createdb":
            if self.createdb_observer:
                self.createdb_observer()
            self.database_exists = True
            if self.fail_createdb_uncertain:
                return CommandResult(1, "connection lost after request")
            return CommandResult(0, "")
        if argv[:2] == ("dropdb", "--help"):
            output = "  --force  try to terminate other connections\n" if self.supports_force_drop else ""
            return CommandResult(0, output)
        if argv[0] == "dropdb":
            if self.fail_drop:
                return CommandResult(1, "database is still in use")
            self.database_exists = False
            return CommandResult(0, "")
        if "manage.py" in argv and "migrate" in argv and self.interrupt_on_migrate:
            raise KeyboardInterrupt
        if "manage.py" in argv and "migrate" in argv and self.fail_migrate:
            return CommandResult(1, "migration failed")
        if Path(argv[0]).name != "tmux":
            return CommandResult(0, "")

        action = argv[5] if len(argv) > 5 and argv[1] == "-L" else argv[1]
        if action == "has-session":
            return CommandResult(0 if argv[-1] in self.sessions else 1, "")
        if action == "new-session":
            if self.fail_new_window:
                return CommandResult(1, "could not start process")
            session = argv[argv.index("-s") + 1]
            self.sessions.add(session)
            metadata: dict[str, str] = {}
            for index, value in enumerate(argv):
                if value == "-e":
                    key, item = argv[index + 1].split("=", 1)
                    metadata[key] = item
            self.session_environment[session] = metadata
            self.panes[session] = {argv[argv.index("-n") + 1]}
            return CommandResult(0, "")
        if action == "show-environment":
            session = argv[argv.index("-t") + 1]
            key = argv[-1]
            environment_value = self.session_environment.get(session, {}).get(key)
            return (
                CommandResult(0, f"{key}={environment_value}\n")
                if environment_value is not None
                else CommandResult(1, "")
            )
        if action == "list-sessions":
            return CommandResult(0, "".join(f"{session}\n" for session in sorted(self.sessions)))
        if action == "new-window":
            if self.fail_new_window:
                return CommandResult(1, "could not start process")
            session = argv[argv.index("-t") + 1]
            name = argv[argv.index("-n") + 1]
            self.panes.setdefault(session, set()).add(name)
            return CommandResult(0, "")
        if action == "respawn-window":
            return CommandResult(0, "")
        if action == "kill-window":
            session, name = argv[-1].split(":", 1)
            self.panes.get(session, set()).discard(name)
            return CommandResult(0, "")
        if action == "list-panes":
            session = argv[argv.index("-t") + 1]
            output = "".join(
                f"{name}\t1\t23\t\n" if name == self.failed_pane else f"{name}\t0\t\t\n"
                for name in sorted(self.panes.get(session, set()))
            )
            return CommandResult(0, output)
        if action == "capture-pane":
            return CommandResult(0, self.pane_output.get(argv[-1], ""))
        if action == "kill-session":
            session = argv[-1]
            self.sessions.discard(session)
            self.panes.pop(session, None)
            return CommandResult(0, "")
        return CommandResult(0, "")


class StateStoreTests(unittest.TestCase):
    def test_version_three_state_round_trips_exact_compact_shape_and_preserves_snapshots(self) -> None:
        with TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            store = StateStore(repo)
            state = persisted_state()
            store.save(state)
            snapshot = store.snapshot_path("django")
            snapshot.parent.mkdir()
            snapshot.write_text("post-mortem output\n")

            loaded = store.load()
            self.assertEqual(loaded, state)
            assert loaded is not None
            loaded.database_setup_pending = True
            store.save(loaded)

            persisted = json.loads(store.state_path.read_text())
            self.assertEqual(
                persisted,
                {
                    "version": 3,
                    "protocolVersion": 1,
                    "djangoPort": 8000,
                    "vitePort": 5173,
                    "usePortless": False,
                    "databaseSetupPending": True,
                },
            )
            self.assertEqual(snapshot.read_text(), "post-mortem output\n")
            self.assertFalse(store.state_path.with_suffix(".json.tmp").exists())

    def test_invalid_versions_shapes_and_exact_types_have_actionable_errors(self) -> None:
        valid = persisted_state().as_dict()
        cases = {
            "non-object": ([], "state must be a JSON object"),
            "legacy version": ({**valid, "version": 1}, "unsupported schema version 1"),
            "unknown version": ({**valid, "version": 99}, "unsupported schema version 99"),
            "boolean version": ({**valid, "version": True}, "version must be an integer"),
            "unknown protocol": (
                {**valid, "protocolVersion": 99},
                "unsupported protocol version 99",
            ),
            "boolean port": ({**valid, "djangoPort": True}, "djangoPort must be an integer"),
            "port out of range": ({**valid, "vitePort": 65536}, "vitePort must be between"),
            "coerced boolean": ({**valid, "usePortless": 0}, "usePortless must be a boolean"),
            "missing field": (
                {key: value for key, value in valid.items() if key != "vitePort"},
                "missing field.*vitePort",
            ),
            "unknown field": ({**valid, "phase": "ready"}, "unknown field.*phase"),
            "zero outside setup": ({**valid, "vitePort": 0}, "vitePort may be 0 only"),
        }
        for label, (value, expected) in cases.items():
            with self.subTest(label=label), TemporaryDirectory() as temporary:
                store = StateStore(Path(temporary) / "repo")
                store.ensure()
                store.state_path.write_text(json.dumps(value))

                with self.assertRaisesRegex(DevError, expected) as raised:
                    store.load()

                self.assertIn(str(store.state_path), str(raised.exception))
                self.assertIn("Clear this file", str(raised.exception))

    def test_zero_ports_are_valid_only_for_pending_preallocation_state(self) -> None:
        with TemporaryDirectory() as temporary:
            store = StateStore(Path(temporary) / "repo")
            pending = PersistedState(
                django_port=0,
                vite_port=0,
                use_portless=False,
                database_setup_pending=True,
            )

            store.save(pending)

            self.assertEqual(store.load(), pending)


class TerminationHandlingTests(unittest.TestCase):
    def test_sigterm_enters_the_keyboard_interrupt_cleanup_path(self) -> None:
        with self.assertRaises(KeyboardInterrupt):
            with interrupt_on_termination():
                signal.raise_signal(signal.SIGTERM)


class LifecycleLockTests(unittest.TestCase):
    def test_worktrees_serialize_independently_within_a_project(self) -> None:
        with TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {"XDG_CACHE_HOME": temporary}):
                with worktree_lock("demo-project", "first"):
                    with self.assertRaisesRegex(DevError, "Timed out waiting"):
                        with worktree_lock("demo-project", "first", timeout=0):
                            self.fail("same-worktree lock unexpectedly re-entered")
                    with worktree_lock("demo-project", "second", timeout=0):
                        pass

    def test_allocation_lock_is_shared_by_different_projects(self) -> None:
        with TemporaryDirectory() as temporary:
            with patch.dict(os.environ, {"XDG_CACHE_HOME": temporary}):
                with allocation_lock():
                    with self.assertRaisesRegex(DevError, "Timed out waiting"):
                        with allocation_lock(timeout=0):
                            self.fail("machine-wide allocation lock unexpectedly re-entered")


class PortAllocationTests(unittest.TestCase):
    def test_port_probe_and_readiness_detect_an_ipv6_localhost_listener(self) -> None:
        try:
            with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as listener:
                listener.bind(("::1", 0))
                listener.listen()
                port = listener.getsockname()[1]

                self.assertFalse(port_available(port))
                self.assertTrue(tcp_ready(port))
        except OSError as error:
            self.skipTest(f"IPv6 localhost is unavailable: {error}")

    def test_free_port_skips_registered_and_unavailable_ports(self) -> None:
        with patch("alliance_platform.dev.lifecycle.port_available", side_effect=lambda port: port != 8001):
            self.assertEqual(find_free_port(8000, {8000}), 8002)

    def test_free_port_reports_exhaustion(self) -> None:
        with self.assertRaisesRegex(DevError, "starting from 65535"):
            find_free_port(65535, {65535})


class ViteReadinessTests(unittest.TestCase):
    def test_vite_probe_requires_the_expected_project(self) -> None:
        with TemporaryDirectory() as temporary:
            project = Path(temporary) / "project"
            project.mkdir()
            with patch("alliance_platform.dev.lifecycle.http.client.HTTPConnection") as connection_type:
                response = connection_type.return_value.getresponse.return_value
                response.status = 200
                response.read.return_value = json.dumps({"check": "ok", "projectDir": str(project)}).encode()

                self.assertTrue(vite_ready(5173, project))

                connection_type.assert_called_once_with("localhost", 5173, timeout=0.5)
                connection_type.return_value.request.assert_called_once_with("GET", "/check")
                connection_type.return_value.close.assert_called_once_with()

    def test_vite_probe_rejects_a_different_project(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "project"
            project.mkdir()
            with patch("alliance_platform.dev.lifecycle.http.client.HTTPConnection") as connection_type:
                response = connection_type.return_value.getresponse.return_value
                response.status = 200
                response.read.return_value = json.dumps(
                    {"check": "ok", "projectDir": str(root / "other")}
                ).encode()

                self.assertFalse(vite_ready(5173, project))

    def test_vite_probe_rejects_an_invalid_response(self) -> None:
        with TemporaryDirectory() as temporary:
            project = Path(temporary)
            with patch("alliance_platform.dev.lifecycle.http.client.HTTPConnection") as connection_type:
                response = connection_type.return_value.getresponse.return_value
                response.status = 200
                response.read.return_value = b"not json"

                self.assertFalse(vite_ready(5173, project))

    def test_machine_reservations_include_every_managed_dedicated_session(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(
                root / "repo",
                config="django_port_base = 8123\nvite_port_base = 5123\n",
            )
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = resolve_identity(repo, config)
            runner = LifecycleRunner()
            add_managed_session(
                runner,
                "other-project-session",
                project="older-project",
                worktree_path="/tmp/older-worktree",
                worktree_id="older-worktree-0123456789",
                django_port=8123,
                vite_port=5123,
            )
            dev = make_dev_environment(runner, repo, config, identity, {}, {})

            with patch("alliance_platform.dev.lifecycle.port_available", return_value=True):
                state = dev._allocate_state(use_portless=False)

            self.assertNotIn(state.django_port, {5123, 8123})
            self.assertNotIn(state.vite_port, {5123, 8123})


class CommandEnvironmentTests(unittest.TestCase):
    def test_foreground_environment_adds_live_ports_only_while_the_session_exists(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = resolve_identity(repo, config)
            runner = LifecycleRunner()
            inherited = {
                "DB_NAME": "wrong",
                "DEV_DJANGO_PORT": "9999",
                "DEV_VITE_PORT": "9998",
                "TERM": "xterm-256color",
            }
            dev = make_dev_environment(runner, repo, config, identity, inherited, {})

            stopped = dev.command_environment()
            self.assertEqual(stopped["DB_NAME"], identity.database_name)
            self.assertEqual(stopped["DEV_BASE_HOST"], "")
            self.assertNotIn("DEV_DJANGO_PORT", stopped)
            self.assertNotIn("DEV_VITE_PORT", stopped)
            self.assertEqual(stopped["TERM"], "xterm-256color")

            dev.store.save(persisted_state())
            add_managed_session(
                runner,
                identity.session_name,
                project=config.project_slug,
                worktree_path=str(repo),
                worktree_id=identity.worktree_id,
            )
            live = dev.command_environment()

            self.assertEqual(live["DEV_DJANGO_PORT"], "8000")
            self.assertEqual(live["DEV_VITE_PORT"], "5173")
            self.assertEqual(live["DEV_BASE_HOST"], "")
            self.assertEqual(live["TERM"], "xterm-256color")


class DoctorTests(unittest.TestCase):
    def test_doctor_reports_disabled_and_missing_verification_commands(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(
                root / "repo",
                config=(
                    'test_command = ["uv", "run", "python", "django-root/manage.py", "test"]\n'
                    'check_command = ["bin/missing-check.sh"]\n'
                ),
            )
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = resolve_identity(repo, config)
            runner = LifecycleRunner()
            environment = {"HOME": str(root / "home")}
            dev = make_dev_environment(runner, repo, config, identity, environment, environment)

            checks = {check.name: check for check in dev.doctor_report().checks}

            self.assertEqual(checks["command:test"].status, "ok")
            self.assertEqual(checks["command:jstest"].status, "warning")
            self.assertIn("not configured", checks["command:jstest"].detail)
            self.assertEqual(checks["command:lint"].status, "warning")
            self.assertEqual(checks["command:check"].status, "error")
            self.assertIn("does not exist", checks["command:check"].detail)

    def test_doctor_reports_when_dropdb_cannot_force_connection_termination(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = resolve_identity(repo, config)
            runner = LifecycleRunner()
            runner.supports_force_drop = False
            environment = {"HOME": str(root / "home")}
            dev = make_dev_environment(runner, repo, config, identity, environment, environment)
            report = dev.doctor_report()

            checks = {check.name: check for check in report.checks}
            self.assertEqual(checks["dropdb:force"].status, "error")
            self.assertEqual(checks["tmux:backend"].status, "ok")
            self.assertIn("socket alliance-dev-v1; 0 managed session(s)", checks["tmux:backend"].detail)
            self.assertFalse(any("start-server" in call.args for call in runner.calls))


class StatusTests(unittest.TestCase):
    def test_missing_expected_window_degrades_managed_session_status(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = resolve_identity(repo, config)
            runner = LifecycleRunner()
            add_managed_session(
                runner,
                identity.session_name,
                project=config.project_slug,
                worktree_path=str(repo),
                worktree_id=identity.worktree_id,
            )
            runner.panes[identity.session_name] = {"django"}
            environment = {"HOME": str(root / "home")}
            dev = make_dev_environment(runner, repo, config, identity, environment, environment)

            records = dev.status_records()

            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].session_state, "degraded")
            self.assertEqual(records[0].readiness, "notReady")
            self.assertEqual(
                tuple(
                    (process.name, process.state, process.required)
                    for process in records[0].processes
                    if process.state != "running"
                ),
                (("vite", "missing", True),),
            )

    def test_default_status_reports_an_absent_current_worktree(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = resolve_identity(repo, config)
            runner = LifecycleRunner()
            dev = make_dev_environment(runner, repo, config, identity, {}, {})

            record = dev.status_records()[0]

            self.assertEqual(record.session_state, "absent")
            self.assertEqual(record.readiness, "notReady")
            self.assertEqual(
                tuple((process.name, process.state) for process in record.processes),
                (("django", "missing"), ("vite", "missing")),
            )

    def test_all_status_does_not_probe_readiness(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = resolve_identity(repo, config)
            runner = LifecycleRunner()
            add_managed_session(
                runner,
                identity.session_name,
                project=config.project_slug,
                worktree_path=str(repo),
                worktree_id=identity.worktree_id,
            )
            runner.panes[identity.session_name] = {"django", "vite", "worker"}
            dev = make_dev_environment(runner, repo, config, identity, {}, {})

            with (
                patch(
                    "alliance_platform.dev.lifecycle.url_ready", side_effect=AssertionError("must not probe")
                ),
                patch(
                    "alliance_platform.dev.lifecycle.vite_ready", side_effect=AssertionError("must not probe")
                ),
            ):
                record = dev.status_records(all_worktrees=True)[0]

            self.assertEqual(record.readiness, "notProbed")
            worker = next(process for process in record.processes if process.name == "worker")
            self.assertIsNone(worker.required)


class DatabaseSessionSafetyTests(unittest.TestCase):
    def make_environment(self, root: Path) -> tuple[DevEnvironment, LifecycleRunner]:
        repo = make_repo(root / "repo")
        config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
        identity = resolve_identity(repo, config)
        runner = LifecycleRunner()
        environment = {"HOME": str(root / "home")}
        primary = make_dev_environment(runner, repo, config, identity, environment, environment)
        return primary, runner

    def test_start_refuses_a_metadata_matched_managed_session(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            primary, runner = self.make_environment(root)
            add_managed_session(
                runner,
                "alternate-managed-session",
                project=primary.config.project_slug,
                worktree_path=str(primary.repo),
                worktree_id=primary.identity.worktree_id,
            )

            with (
                patch.dict(os.environ, {"XDG_CACHE_HOME": str(root / "cache")}),
                self.assertRaisesRegex(DevError, "another dev session is active"),
            ):
                primary.start()

            self.assertFalse(any(call.args[0] in {"createdb", "dropdb"} for call in runner.calls))
            self.assertFalse(any("manage.py" in call.args for call in runner.calls))

    def test_drop_refuses_metadata_matched_managed_session(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            primary, runner = self.make_environment(root)
            add_managed_session(
                runner,
                "alternate-managed-session",
                project=primary.config.project_slug,
                worktree_path=str(primary.repo),
                worktree_id=primary.identity.worktree_id,
            )

            with (
                patch.dict(os.environ, {"XDG_CACHE_HOME": str(root / "cache")}),
                self.assertRaisesRegex(DevError, "alternate-managed-session"),
            ):
                primary.stop(drop_database=True)

            self.assertFalse(any(call.args[0] == "dropdb" for call in runner.calls))

    def test_pending_recovery_refuses_a_metadata_matched_managed_session(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            primary, runner = self.make_environment(root)
            with patch("alliance_platform.dev.lifecycle.port_available", return_value=True):
                state = primary._allocate_state(use_portless=False)
            state.database_setup_pending = True
            primary._save_state(state)
            add_managed_session(
                runner,
                "alternate-managed-session",
                project=primary.config.project_slug,
                worktree_path=str(primary.repo),
                worktree_id=primary.identity.worktree_id,
            )

            with self.assertRaisesRegex(DevError, "another dev session is active"):
                primary._recover_interrupted_database()

            self.assertFalse(any(call.args[0] == "dropdb" for call in runner.calls))

    def test_runtime_view_derives_identity_and_urls_instead_of_persisting_them(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            primary, _runner = self.make_environment(root)
            with patch("alliance_platform.dev.lifecycle.port_available", return_value=True):
                allocated = primary._allocate_state(use_portless=False)
            primary._save_state(allocated)

            persisted = primary.store.load()
            assert persisted is not None
            runtime = primary._runtime_view(persisted)

            self.assertEqual(runtime.worktree_id, primary.identity.worktree_id)
            self.assertEqual(runtime.worktree_path, str(primary.identity.repo))
            self.assertEqual(runtime.session_name, primary.identity.session_name)
            self.assertEqual(runtime.database_name, primary.identity.database_name)
            self.assertEqual(runtime.django_url, f"http://localhost:{persisted.django_port}")
            self.assertEqual(runtime.vite_url, f"http://localhost:{persisted.vite_port}")

    def test_runtime_view_resolves_portless_url_and_host_at_read_time(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            primary, _runner = self.make_environment(root)
            persisted = PersistedState(django_port=0, vite_port=5173, use_portless=True)

            with patch.object(
                primary.portless,
                "resolve_url",
                return_value="https://checkout.demo.test",
            ) as resolve_url:
                runtime = primary._runtime_view(persisted)

            resolve_url.assert_called_once_with()
            self.assertEqual(runtime.django_url, "https://checkout.demo.test")
            self.assertEqual(runtime.dev_base_host, "checkout.demo.test")

    def test_explicit_drop_uses_current_derived_database_identity(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            primary, runner = self.make_environment(root)
            with patch("alliance_platform.dev.lifecycle.port_available", return_value=True):
                state = primary._allocate_state(use_portless=False)
            primary._save_state(state)

            with (
                patch.dict(os.environ, {"XDG_CACHE_HOME": str(root / "cache")}),
                redirect_stdout(io.StringIO()),
            ):
                primary.stop(drop_database=True)

            drops = destructive_drop_calls(runner)
            self.assertEqual(len(drops), 1)
            self.assertEqual(drops[0].args[-1], primary.identity.database_name)
            self.assertIsNone(primary.registry.load())


class EnvironmentRegistryLifecycleTests(unittest.TestCase):
    def make_environment(self, root: Path) -> tuple[DevEnvironment, LifecycleRunner]:
        repo = make_repo(root / "repo")
        config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
        identity = resolve_identity(repo, config)
        runner = LifecycleRunner()
        environment = {"HOME": str(root / "home")}
        return (
            make_dev_environment(runner, repo, config, identity, environment, environment),
            runner,
        )

    def test_environment_inventory_reconciles_registry_with_worktree_and_tmux(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            dev, runner = self.make_environment(root)
            entry = register_environment(dev)

            orphaned = dev.environment_record(entry.worktree_id)
            self.assertEqual(orphaned.state, "orphaned")
            self.assertEqual(orphaned.session_state, "absent")
            self.assertFalse(orphaned.worktree_exists)

            add_managed_session(
                runner,
                entry.session_name,
                project=dev.config.project_slug,
                worktree_path=entry.worktree_path,
                worktree_id=entry.worktree_id,
            )
            runner.panes[entry.session_name] = {"django", "vite"}

            running = dev.environment_record(entry.worktree_id)
            self.assertEqual(running.state, "running-orphaned")
            self.assertEqual(running.session_state, "running")

    def test_incomplete_and_conflicting_environments_are_identified(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            dev, runner = self.make_environment(root)
            entry = register_environment(dev, setup_pending=True)

            self.assertEqual(dev.environment_record(entry.worktree_id).state, "incomplete")

            add_managed_session(
                runner,
                entry.session_name,
                project=dev.config.project_slug,
                worktree_path="/different/worktree",
                worktree_id="different-0123456789",
            )
            self.assertEqual(dev.environment_record(entry.worktree_id).state, "conflict")

    def test_remove_stops_matching_session_and_drops_owned_database(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            dev, runner = self.make_environment(root)
            entry = register_environment(dev)
            add_managed_session(
                runner,
                entry.session_name,
                project=dev.config.project_slug,
                worktree_path=entry.worktree_path,
                worktree_id=entry.worktree_id,
            )
            runner.panes[entry.session_name] = {"django", "vite"}

            result = dev.remove_environment(entry.worktree_id)

            self.assertTrue(result.session_stopped)
            self.assertTrue(result.database_dropped)
            self.assertFalse(result.database_retained)
            self.assertNotIn(entry.session_name, runner.sessions)
            self.assertIsNone(dev.registry.load_project_entry(entry.worktree_id))
            self.assertEqual(destructive_drop_calls(runner)[0].args[-1], entry.database_name)

    def test_remove_forgets_unowned_database_without_dropping_it(self) -> None:
        with TemporaryDirectory() as temporary:
            dev, runner = self.make_environment(Path(temporary))
            entry = register_environment(dev, database_owned=False)

            result = dev.remove_environment(entry.worktree_id)

            self.assertTrue(result.database_retained)
            self.assertTrue(runner.database_exists)
            self.assertEqual(destructive_drop_calls(runner), [])
            self.assertIsNone(dev.registry.load_project_entry(entry.worktree_id))

    def test_failed_database_cleanup_retains_a_retryable_registry_record(self) -> None:
        with TemporaryDirectory() as temporary:
            dev, runner = self.make_environment(Path(temporary))
            entry = register_environment(dev)
            runner.fail_drop = True

            with self.assertRaisesRegex(DevError, "Dropping database.*failed"):
                dev.remove_environment(entry.worktree_id)

            retained = dev.registry.load_project_entry(entry.worktree_id)
            assert retained is not None
            self.assertEqual(retained.last_action, "cleanupPending")
            self.assertTrue(retained.database_owned)
            self.assertTrue(retained.database_present)

    def test_failed_registry_unlink_retains_an_accurate_database_removed_record(self) -> None:
        with TemporaryDirectory() as temporary:
            dev, runner = self.make_environment(Path(temporary))
            entry = register_environment(dev)

            with (
                patch.object(
                    dev.registry,
                    "remove_project_entry",
                    side_effect=DevError("registry unlink failed"),
                ),
                self.assertRaisesRegex(DevError, "registry unlink failed"),
            ):
                dev.remove_environment(entry.worktree_id)

            retained = dev.registry.load_project_entry(entry.worktree_id)
            assert retained is not None
            self.assertEqual(retained.last_action, "databaseRemoved")
            self.assertFalse(retained.database_present)
            self.assertFalse(runner.database_exists)

    def test_remove_refuses_a_tmux_session_with_mismatched_metadata(self) -> None:
        with TemporaryDirectory() as temporary:
            dev, runner = self.make_environment(Path(temporary))
            entry = register_environment(dev)
            add_managed_session(
                runner,
                entry.session_name,
                project=dev.config.project_slug,
                worktree_path="/different/worktree",
                worktree_id="different-0123456789",
            )

            with self.assertRaisesRegex(DevError, "metadata does not match"):
                dev.remove_environment(entry.worktree_id)

            self.assertIn(entry.session_name, runner.sessions)
            self.assertEqual(destructive_drop_calls(runner), [])
            self.assertIsNotNone(dev.registry.load_project_entry(entry.worktree_id))


class PublicLifecycleTests(unittest.TestCase):
    def test_invalid_state_is_rejected_before_starting_tmux_or_preparing_database(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = resolve_identity(repo, config)
            runner = LifecycleRunner()
            dev = make_dev_environment(runner, repo, config, identity, {}, {})
            dev.store.ensure()
            dev.store.state_path.write_text('{"version": 1}\n')

            with (
                patch.dict(os.environ, {"XDG_CACHE_HOME": str(root / "cache")}),
                self.assertRaisesRegex(DevError, "unsupported schema version 1"),
            ):
                dev.start()

            self.assertEqual(runner.calls, [])

    def test_required_portless_fails_before_database_preparation_or_allocation(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo", config='portless = "required"\n')
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = resolve_identity(repo, config)
            runner = LifecycleRunner()
            environment = {"HOME": str(root / "home")}
            dev = make_dev_environment(runner, repo, config, identity, environment, environment)

            with (
                patch.dict(os.environ, {"XDG_CACHE_HOME": str(root / "cache")}),
                redirect_stdout(io.StringIO()),
                self.assertRaisesRegex(DevError, "Portless is required.*not installed"),
            ):
                dev.start()

            self.assertIsNone(dev.store.load())
            self.assertIsNone(dev.registry.load())
            self.assertNotIn(identity.session_name, runner.sessions)
            self.assertEqual(destructive_drop_calls(runner), [])
            self.assertFalse(any("migrate" in call.args for call in runner.calls))

    def test_public_lifecycle_allocates_a_unique_pair_and_reuses_it_after_stop(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(
                root / "repo",
                config="django_port_base = 8000\nvite_port_base = 8000\n",
            )
            (repo / "node_modules").mkdir()
            (repo / ".yarn").mkdir()
            (repo / ".yarn" / "install-state.gz").write_bytes(b"installed")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = resolve_identity(repo, config)
            runner = LifecycleRunner()
            environment = {"HOME": str(root / "home")}
            dev = make_dev_environment(runner, repo, config, identity, environment, environment)
            progress: list[str] = []

            patches = (
                patch.dict(os.environ, {"XDG_CACHE_HOME": str(root / "cache")}),
                patch("alliance_platform.dev.lifecycle.port_available", return_value=True),
                patch("alliance_platform.dev.lifecycle.vite_ready", return_value=True),
                patch("alliance_platform.dev.lifecycle.url_ready", return_value=True),
                patch("alliance_platform.dev.tmux.time.sleep", return_value=None),
            )
            with (
                patches[0],
                patches[1],
                patches[2],
                patches[3],
                patches[4],
                redirect_stdout(io.StringIO()),
            ):
                dev.start(on_progress=progress.append)
                first = dev.store.load()
                assert first is not None
                live = dev.live_environment()
                self.assertEqual(live.session_name, identity.session_name)
                self.assertEqual(live.database_name, identity.database_name)
                self.assertEqual(live.django_url, "http://localhost:8000")
                runner.pane_output[f"{identity.session_name}:django"] = "first run output\n"
                live_output = dev.log_records("django", lines=1)
                self.assertEqual(live_output[0].output, "first run output")
                dev.stop()
                stopped = dev.store.load()
                assert stopped is not None
                self.assertEqual(
                    dev.store.snapshot_path("django").read_text(),
                    "first run output\n",
                )
                saved_output = dev.log_records("django", lines=1)
                self.assertEqual(saved_output[0].output, "first run output")
                dev.start()
                restarted = dev.store.load()

            assert restarted is not None
            registry_entry = dev.registry.load()
            assert registry_entry is not None
            self.assertEqual((first.django_port, first.vite_port), (8000, 8001))
            self.assertEqual((restarted.django_port, restarted.vite_port), (8000, 8001))
            self.assertEqual(len(progress), 2)
            self.assertEqual(progress[0], "Running Django migrations...")
            self.assertTrue(progress[1].startswith("Django migrations complete ("))
            self.assertEqual(registry_entry.last_action, "running")
            self.assertTrue(registry_entry.database_present)
            self.assertEqual((registry_entry.django_port, registry_entry.vite_port), (8000, 8001))
            self.assertEqual(runner.panes[identity.session_name], {"django", "vite"})
            self.assertEqual(dev.store.snapshot_path("django").read_text(), "first run output\n")
            manage_calls = [
                call.args for call in runner.calls if call.args[0] == "uv" and "manage.py" in call.args
            ]
            self.assertEqual(
                manage_calls,
                [
                    ("uv", "run", "python", "manage.py", "migrate", "--noinput"),
                    ("uv", "run", "python", "manage.py", "migrate", "--noinput"),
                ],
            )

    def test_restart_all_revalidates_ports_without_preparing_dependencies_or_database(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(
                root / "repo",
                config="django_port_base = 8000\nvite_port_base = 8000\n",
            )
            (repo / "node_modules").mkdir()
            (repo / ".yarn").mkdir()
            (repo / ".yarn" / "install-state.gz").write_bytes(b"installed")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = resolve_identity(repo, config)
            runner = LifecycleRunner()
            environment = {"HOME": str(root / "home")}
            dev = make_dev_environment(runner, repo, config, identity, environment, environment)
            unavailable: set[int] = set()

            with (
                patch.dict(os.environ, {"XDG_CACHE_HOME": str(root / "cache")}),
                patch(
                    "alliance_platform.dev.lifecycle.port_available",
                    side_effect=lambda port: port not in unavailable,
                ),
                patch("alliance_platform.dev.lifecycle.vite_ready", return_value=True),
                patch("alliance_platform.dev.lifecycle.url_ready", return_value=True),
                patch("alliance_platform.dev.tmux.time.sleep", return_value=None),
                patch(
                    "alliance_platform.dev.lifecycle.allocation_lock", side_effect=allocation_lock
                ) as acquire_lock,
            ):
                start_result = dev.start()
                started = dev.store.load()
                assert started is not None
                call_boundary = len(runner.calls)
                unavailable.update({started.django_port, started.vite_port})

                restart_result = dev.restart()

            restarted = dev.store.load()
            assert restarted is not None
            restart_calls = runner.calls[call_boundary:]
            self.assertFalse(start_result.already_running)
            self.assertEqual(restart_result.environment.django_url, "http://localhost:8002")
            self.assertEqual((restarted.django_port, restarted.vite_port), (8002, 8003))
            self.assertEqual(acquire_lock.call_count, 2)
            self.assertFalse(
                any(call.args[0] in {"psql", "createdb", "dropdb", "yarn"} for call in restart_calls)
            )
            self.assertFalse(any(call.args[0] == "uv" and "manage.py" in call.args for call in restart_calls))
            self.assertEqual(runner.panes[identity.session_name], {"django", "vite"})

    def test_normal_stop_never_acquires_the_machine_allocation_lock(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = resolve_identity(repo, config)
            runner = LifecycleRunner()
            add_managed_session(
                runner,
                identity.session_name,
                project=config.project_slug,
                worktree_path=str(repo),
                worktree_id=identity.worktree_id,
            )
            runner.panes[identity.session_name] = {"django", "vite"}
            dev = make_dev_environment(runner, repo, config, identity, {}, {})
            dev.store.save(persisted_state())

            with (
                patch.dict(os.environ, {"XDG_CACHE_HOME": str(root / "cache")}),
                patch("alliance_platform.dev.tmux.time.sleep", return_value=None),
                patch(
                    "alliance_platform.dev.lifecycle.allocation_lock",
                    side_effect=AssertionError("stop must not acquire allocation lock"),
                ),
            ):
                result = dev.stop()

            self.assertTrue(result.was_running)

    def test_no_op_stop_does_not_create_a_registry_record(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = resolve_identity(repo, config)
            runner = LifecycleRunner()
            dev = make_dev_environment(runner, repo, config, identity, {}, {})

            with patch.dict(os.environ, {"XDG_CACHE_HOME": str(root / "cache")}):
                result = dev.stop()

            self.assertFalse(result.was_running)
            self.assertIsNone(dev.registry.load())

    def test_failed_restart_all_stops_partial_replacement_without_touching_database(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = resolve_identity(repo, config)
            runner = LifecycleRunner()
            add_managed_session(
                runner,
                identity.session_name,
                project=config.project_slug,
                worktree_path=str(repo),
                worktree_id=identity.worktree_id,
            )
            runner.panes[identity.session_name] = {"django", "vite"}
            runner.fail_new_window = True
            dev = make_dev_environment(runner, repo, config, identity, {}, {})
            dev.store.save(persisted_state())

            with (
                patch.dict(os.environ, {"XDG_CACHE_HOME": str(root / "cache")}),
                patch("alliance_platform.dev.lifecycle.port_available", return_value=True),
                patch("alliance_platform.dev.tmux.time.sleep", return_value=None),
                self.assertRaisesRegex(DevError, "Starting django failed"),
            ):
                dev.restart()

            state = dev.store.load()
            assert state is not None
            self.assertFalse(state.database_setup_pending)
            self.assertNotIn(identity.session_name, runner.sessions)
            self.assertFalse(any(call.args[0] in {"psql", "createdb", "dropdb"} for call in runner.calls))
            self.assertFalse(any(call.args[0] == "uv" and "manage.py" in call.args for call in runner.calls))

    def test_interrupted_first_migration_drops_the_owned_database_and_clears_marker(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo")
            (repo / "node_modules").mkdir()
            (repo / ".yarn").mkdir()
            (repo / ".yarn" / "install-state.gz").write_bytes(b"installed")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = resolve_identity(repo, config)
            runner = LifecycleRunner()
            runner.database_exists = False
            runner.interrupt_on_migrate = True
            environment = {"HOME": str(root / "home")}
            dev = make_dev_environment(runner, repo, config, identity, environment, environment)

            with (
                patch.dict(os.environ, {"XDG_CACHE_HOME": str(root / "cache")}),
                patch("alliance_platform.dev.lifecycle.port_available", return_value=True),
                patch("alliance_platform.dev.tmux.time.sleep", return_value=None),
                redirect_stdout(io.StringIO()),
                self.assertRaises(KeyboardInterrupt),
            ):
                dev.start()

            self.assertIsNone(dev.store.load())
            self.assertIsNone(dev.registry.load())
            self.assertFalse(runner.database_exists)
            self.assertNotIn(identity.session_name, runner.sessions)
            self.assertEqual(len(destructive_drop_calls(runner)), 1)

    def test_startup_failure_saves_dead_pane_output_before_cleanup(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo")
            (repo / "node_modules").mkdir()
            (repo / ".yarn").mkdir()
            (repo / ".yarn" / "install-state.gz").write_bytes(b"installed")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = resolve_identity(repo, config)
            runner = LifecycleRunner()
            runner.database_exists = True
            runner.failed_pane = "django"
            runner.pane_output[f"{identity.session_name}:django"] = "django boot failed\n"
            environment = {"HOME": str(root / "home")}
            dev = make_dev_environment(runner, repo, config, identity, environment, environment)

            with (
                patch.dict(os.environ, {"XDG_CACHE_HOME": str(root / "cache")}),
                patch("alliance_platform.dev.lifecycle.port_available", return_value=True),
                patch("alliance_platform.dev.tmux.time.sleep", return_value=None),
                redirect_stdout(io.StringIO()),
                self.assertRaisesRegex(DevError, "django.*exit 23"),
            ):
                dev.start()

            self.assertNotIn(identity.session_name, runner.sessions)
            self.assertEqual(
                dev.store.snapshot_path("django").read_text(),
                "django boot failed\n",
            )
            output = dev.log_records("django")
            self.assertEqual(output[0].output, "django boot failed")

    def test_uncertain_createdb_result_recovers_using_the_persisted_marker(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo")
            (repo / "node_modules").mkdir()
            (repo / ".yarn").mkdir()
            (repo / ".yarn" / "install-state.gz").write_bytes(b"installed")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = resolve_identity(repo, config)
            runner = LifecycleRunner()
            runner.database_exists = False
            runner.fail_createdb_uncertain = True
            environment = {"HOME": str(root / "home")}
            dev = make_dev_environment(runner, repo, config, identity, environment, environment)
            pending_at_createdb: list[bool] = []

            def observe_createdb() -> None:
                state = dev.store.load()
                pending_at_createdb.append(state is not None and state.database_setup_pending)

            runner.createdb_observer = observe_createdb
            with (
                patch.dict(os.environ, {"XDG_CACHE_HOME": str(root / "cache")}),
                patch("alliance_platform.dev.lifecycle.port_available", return_value=True),
                patch("alliance_platform.dev.tmux.time.sleep", return_value=None),
                redirect_stdout(io.StringIO()),
                self.assertRaisesRegex(DevError, "Creating database.*failed"),
            ):
                dev.start()

            self.assertEqual(pending_at_createdb, [True])
            self.assertIsNone(dev.store.load())
            self.assertFalse(runner.database_exists)
            self.assertEqual(len(destructive_drop_calls(runner)), 1)

    def test_migration_failure_against_existing_database_never_drops_it(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo")
            (repo / "node_modules").mkdir()
            (repo / ".yarn").mkdir()
            (repo / ".yarn" / "install-state.gz").write_bytes(b"installed")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = resolve_identity(repo, config)
            runner = LifecycleRunner()
            runner.database_exists = True
            runner.fail_migrate = True
            environment = {"HOME": str(root / "home")}
            dev = make_dev_environment(runner, repo, config, identity, environment, environment)

            with (
                patch.dict(os.environ, {"XDG_CACHE_HOME": str(root / "cache")}),
                patch("alliance_platform.dev.lifecycle.port_available", return_value=True),
                patch("alliance_platform.dev.tmux.time.sleep", return_value=None),
                redirect_stdout(io.StringIO()),
                self.assertRaisesRegex(DevError, "Django migrations failed"),
            ):
                dev.start()

            self.assertIsNone(dev.store.load())
            self.assertTrue(runner.database_exists)
            self.assertEqual(destructive_drop_calls(runner), [])

    def test_failure_after_successful_preparation_uses_the_explicit_creation_result(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo")
            (repo / "node_modules").mkdir()
            (repo / ".yarn").mkdir()
            (repo / ".yarn" / "install-state.gz").write_bytes(b"installed")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = resolve_identity(repo, config)
            runner = LifecycleRunner()
            runner.database_exists = False
            runner.fail_new_window = True
            environment = {"HOME": str(root / "home")}
            dev = make_dev_environment(runner, repo, config, identity, environment, environment)

            with (
                patch.dict(os.environ, {"XDG_CACHE_HOME": str(root / "cache")}),
                patch("alliance_platform.dev.lifecycle.port_available", return_value=True),
                patch("alliance_platform.dev.tmux.time.sleep", return_value=None),
                redirect_stdout(io.StringIO()),
                self.assertRaisesRegex(DevError, "Starting django failed"),
            ):
                dev.start()

            state = dev.store.load()
            assert state is not None
            self.assertFalse(state.database_setup_pending)
            self.assertFalse(runner.database_exists)
            self.assertEqual(len(destructive_drop_calls(runner)), 1)

    def test_failed_cleanup_repersists_ownership_for_next_invocation_recovery(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo")
            (repo / "node_modules").mkdir()
            (repo / ".yarn").mkdir()
            (repo / ".yarn" / "install-state.gz").write_bytes(b"installed")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = resolve_identity(repo, config)
            runner = LifecycleRunner()
            runner.database_exists = False
            runner.fail_new_window = True
            runner.fail_drop = True
            environment = {"HOME": str(root / "home")}
            dev = make_dev_environment(runner, repo, config, identity, environment, environment)

            with (
                patch.dict(os.environ, {"XDG_CACHE_HOME": str(root / "cache")}),
                patch("alliance_platform.dev.lifecycle.port_available", return_value=True),
                patch("alliance_platform.dev.tmux.time.sleep", return_value=None),
                redirect_stderr(io.StringIO()),
                redirect_stdout(io.StringIO()),
                self.assertRaisesRegex(DevError, "Starting django failed"),
            ):
                dev.start()

            failed = dev.store.load()
            registry_entry = dev.registry.load()
            assert failed is not None
            assert registry_entry is not None
            self.assertTrue(failed.database_setup_pending)
            self.assertTrue(registry_entry.database_owned)
            self.assertTrue(registry_entry.database_setup_pending)
            self.assertTrue(runner.database_exists)

            runner.fail_drop = False
            runner.fail_new_window = False
            with redirect_stdout(io.StringIO()):
                dev._recover_interrupted_database()

            recovered = dev.store.load()
            assert recovered is not None
            self.assertFalse(recovered.database_setup_pending)
            self.assertIsNone(dev.registry.load())
            self.assertFalse(runner.database_exists)

    def test_next_start_recovers_a_persisted_incomplete_database_marker(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo")
            (repo / "node_modules").mkdir()
            (repo / ".yarn").mkdir()
            (repo / ".yarn" / "install-state.gz").write_bytes(b"installed")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = resolve_identity(repo, config)
            runner = LifecycleRunner()
            environment = {"HOME": str(root / "home")}
            dev = make_dev_environment(runner, repo, config, identity, environment, environment)
            with patch("alliance_platform.dev.lifecycle.port_available", return_value=True):
                interrupted = dev._allocate_state(use_portless=False)
            interrupted.database_setup_pending = True
            dev._save_state(interrupted)

            with (
                patch.dict(os.environ, {"XDG_CACHE_HOME": str(root / "cache")}),
                patch("alliance_platform.dev.lifecycle.port_available", return_value=True),
                patch("alliance_platform.dev.lifecycle.vite_ready", return_value=True),
                patch("alliance_platform.dev.lifecycle.url_ready", return_value=True),
                patch("alliance_platform.dev.tmux.time.sleep", return_value=None),
                redirect_stdout(io.StringIO()),
            ):
                dev.start()

            recovered = dev.store.load()
            assert recovered is not None
            self.assertFalse(recovered.database_setup_pending)
            self.assertEqual(runner.panes[identity.session_name], {"django", "vite"})
            commands = [call.args for call in runner.calls]
            self.assertEqual(len(destructive_drop_calls(runner)), 1)
            self.assertTrue(any(command[0] == "createdb" for command in commands))
            self.assertTrue(any("createdevdata" in command for command in commands))


if __name__ == "__main__":
    unittest.main()
