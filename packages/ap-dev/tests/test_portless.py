from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from alliance_platform.dev.errors import DevError
from alliance_platform.dev.portless import PortlessAdapter
from alliance_platform.dev.runner import CommandResult

from tests.helpers import RecordingRunner


class PortlessAdapterTests(unittest.TestCase):
    def adapter(self, runner: RecordingRunner, repo: Path) -> PortlessAdapter:
        return PortlessAdapter(
            runner,
            repo,
            {"PATH": "/fake/bin"},
            "checkout-0123456789.demo-project",
        )

    @staticmethod
    def supported_runner() -> RecordingRunner:
        return RecordingRunner(
            [
                CommandResult(
                    0,
                    "--name <name>\napps auto-start the proxy and register automatically\n",
                ),
                CommandResult(0, "Usage: portless get <name>\n--no-worktree\n"),
            ],
            available=("portless",),
        )

    def test_off_never_checks_or_invokes_the_cli(self) -> None:
        runner = RecordingRunner(available=("portless",))

        selection = self.adapter(runner, Path("/repo")).select("off")

        self.assertFalse(selection.enabled)
        self.assertEqual(selection.reason, "disabled by configuration")
        self.assertEqual(runner.calls, [])

    def test_no_portless_override_wins_over_required_policy(self) -> None:
        runner = RecordingRunner()

        selection = self.adapter(runner, Path("/repo")).select("required", force_off=True)

        self.assertFalse(selection.enabled)
        self.assertIn("--no-portless", selection.reason)

    def test_auto_enables_a_cli_with_the_documented_launch_and_url_contract(self) -> None:
        runner = self.supported_runner()

        selection = self.adapter(runner, Path("/repo")).select("auto")

        self.assertTrue(selection.enabled)
        self.assertIn("on-demand proxy startup", selection.reason)
        self.assertEqual(
            [call.args for call in runner.calls],
            [("portless", "--help"), ("portless", "get", "--help")],
        )

    def test_required_enables_a_supported_cli(self) -> None:
        selection = self.adapter(self.supported_runner(), Path("/repo")).select("required")

        self.assertTrue(selection.enabled)

    def test_required_fails_actionably_when_cli_is_missing(self) -> None:
        with self.assertRaisesRegex(DevError, "required.*not installed.*portless ="):
            self.adapter(RecordingRunner(), Path("/repo")).select("required")

    def test_unsupported_cli_falls_back_for_auto_and_fails_for_required(self) -> None:
        auto_runner = RecordingRunner(
            [CommandResult(0, "older help\n"), CommandResult(0, "older get help\n")],
            available=("portless",),
        )
        required_runner = RecordingRunner(
            [CommandResult(0, "older help\n"), CommandResult(0, "older get help\n")],
            available=("portless",),
        )

        selection = self.adapter(auto_runner, Path("/repo")).select("auto")

        self.assertFalse(selection.enabled)
        self.assertIn("does not advertise", selection.reason)

        with self.assertRaisesRegex(DevError, "required.*does not support.*Upgrade"):
            self.adapter(required_runner, Path("/repo")).select("required")

    def test_diagnostics_reports_supported_auto_selection(self) -> None:
        diagnostics = self.adapter(self.supported_runner(), Path("/repo")).diagnostics("auto")

        self.assertTrue(diagnostics.selected)
        self.assertEqual(diagnostics.proxy_availability_capability, "autoStart")

    def test_url_resolution_uses_only_the_documented_get_command(self) -> None:
        runner = RecordingRunner([CommandResult(0, "https://checkout.demo.test\n")])
        adapter = self.adapter(runner, Path("/repo"))

        url = adapter.resolve_url()

        self.assertEqual(url, "https://checkout.demo.test")
        self.assertEqual(
            runner.calls[0].args,
            ("portless", "get", "checkout-0123456789.demo-project", "--no-worktree"),
        )
        self.assertTrue(runner.calls[0].capture)

    def test_url_resolution_rejects_invalid_cli_output(self) -> None:
        runner = RecordingRunner([CommandResult(0, "https://\n")])

        with self.assertRaisesRegex(DevError, "invalid URL"):
            self.adapter(runner, Path("/repo")).resolve_url()

    def test_django_command_passes_cwd_and_argv_directly_without_a_spec_file(self) -> None:
        adapter = self.adapter(RecordingRunner(), Path("/repo"))

        command = adapter.django_command(
            Path("/repo/django-root"),
            ("uv", "run", "python", "manage.py", "runserver", "value with spaces; $()"),
        )

        self.assertEqual(command[:4], ["portless", "--name", adapter.app_name, "--"])
        self.assertEqual(command[4:6], ["/bin/sh", "-c"])
        self.assertEqual(
            command[7:10],
            ["alliance-dev-portless", "alliance-dev", "/repo/django-root"],
        )
        self.assertEqual(
            command[10:],
            ["uv", "run", "python", "manage.py", "runserver", "value with spaces; $()"],
        )
        self.assertNotIn(sys.executable, command)
        self.assertNotIn("alliance_platform.dev", " ".join(command))


class PortlessShellAdapterTests(unittest.TestCase):
    def _command(self, cwd: Path, argv: tuple[str, ...]) -> list[str]:
        generated = PortlessAdapter(RecordingRunner(), cwd.parent, {}, "example.demo").django_command(
            cwd, argv
        )
        return generated[4:]

    def test_adapter_execs_direct_argv_from_cwd_with_portless_bind_appended(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            cwd = root / "working directory"
            cwd.mkdir()
            output = root / "result.json"
            hostile = "value with spaces; $(touch never-executed)"
            script = (
                "import json, os, pathlib, sys; "
                "pathlib.Path(sys.argv[1]).write_text(json.dumps("
                "{'cwd': os.getcwd(), 'argv': sys.argv[2:]}))"
            )
            environment = dict(os.environ)
            environment["PORT"] = "4567"

            result = subprocess.run(
                self._command(
                    cwd,
                    (sys.executable, "-c", script, str(output), hostile, ""),
                ),
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            value = json.loads(output.read_text())
            self.assertEqual(Path(value["cwd"]).resolve(), cwd.resolve())
            self.assertEqual(value["argv"], [hostile, "", "127.0.0.1:4567"])
            self.assertFalse((cwd / "never-executed").exists())

    def test_adapter_rejects_a_missing_or_out_of_range_port(self) -> None:
        for port in (None, "not-a-number", "１２", "0", "65536"):
            with self.subTest(port=port), TemporaryDirectory() as temporary:
                environment = dict(os.environ)
                if port is None:
                    environment.pop("PORT", None)
                else:
                    environment["PORT"] = port
                result = subprocess.run(
                    self._command(
                        Path(temporary),
                        (sys.executable, "-c", "raise SystemExit(99)"),
                    ),
                    env=environment,
                    check=False,
                    capture_output=True,
                    text=True,
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("numeric PORT", result.stderr)


if __name__ == "__main__":
    unittest.main()
