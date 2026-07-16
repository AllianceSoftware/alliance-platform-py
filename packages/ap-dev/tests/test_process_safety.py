from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from alliance_platform.dev.errors import DevError
from alliance_platform.dev.models import ProcessSpec
from alliance_platform.dev.models import ProcessStatus
from alliance_platform.dev.runner import CommandResult
from alliance_platform.dev.tmux import TmuxClient

from tests.helpers import RecordingRunner


class ProcessSpecSafetyTests(unittest.TestCase):
    def test_tmux_returns_shared_process_status_records(self) -> None:
        with TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            runner = RecordingRunner(
                [CommandResult(0, "django\t0\t\t\nworker\t1\t23\t\nsignalled\t1\t\tterm\n")],
                available=("tmux",),
            )
            tmux = TmuxClient(runner, repo, {})

            statuses = tmux.process_statuses("demo-session")

            self.assertEqual(
                statuses,
                {
                    "django": ProcessStatus("django", True, None),
                    "worker": ProcessStatus("worker", False, 23),
                    "signalled": ProcessStatus("signalled", False, None, "term"),
                },
            )

    def test_configured_argv_is_passed_directly_after_the_tmux_separator(self) -> None:
        with TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            runner = RecordingRunner(
                [CommandResult(0), CommandResult(1), CommandResult(0)],
                available=("tmux",),
            )
            tmux = TmuxClient(runner, repo, {"HOME": "/home/dev", "STALE": "control-only"})
            dangerous = (
                "worker executable",
                "argument with spaces",
                "; touch should-not-exist",
                "$(touch should-not-exist)",
                "quote'\"value",
                "",
            )

            tmux.start_session(
                "demo-session",
                (ProcessSpec("worker", dangerous, repo),),
                {"TOKEN": "value", "TERM": "xterm", "TMUX": "personal"},
                {
                    "DEV_PROJECT": "demo",
                    "DEV_WORKTREE": str(repo),
                    "DEV_WORKTREE_ID": "repo-0123456789",
                    "DEV_DJANGO_PORT": "8000",
                    "DEV_VITE_PORT": "5173",
                    "DEV_PROTOCOL_VERSION": "1",
                },
            )

            launch = next(call.args for call in runner.calls if "new-session" in call.args)
            separator = launch.index("--")
            self.assertEqual(launch[separator + 1 :], dangerous)
            self.assertEqual(launch[launch.index("-c") + 1], str(repo))
            self.assertIn("TOKEN=value", launch)
            self.assertIn("DEV_PROJECT=demo", launch)
            self.assertFalse(any(value.startswith("TERM=") for value in launch))
            self.assertFalse(any(value.startswith("TMUX=") for value in launch))
            self.assertFalse(any("sleep 2147483647" in value for value in launch))
            self.assertFalse((repo / ".dev-server" / "processes").exists())

    def test_restart_and_output_capture_use_native_tmux_commands(self) -> None:
        with TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            runner = RecordingRunner(
                [
                    CommandResult(0, ""),
                    CommandResult(0, "captured output\n"),
                ]
            )
            runner.available.add("tmux")
            tmux = TmuxClient(runner, repo, {})

            tmux.restart_process("demo-session", "django")
            output = tmux.capture_output("demo-session", "django", lines=75)

            self.assertEqual(output, "captured output")
            commands = [call.args for call in runner.calls]
            self.assertIn(
                (
                    "/fake/tmux",
                    "-L",
                    "alliance-dev-v1",
                    "-f",
                    "/dev/null",
                    "respawn-window",
                    "-k",
                    "-t",
                    "demo-session:django",
                ),
                commands,
            )
            self.assertIn(
                (
                    "/fake/tmux",
                    "-L",
                    "alliance-dev-v1",
                    "-f",
                    "/dev/null",
                    "capture-pane",
                    "-p",
                    "-J",
                    "-S",
                    "-75",
                    "-t",
                    "demo-session:django",
                ),
                commands,
            )

    def test_start_requires_the_exact_metadata_shape_before_mutation(self) -> None:
        with TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            runner = RecordingRunner(available=("tmux",))
            tmux = TmuxClient(runner, repo, {})

            with self.assertRaisesRegex(DevError, "Missing tmux metadata.*DEV_VITE_PORT"):
                tmux.start_session(
                    "demo-session",
                    (ProcessSpec("django", ("python",), repo),),
                    {},
                    {
                        "DEV_PROJECT": "demo",
                        "DEV_WORKTREE": str(repo),
                        "DEV_WORKTREE_ID": "repo-0123456789",
                        "DEV_DJANGO_PORT": "8000",
                    },
                )

            self.assertEqual(runner.calls, [])

    def test_attach_can_target_one_process(self) -> None:
        with TemporaryDirectory() as temporary:
            repo = Path(temporary) / "repo"
            repo.mkdir()
            tmux = TmuxClient(RecordingRunner(available=("tmux",)), repo, {"PATH": "/bin"})

            with (
                patch.dict("alliance_platform.dev.tmux.os.environ", {}, clear=True),
                patch("alliance_platform.dev.tmux.os.execvpe") as execute,
            ):
                tmux.attach("demo-session", "django")

            execute.assert_called_once_with(
                "/fake/tmux",
                [
                    "/fake/tmux",
                    "-L",
                    "alliance-dev-v1",
                    "-f",
                    "/dev/null",
                    "attach-session",
                    "-E",
                    "-t",
                    "demo-session:django",
                ],
                {"PATH": "/bin"},
            )


if __name__ == "__main__":
    unittest.main()
