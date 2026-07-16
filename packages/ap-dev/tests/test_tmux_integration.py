from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest
from uuid import uuid4

from alliance_platform.dev.models import ProcessSpec
from alliance_platform.dev.runner import SubprocessRunner
from alliance_platform.dev.tmux import TmuxClient


@unittest.skipUnless(shutil.which("tmux"), "tmux is not installed")
class TmuxIntegrationTests(unittest.TestCase):
    """Exercise the production backend against disposable tmux servers."""

    def setUp(self) -> None:
        self.socket_names: list[str] = []
        self.temporary_directory = TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.environment = {
            **os.environ,
            "CONTROL_ONLY": "must-not-leak",
            "TERM": "poison-control-term",
            "TMUX": "poison-control-tmux",
        }
        self.client = self._new_client()
        self.client.ensure_server()

    def _new_client(self) -> TmuxClient:
        socket_name = f"alliance-dev-test-{uuid4().hex}"
        self.socket_names.append(socket_name)
        return TmuxClient(
            SubprocessRunner(),
            self.root,
            self.environment,
            socket_name=socket_name,
        )

    def tearDown(self) -> None:
        executable = shutil.which("tmux") or "tmux"
        environment = os.environ.copy()
        for key in ("TMUX", "TMUX_PANE", "TMUX_TMPDIR"):
            environment.pop(key, None)
        for socket_name in self.socket_names:
            subprocess.run(
                [executable, "-L", socket_name, "-f", "/dev/null", "kill-server"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
                env=environment,
            )

    def _metadata(
        self,
        session: str,
        *,
        django_port: int = 8000,
        vite_port: int = 5173,
    ) -> dict[str, str]:
        return {
            "DEV_PROJECT": "tmux-integration",
            "DEV_WORKTREE": str(self.root),
            "DEV_WORKTREE_ID": f"{session[:20]}-0123456789",
            "DEV_DJANGO_PORT": str(django_port),
            "DEV_VITE_PORT": str(vite_port),
            "DEV_PROTOCOL_VERSION": "1",
        }

    def _start(
        self,
        *command: str,
        client: TmuxClient | None = None,
        session: str | None = None,
        name: str = "process",
        environment: dict[str, str] | None = None,
        django_port: int = 8000,
        vite_port: int = 5173,
    ) -> tuple[TmuxClient, str]:
        selected_client = client or self.client
        selected_session = session or f"session-{uuid4().hex}"
        selected_client.start_session(
            selected_session,
            (ProcessSpec(name, tuple(command), self.root),),
            environment or {"PATH": os.environ.get("PATH", "")},
            self._metadata(
                selected_session,
                django_port=django_port,
                vite_port=vite_port,
            ),
        )
        return selected_client, selected_session

    def _wait_for_death(
        self,
        client: TmuxClient,
        session: str,
        *,
        name: str = "process",
    ):
        deadline = time.monotonic() + 5
        status = client.process_statuses(session).get(name)
        while (status is None or status.alive) and time.monotonic() < deadline:
            time.sleep(0.02)
            status = client.process_statuses(session).get(name)
        self.assertIsNotNone(status, f"pane {session}:{name} disappeared")
        assert status is not None
        self.assertFalse(status.alive, f"pane {session}:{name} did not exit")
        return status

    def _wait_for_lines(self, path: Path, count: int) -> list[str]:
        deadline = time.monotonic() + 5
        lines: list[str] = []
        while time.monotonic() < deadline:
            if path.exists():
                lines = path.read_text().splitlines()
                if len(lines) >= count:
                    return lines
            time.sleep(0.02)
        self.fail(f"{path} did not contain {count} lines; found {lines!r}")

    def test_server_options_are_set_before_process_launch(self) -> None:
        executable = shutil.which("tmux") or "tmux"
        prefix = [
            executable,
            "-L",
            self.client.socket_name,
            "-f",
            "/dev/null",
            "show-options",
            "-g",
        ]
        environment = self.client._server_environment(self.environment)

        exit_empty = subprocess.run(
            [*prefix, "exit-empty"],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        ).stdout
        remain = subprocess.run(
            [*prefix, "remain-on-exit"],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        ).stdout
        history = subprocess.run(
            [*prefix, "history-limit"],
            check=True,
            capture_output=True,
            text=True,
            env=environment,
        ).stdout

        self.assertIn("exit-empty off", exit_empty)
        self.assertIn("remain-on-exit on", remain)
        self.assertIn("history-limit 5000", history)

    def test_direct_argv_treats_hostile_values_as_data(self) -> None:
        result_path = self.root / "argv.json"
        sentinel = self.root / "shell-expanded"
        hostile = [
            "argument with spaces",
            f"; touch {sentinel}",
            f"$(touch {sentinel})",
            "quote'\"value",
            "",
        ]
        script = "import json, pathlib, sys; pathlib.Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]))"

        client, session = self._start(
            sys.executable,
            "-c",
            script,
            str(result_path),
            *hostile,
        )
        self._wait_for_death(client, session)

        self.assertEqual(json.loads(result_path.read_text()), hostile)
        self.assertFalse(sentinel.exists())

    def test_immediate_exit_metadata_when_available_and_dead_output_are_retained(self) -> None:
        marker = f"captured-after-death-{uuid4().hex}"
        client, exited = self._start(
            sys.executable,
            "-c",
            f"print({marker!r}, flush=True); raise SystemExit(23)",
        )
        exit_status = self._wait_for_death(client, exited)

        if exit_status.exit_code is not None:
            self.assertEqual(exit_status.exit_code, 23)
        self.assertIsNone(exit_status.signal)
        self.assertIn(marker, client.capture_output(exited, "process"))

        client, signalled = self._start(
            sys.executable,
            "-c",
            "import os, signal; os.kill(os.getpid(), signal.SIGTERM)",
        )
        signal_status = self._wait_for_death(client, signalled)

        self.assertIsNone(signal_status.exit_code)
        if signal_status.signal is not None:
            self.assertEqual(signal_status.signal, "term")

    def test_bare_respawn_reuses_original_argv(self) -> None:
        result_path = self.root / "respawn.jsonl"
        original_argv = ["argument with spaces", "; shell data", "$(still data)", "quote'\"value"]
        script = (
            "import json, pathlib, sys; "
            "path = pathlib.Path(sys.argv[1]); "
            "handle = path.open('a'); "
            "handle.write(json.dumps(sys.argv[2:]) + '\\n'); "
            "handle.close()"
        )
        client, session = self._start(
            sys.executable,
            "-c",
            script,
            str(result_path),
            *original_argv,
        )
        self._wait_for_lines(result_path, 1)
        self._wait_for_death(client, session)

        client.restart_process(session, "process")

        lines = self._wait_for_lines(result_path, 2)
        self._wait_for_death(client, session)
        self.assertEqual([json.loads(line) for line in lines], [original_argv, original_argv])

    def test_session_environment_is_exact_and_does_not_leak(self) -> None:
        first_path = self.root / "first-env.json"
        second_path = self.root / "second-env.json"
        script = (
            "import json, os, pathlib, sys; "
            "keys = ('LEAK_ONLY', 'CONTROL_ONLY', 'TERM', 'TMUX'); "
            "pathlib.Path(sys.argv[1]).write_text(json.dumps({key: os.environ.get(key) for key in keys}))"
        )

        client, first = self._start(
            sys.executable,
            "-c",
            script,
            str(first_path),
            environment={
                "PATH": os.environ.get("PATH", ""),
                "LEAK_ONLY": "first-session-only",
                "TERM": "poison-process-term",
                "TMUX": "poison-process-tmux",
            },
        )
        self._wait_for_death(client, first)
        client, second = self._start(
            sys.executable,
            "-c",
            script,
            str(second_path),
            environment={"PATH": os.environ.get("PATH", "")},
        )
        self._wait_for_death(client, second)

        first_values = json.loads(first_path.read_text())
        second_values = json.loads(second_path.read_text())
        self.assertEqual(first_values["LEAK_ONLY"], "first-session-only")
        self.assertIsNone(second_values["LEAK_ONLY"])
        self.assertIsNone(first_values["CONTROL_ONLY"])
        self.assertIsNone(second_values["CONTROL_ONLY"])
        for values in (first_values, second_values):
            self.assertNotIn(values["TERM"], {"poison-control-term", "poison-process-term"})
            self.assertNotIn(values["TMUX"], {"poison-control-tmux", "poison-process-tmux"})

    def test_managed_metadata_and_session_stop_are_isolated(self) -> None:
        client, first = self._start(
            sys.executable,
            "-c",
            "raise SystemExit(0)",
            django_port=8100,
            vite_port=5100,
        )
        client, second = self._start(
            sys.executable,
            "-c",
            "import time; time.sleep(30)",
            django_port=8101,
            vite_port=5101,
        )
        self._wait_for_death(client, first)

        records = {record.name: record for record in client.list_managed_sessions()}
        self.assertEqual(records[first].django_port, 8100)
        self.assertEqual(records[second].vite_port, 5101)

        client.stop_session(first)

        self.assertFalse(client.session_exists(first))
        self.assertTrue(client.session_exists(second))

    def test_dedicated_socket_isolation_allows_the_same_session_name(self) -> None:
        other = self._new_client()
        other.ensure_server()
        shared_name = f"same-name-{uuid4().hex}"
        self._start(
            sys.executable,
            "-c",
            "raise SystemExit(0)",
            client=self.client,
            session=shared_name,
        )
        self._start(
            sys.executable,
            "-c",
            "import time; time.sleep(30)",
            client=other,
            session=shared_name,
        )
        self._wait_for_death(self.client, shared_name)

        self.client.stop_session(shared_name)

        self.assertFalse(self.client.session_exists(shared_name))
        self.assertTrue(other.session_exists(shared_name))


if __name__ == "__main__":
    unittest.main()
