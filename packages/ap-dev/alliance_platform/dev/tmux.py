from __future__ import annotations

import os
from pathlib import Path
import signal
import time

from . import TMUX_PROTOCOL_VERSION
from .errors import DevError
from .models import ManagedSession
from .models import ProcessSpec
from .models import ProcessStatus
from .runner import CommandResult
from .runner import Runner
from .runner import require_success

TMUX_SOCKET_NAME = "alliance-dev-v1"
TMUX_EXCLUDED_ENVIRONMENT = {"TERM", "TMUX", "TMUX_PANE", "TMUX_TMPDIR"}
TMUX_METADATA_KEYS = {
    "DEV_PROJECT",
    "DEV_WORKTREE",
    "DEV_WORKTREE_ID",
    "DEV_DJANGO_PORT",
    "DEV_VITE_PORT",
    "DEV_PROTOCOL_VERSION",
}


def _normalise_signal(value: str) -> str | None:
    if not value:
        return None
    if not value.isdigit():
        return value
    try:
        name = signal.Signals(int(value)).name
    except ValueError:
        return value
    return name.removeprefix("SIG").lower()


class TmuxClient:
    """Narrow client for the dedicated Alliance dev tmux server."""

    def __init__(
        self,
        runner: Runner,
        repo: Path,
        environment: dict[str, str],
        *,
        socket_name: str = TMUX_SOCKET_NAME,
    ) -> None:
        self.runner = runner
        self.repo = repo
        self.environment = dict(environment)
        self.socket_name = socket_name
        self._executable: str | None = None
        self._resolved = False

    def _resolve(self, *, required: bool) -> str | None:
        if not self._resolved:
            self._executable = self.runner.which("tmux", self.environment)
            self._resolved = True
        if self._executable is None and required:
            raise DevError("Missing 'tmux'. Install it with: brew install tmux")
        return self._executable

    @staticmethod
    def _server_environment(environment: dict[str, str]) -> dict[str, str]:
        result: dict[str, str] = {}
        fixed = {"HOME", "LOGNAME", "PATH", "SHELL", "TMPDIR", "USER", "XDG_RUNTIME_DIR"}
        for key, value in environment.items():
            if key in fixed or key == "LANG" or key.startswith("LC_"):
                result[key] = value
        return result

    def _command(self, *args: str, required: bool = True) -> list[str] | None:
        executable = self._resolve(required=required)
        if executable is None:
            return None
        return [executable, "-L", self.socket_name, "-f", "/dev/null", *args]

    def _run(
        self,
        *args: str,
        required: bool = True,
        cwd: Path | None = None,
    ) -> CommandResult | None:
        command = self._command(*args, required=required)
        if command is None:
            return None
        return self.runner.run(
            command,
            cwd=cwd,
            env=self._server_environment(self.environment),
            capture=True,
        )

    def ensure_server(self) -> None:
        result = self._run(
            "start-server",
            ";",
            "set-option",
            "-g",
            "exit-empty",
            "off",
            ";",
            "set-option",
            "-g",
            "remain-on-exit",
            "on",
            ";",
            "set-option",
            "-g",
            "history-limit",
            "5000",
            ";",
            "set-option",
            "-g",
            "update-environment",
            "",
        )
        assert result is not None
        require_success(result, "Starting the dedicated tmux server")

    def session_exists(self, session: str) -> bool:
        result = self._run("has-session", "-t", session, required=False)
        return result is not None and result.returncode == 0

    @staticmethod
    def _environment_args(
        environment: dict[str, str],
        metadata: dict[str, str],
    ) -> list[str]:
        unknown_metadata = set(metadata) - TMUX_METADATA_KEYS
        if unknown_metadata:
            raise DevError(f"Unknown tmux metadata: {', '.join(sorted(unknown_metadata))}")
        missing_metadata = TMUX_METADATA_KEYS - set(metadata)
        if missing_metadata:
            raise DevError(f"Missing tmux metadata: {', '.join(sorted(missing_metadata))}")
        if metadata["DEV_PROTOCOL_VERSION"] != str(TMUX_PROTOCOL_VERSION):
            raise DevError(
                "Invalid tmux metadata protocol: "
                f"{metadata['DEV_PROTOCOL_VERSION']!r}; expected {TMUX_PROTOCOL_VERSION}"
            )
        combined = {**environment, **metadata}
        args: list[str] = []
        for key, value in sorted(combined.items()):
            if key in TMUX_EXCLUDED_ENVIRONMENT:
                continue
            if not key or "\x00" in key or "=" in key or "\x00" in value:
                raise DevError(f"Invalid tmux environment variable {key!r}")
            args.extend(["-e", f"{key}={value}"])
        return args

    def start_session(
        self,
        session: str,
        processes: tuple[ProcessSpec, ...],
        environment: dict[str, str],
        metadata: dict[str, str],
    ) -> None:
        if not processes:
            raise DevError("At least one dev process is required")
        for process in processes:
            if not process.argv:
                raise DevError(f"Process {process.name} has no command")
        first, *remaining = processes
        environment_args = self._environment_args(environment, metadata)
        self.ensure_server()
        if self.session_exists(session):
            raise DevError(f"tmux session already exists: {session}")
        result = self._run(
            "new-session",
            "-d",
            "-E",
            "-s",
            session,
            "-n",
            first.name,
            "-c",
            str(first.cwd),
            *environment_args,
            "--",
            *first.argv,
            cwd=self.repo,
        )
        assert result is not None
        require_success(result, f"Starting {first.name}")
        try:
            for process in remaining:
                result = self._run(
                    "new-window",
                    "-d",
                    "-t",
                    session,
                    "-n",
                    process.name,
                    "-c",
                    str(process.cwd),
                    "--",
                    *process.argv,
                )
                assert result is not None
                require_success(result, f"Starting {process.name}")
        except BaseException:
            self.stop_session(session)
            raise

    def stop_session(self, session: str) -> None:
        if not self.session_exists(session):
            return
        statuses = self.process_statuses(session)
        for name, status in statuses.items():
            if status.alive:
                self._run("send-keys", "-t", f"{session}:{name}", "C-c")
        if any(status.alive for status in statuses.values()):
            time.sleep(1.0)
        result = self._run("kill-session", "-t", session)
        assert result is not None
        require_success(result, f"Stopping tmux session {session}")

    def restart_process(self, session: str, name: str) -> None:
        result = self._run("respawn-window", "-k", "-t", f"{session}:{name}")
        assert result is not None
        require_success(result, f"Restarting {name}")

    def process_statuses(self, session: str) -> dict[str, ProcessStatus]:
        result = self._run(
            "list-panes",
            "-s",
            "-t",
            session,
            "-F",
            "#{window_name}\t#{pane_dead}\t#{pane_dead_status}\t#{pane_dead_signal}",
            required=False,
        )
        if result is None or result.returncode != 0:
            return {}
        statuses: dict[str, ProcessStatus] = {}
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) != 4:
                continue
            exit_code = int(parts[2]) if parts[2].isdigit() else None
            statuses[parts[0]] = ProcessStatus(
                name=parts[0],
                alive=parts[1] != "1",
                exit_code=exit_code,
                signal=_normalise_signal(parts[3]),
            )
        return statuses

    def capture_output(self, session: str, name: str, *, lines: int = 200) -> str:
        if lines <= 0:
            raise DevError("Log line count must be positive")
        result = self._run(
            "capture-pane",
            "-p",
            "-J",
            "-S",
            f"-{lines}",
            "-t",
            f"{session}:{name}",
        )
        assert result is not None
        require_success(result, f"Capturing {name} output")
        return result.stdout.rstrip()

    def _session_environment(self, session: str, key: str) -> str:
        result = self._run("show-environment", "-t", session, key, required=False)
        if result is None or result.returncode != 0:
            return ""
        line = result.stdout.rstrip("\n")
        return line[len(key) + 1 :] if line.startswith(f"{key}=") else ""

    def list_managed_sessions(self) -> list[ManagedSession]:
        result = self._run(
            "list-sessions",
            "-F",
            "#{session_name}",
            required=False,
        )
        if result is None or result.returncode != 0:
            return []
        records: list[ManagedSession] = []
        for session in (line for line in result.stdout.splitlines() if line):
            project = self._session_environment(session, "DEV_PROJECT")
            worktree_path = self._session_environment(session, "DEV_WORKTREE")
            worktree_id = self._session_environment(session, "DEV_WORKTREE_ID")
            protocol = self._session_environment(session, "DEV_PROTOCOL_VERSION")
            if not project or not worktree_path or not worktree_id or protocol != str(TMUX_PROTOCOL_VERSION):
                continue
            django_port = self._session_environment(session, "DEV_DJANGO_PORT")
            vite_port = self._session_environment(session, "DEV_VITE_PORT")
            records.append(
                ManagedSession(
                    name=session,
                    project_slug=project,
                    worktree_path=worktree_path,
                    worktree_id=worktree_id,
                    django_port=int(django_port) if django_port.isdigit() else 0,
                    vite_port=int(vite_port) if vite_port.isdigit() else 0,
                )
            )
        return records

    def _attach_environment(self) -> dict[str, str]:
        result = self._server_environment(self.environment)
        for key, value in os.environ.items():
            if key == "TERM" or key == "COLORTERM" or key == "LANG" or key.startswith("LC_"):
                result[key] = value
        for key in TMUX_EXCLUDED_ENVIRONMENT:
            result.pop(key, None)
        return result

    def attach(self, session: str, name: str | None = None) -> None:
        target = f"{session}:{name}" if name else session
        command = self._command("attach-session", "-E", "-t", target)
        assert command is not None
        os.execvpe(command[0], command, self._attach_environment())
