from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from typing import Callable
import unittest
from unittest.mock import patch

from alliance_platform.dev.cli import Context
from alliance_platform.dev.cli import _doctor_payload
from alliance_platform.dev.cli import _environment_payload
from alliance_platform.dev.cli import _print_environment_removal
from alliance_platform.dev.cli import _print_environments
from alliance_platform.dev.cli import _print_progress
from alliance_platform.dev.cli import _print_start_result
from alliance_platform.dev.cli import _print_status
from alliance_platform.dev.cli import _show_config
from alliance_platform.dev.cli import _show_paths
from alliance_platform.dev.cli import _status_payload
from alliance_platform.dev.cli import build_parser
from alliance_platform.dev.cli import dispatch
from alliance_platform.dev.cli import main
from alliance_platform.dev.commands import CommandDelegates
from alliance_platform.dev.config import load_config
from alliance_platform.dev.errors import DevError
from alliance_platform.dev.models import ConfigPaths
from alliance_platform.dev.models import DoctorCheck
from alliance_platform.dev.models import DoctorReport
from alliance_platform.dev.models import DoctorStateRecord
from alliance_platform.dev.models import EnvironmentRecord
from alliance_platform.dev.models import EnvironmentRemovalResult
from alliance_platform.dev.models import EnvironmentSummary
from alliance_platform.dev.models import StartResult
from alliance_platform.dev.models import StatusProcessRecord
from alliance_platform.dev.models import StatusRecord
from alliance_platform.dev.models import WorktreeIdentity

from tests.helpers import make_repo


class TTYBuffer(io.StringIO):
    def isatty(self) -> bool:
        return True


class CommandLineInteractionTests(unittest.TestCase):
    def environment_record(self) -> EnvironmentRecord:
        return EnvironmentRecord(
            project_id="demo",
            environment_id="agent-cleanup-0123456789",
            state="orphaned",
            worktree_path="/tmp/missing-agent",
            worktree_branch="codex/cleanup",
            worktree_exists=False,
            session_name="demo-wt-agent-cleanup-0123456789",
            session_state="absent",
            database_name="demo_agent_cleanup_0123456789",
            database_present=True,
            database_owned=True,
            database_setup_pending=False,
            owner_kind="agent",
            owner_id="task-123",
            lease_expires_at="2026-07-21T00:00:00Z",
            registered_at="2026-07-20T00:00:00Z",
            last_seen_at="2026-07-20T01:00:00Z",
            last_started_at="2026-07-20T00:30:00Z",
            last_stopped_at="2026-07-20T00:45:00Z",
        )

    def test_cli_owns_stable_status_json_mapping(self) -> None:
        record = StatusRecord(
            project_id="demo",
            worktree="/tmp/repo",
            worktree_id="repo-0123456789",
            branch="feature/example",
            session_name="demo-wt-repo-0123456789",
            session_state="degraded",
            readiness="notReady",
            django_url="http://localhost:8000",
            vite_url="http://localhost:5173",
            database_name="demo_repo_0123456789",
            processes=(StatusProcessRecord("worker", False, "exited", 23, "TERM"),),
        )

        self.assertEqual(
            _status_payload(record),
            {
                "projectId": "demo",
                "worktree": {
                    "id": "repo-0123456789",
                    "path": "/tmp/repo",
                    "branch": "feature/example",
                },
                "session": {
                    "name": "demo-wt-repo-0123456789",
                    "state": "degraded",
                },
                "readiness": "notReady",
                "databaseName": "demo_repo_0123456789",
                "urls": {
                    "django": "http://localhost:8000",
                    "vite": "http://localhost:5173",
                },
                "processes": [
                    {
                        "name": "worker",
                        "required": False,
                        "state": "exited",
                        "exitCode": 23,
                        "signal": "TERM",
                    }
                ],
            },
        )

    def test_status_json_uses_distinct_current_and_all_envelopes(self) -> None:
        record = StatusRecord(
            project_id="demo",
            worktree="/tmp/repo",
            worktree_id="repo-0123456789",
            branch=None,
            session_name="demo-wt-repo-0123456789",
            session_state="absent",
            readiness="notReady",
            django_url=None,
            vite_url=None,
            database_name="demo_repo_0123456789",
            processes=(StatusProcessRecord("django", True, "missing", None, None),),
        )

        current_output = io.StringIO()
        all_output = io.StringIO()
        with redirect_stdout(current_output):
            _print_status((record,), all_worktrees=False, as_json=True)
        with redirect_stdout(all_output):
            _print_status((record,), all_worktrees=True, as_json=True)

        self.assertEqual(set(json.loads(current_output.getvalue())), {"schemaVersion", "environment"})
        self.assertEqual(set(json.loads(all_output.getvalue())), {"schemaVersion", "environments"})

    def test_environment_list_has_a_stable_secret_free_json_shape(self) -> None:
        record = self.environment_record()
        output = io.StringIO()

        with redirect_stdout(output):
            _print_environments((record,), as_json=True)

        payload = json.loads(output.getvalue())
        self.assertEqual(set(payload), {"schemaVersion", "environments"})
        self.assertEqual(payload["environments"], [_environment_payload(record)])
        self.assertEqual(payload["environments"][0]["state"], "orphaned")
        self.assertEqual(
            set(payload["environments"][0]),
            {"id", "state", "projectId", "worktree", "session", "database", "owner", "activity"},
        )

    def test_environment_removal_reports_retained_unowned_database(self) -> None:
        output = io.StringIO()
        result = EnvironmentRemovalResult(
            environment_id="agent-cleanup-0123456789",
            session_stopped=True,
            database_dropped=False,
            database_was_absent=False,
            database_retained=True,
        )

        with redirect_stdout(output):
            _print_environment_removal(result)

        self.assertIn("session stopped", output.getvalue())
        self.assertIn("not registry-owned", output.getvalue())

    def test_doctor_json_has_the_documented_secret_free_shape(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = ConfigPaths(root / "project.toml", root / "global.toml", root / "worktree.toml")
            paths.project.write_text("project_id = 'demo'\n")
            report = DoctorReport(
                package_version="0.0.1",
                protocol_version=1,
                project_id="demo",
                branch="feature/example",
                worktree_id="repo-0123456789",
                worktree_path="/tmp/repo",
                session_name="demo-wt-repo-0123456789",
                database_name="demo_repo_0123456789",
                config_paths=paths,
                state=DoctorStateRecord(root / "state.json", "missing", None),
                checks=(DoctorCheck("tool:uv", "ok", "/usr/bin/uv"),),
            )

            payload = _doctor_payload(report)

            self.assertEqual(
                set(payload),
                {"schemaVersion", "tool", "identity", "configPaths", "state", "checks"},
            )
            self.assertEqual(payload["schemaVersion"], 1)
            self.assertEqual(
                payload["state"],
                {
                    "path": str(root / "state.json"),
                    "status": "missing",
                    "databaseSetupPending": None,
                },
            )

    def make_dispatch_context(self, root: Path) -> Context:
        repo = make_repo(root / "repo")
        config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
        identity = WorktreeIdentity(
            repo=repo,
            branch="feature/test",
            worktree_id="repo-0123456789",
            session_name="demo-wt-repo-0123456789",
            database_name="demo_repo_0123456789",
            portless_app_name="repo-0123456789.demo",
        )
        return Context(repo, config, identity, {}, {})

    def doctor_report(self, root: Path, *checks: DoctorCheck) -> DoctorReport:
        return DoctorReport(
            package_version="0.0.1",
            protocol_version=1,
            project_id="demo",
            branch="feature/example",
            worktree_id="repo-0123456789",
            worktree_path="/tmp/repo",
            session_name="demo-wt-repo-0123456789",
            database_name="demo_repo_0123456789",
            config_paths=ConfigPaths(root / "project.toml", root / "global.toml", root / "worktree.toml"),
            state=DoctorStateRecord(root / "state.json", "missing", None),
            checks=checks,
        )

    def test_doctor_exit_status_and_summary_reflect_failed_checks(self) -> None:
        cases = (
            ((DoctorCheck("tool:uv", "ok", "/usr/bin/uv"),), 0, "All checks passed."),
            (
                (
                    DoctorCheck("tool:uv", "ok", "/usr/bin/uv"),
                    DoctorCheck("tool:portless", "warning", "optional; not installed"),
                ),
                0,
                "1 warning.",
            ),
            (
                (
                    DoctorCheck("tool:tmux", "error", "not found on PATH"),
                    DoctorCheck("dropdb:force", "error", "installed dropdb must support --force"),
                    DoctorCheck("portless", "warning", "CLI is not installed; localhost will be used"),
                ),
                1,
                "2 errors, 1 warning.",
            ),
        )
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            context = self.make_dispatch_context(root)
            for checks, expected_status, summary in cases:
                for as_json in (False, True):
                    output = io.StringIO()
                    with (
                        self.subTest(summary=summary, as_json=as_json),
                        patch("alliance_platform.dev.cli.make_context", return_value=context),
                        patch("alliance_platform.dev.cli.DevEnvironment") as dev_environment,
                        patch("alliance_platform.dev.cli.CommandDelegates"),
                        redirect_stdout(output),
                    ):
                        dev_environment.return_value.doctor_report.return_value = self.doctor_report(
                            root, *checks
                        )
                        result = dispatch(["doctor", "--json"] if as_json else ["doctor"])

                        self.assertEqual(result, expected_status)
                        if as_json:
                            payload = json.loads(output.getvalue())
                            self.assertEqual(
                                [check["status"] for check in payload["checks"]],
                                [check.status for check in checks],
                            )
                        else:
                            self.assertTrue(output.getvalue().endswith(f"\n{summary}\n"), output.getvalue())

    def test_url_json_carries_the_schema_version(self) -> None:
        environment = EnvironmentSummary(
            branch="feature/test",
            worktree_id="repo-0123456789",
            session_name="demo-wt-repo-0123456789",
            database_name="demo_repo_0123456789",
            django_url="https://repo-0123456789.demo.localhost",
            vite_url="http://localhost:5173",
            use_portless=True,
        )
        with TemporaryDirectory() as temporary:
            context = self.make_dispatch_context(Path(temporary))
            outputs: dict[bool, str] = {}
            for as_json in (False, True):
                output = io.StringIO()
                with (
                    patch("alliance_platform.dev.cli.make_context", return_value=context),
                    patch("alliance_platform.dev.cli.DevEnvironment") as dev_environment,
                    patch("alliance_platform.dev.cli.CommandDelegates"),
                    redirect_stdout(output),
                ):
                    dev_environment.return_value.live_environment.return_value = environment
                    result = dispatch(["url", "--json"] if as_json else ["url"])

                self.assertEqual(result, 0)
                dev_environment.return_value.live_environment.assert_called_once_with(require_ready=True)
                outputs[as_json] = output.getvalue()

        self.assertEqual(outputs[False], "https://repo-0123456789.demo.localhost\n")
        self.assertEqual(
            json.loads(outputs[True]),
            {"schemaVersion": 1, "url": "https://repo-0123456789.demo.localhost"},
        )

    def test_cli_formats_an_immutable_start_result(self) -> None:
        result = StartResult(
            environment=EnvironmentSummary(
                branch="feature/example",
                worktree_id="repo-0123456789",
                session_name="demo-wt-repo-0123456789",
                database_name="demo_repo_0123456789",
                django_url="http://localhost:8000",
                vite_url="http://localhost:5173",
                use_portless=False,
            ),
            already_running=False,
            frontend_dependencies_installed=False,
            frontend_symlink_removed=False,
            database_created=False,
            recovered_incomplete_database=False,
            portless_reason="disabled by configuration",
        )
        output = io.StringIO()

        with redirect_stdout(output):
            _print_start_result(result)

        rendered = output.getvalue()
        self.assertIn("Branch:    feature/example", rendered)
        self.assertIn("Django:    http://localhost:8000", rendered)
        self.assertIn("Ready.", rendered)

    def test_progress_output_is_immediately_flushed(self) -> None:
        with patch("builtins.print") as print_output:
            _print_progress("Cloning database...")

        print_output.assert_called_once_with("→ Cloning database...", flush=True)

    def test_config_show_lists_environment_keys_without_disclosing_values(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(
                root / "repo",
                config='[environment]\nSECRET_TOKEN = "do-not-print-this"\n',
            )
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            output = io.StringIO()

            with redirect_stdout(output):
                _show_config(config)

            rendered = output.getvalue()
            self.assertIn("SECRET_TOKEN", rendered)
            self.assertIn("<redacted>", rendered)
            self.assertNotIn("do-not-print-this", rendered)

    def test_config_show_json_reports_provenance_without_environment_values(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(
                root / "repo",
                config=(
                    'project_id = "demo-project"\n'
                    "startup_timeout = 75\n"
                    '[environment]\nSECRET_TOKEN = "do-not-print-this"\n'
                ),
            )
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            output = io.StringIO()

            with redirect_stdout(output):
                _show_config(config, as_json=True)

            payload = json.loads(output.getvalue())
            self.assertEqual(payload["schemaVersion"], 1)
            timeout = next(item for item in payload["settings"] if item["key"] == "startup_timeout")
            self.assertEqual(timeout, {"key": "startup_timeout", "value": 75.0, "source": "project"})
            self.assertEqual(
                payload["environment"],
                [{"key": "SECRET_TOKEN", "source": "project"}],
            )
            self.assertNotIn("do-not-print-this", output.getvalue())

    def test_environment_values_can_only_be_revealed_in_a_terminal(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(
                root / "repo",
                config='[environment]\nSECRET_TOKEN = "visible-in-terminal"\n',
            )
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})

            with (
                patch.object(sys, "stdin", io.StringIO()),
                redirect_stdout(io.StringIO()),
                self.assertRaisesRegex(DevError, "interactive terminal"),
            ):
                _show_config(config, show_environment_values=True)

            output = TTYBuffer()
            with patch.object(sys, "stdin", TTYBuffer()), redirect_stdout(output):
                _show_config(config, show_environment_values=True)

            self.assertIn("visible-in-terminal", output.getvalue())

    def test_config_paths_json_uses_public_scope_names(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo", config='project_id = "demo-project"\n')
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            output = io.StringIO()

            with redirect_stdout(output):
                _show_paths(config, as_json=True)

            payload = json.loads(output.getvalue())
            self.assertEqual(payload["schemaVersion"], 1)
            self.assertEqual(
                [item["scope"] for item in payload["paths"]],
                ["project", "global", "worktree"],
            )
            self.assertTrue(payload["paths"][0]["committed"])
            self.assertFalse(payload["paths"][1]["committed"])

    def test_removed_config_commands_and_old_layer_names_are_rejected(self) -> None:
        parser = build_parser()
        for arguments in (
            ["config"],
            ["config", "set", "startup_timeout", "90"],
            ["config", "unset", "startup_timeout"],
            ["config", "path", "global"],
            ["config", "get", "startup_timeout"],
            ["config", "env", "show"],
            ["config", "edit", "base"],
            ["config", "edit", "local"],
        ):
            with (
                self.subTest(arguments=arguments),
                redirect_stdout(io.StringIO()),
                patch.object(sys, "stderr", io.StringIO()),
                self.assertRaises(SystemExit) as raised,
            ):
                parser.parse_args(arguments)
            self.assertEqual(raised.exception.code, 2)

    def test_logs_has_bounded_lines_and_attach_is_a_separate_command(self) -> None:
        parser = build_parser()

        logs = parser.parse_args(["logs", "django", "--lines", "75"])
        attach = parser.parse_args(["attach", "django"])

        self.assertEqual((logs.target, logs.lines), ("django", 75))
        self.assertEqual(attach.target, "django")
        for arguments in (["logs", "django", "--follow"], ["logs", "--attach"]):
            with (
                self.subTest(arguments=arguments),
                patch.object(sys, "stderr", io.StringIO()),
                self.assertRaises(SystemExit) as raised,
            ):
                parser.parse_args(arguments)
            self.assertEqual(raised.exception.code, 2)

    def test_run_parser_separates_wrapper_options_from_literal_command_arguments(self) -> None:
        parsed = build_parser().parse_args(
            ["run", "--cwd", "django-root", "--", "./project-script", "--help"]
        )

        self.assertEqual(parsed.cwd, "django-root")
        self.assertEqual(parsed.args, ["--", "./project-script", "--help"])

    def test_attach_rejects_a_non_tty_before_building_context_or_inspecting_tmux(self) -> None:
        with (
            patch.object(sys, "stdin", io.StringIO()),
            patch.object(sys, "stdout", io.StringIO()),
            patch(
                "alliance_platform.dev.cli.make_context",
                side_effect=AssertionError("must not inspect context"),
            ),
            self.assertRaisesRegex(DevError, "interactive terminal"),
        ):
            dispatch(["attach"])

    def test_no_arguments_always_prints_help_without_reading_input(self) -> None:
        output = io.StringIO()
        with (
            patch.object(sys, "stdin", TTYBuffer()),
            redirect_stdout(output),
            patch("builtins.input", side_effect=AssertionError("input must not be read")),
        ):
            result = main([])

        self.assertEqual(result, 0)
        self.assertIn("Worktree-aware development environment", output.getvalue())
        self.assertNotIn("menu", output.getvalue())

    def test_removed_commands_and_restart_override_are_rejected(self) -> None:
        parser = build_parser()
        for arguments in (
            ["menu"],
            ["open"],
            ["devtests"],
            ["restart", "--no-portless"],
            ["config", "edit"],
        ):
            with (
                self.subTest(arguments=arguments),
                patch.object(sys, "stderr", io.StringIO()),
                self.assertRaises(SystemExit) as raised,
            ):
                parser.parse_args(arguments)
            self.assertEqual(raised.exception.code, 2)

    def test_status_defaults_to_current_and_accepts_all(self) -> None:
        parser = build_parser()

        current = parser.parse_args(["status"])
        all_worktrees = parser.parse_args(["status", "--all", "--json"])

        self.assertFalse(current.all_worktrees)
        self.assertTrue(all_worktrees.all_worktrees)
        self.assertTrue(all_worktrees.as_json)

    def test_env_parser_requires_an_action_and_accepts_list_and_remove(self) -> None:
        parser = build_parser()

        listed = parser.parse_args(["env", "list", "--json"])
        removed = parser.parse_args(["env", "remove", "repo-0123456789", "--yes"])

        self.assertEqual(listed.env_action, "list")
        self.assertTrue(listed.as_json)
        self.assertEqual(removed.env_action, "remove")
        self.assertEqual(removed.environment_id, "repo-0123456789")
        self.assertTrue(removed.yes)

        with patch.object(sys, "stderr", io.StringIO()), self.assertRaises(SystemExit):
            parser.parse_args(["env"])

    def test_remainder_arguments_are_not_consumed_by_the_top_level_parser(self) -> None:
        parser = build_parser()
        parsed = parser.parse_args(["test", "package.Case.test_name", "--keepdb", "argument with spaces"])
        self.assertEqual(
            parsed.args,
            ["package.Case.test_name", "--keepdb", "argument with spaces"],
        )

    def test_dispatch_passes_every_native_argument_after_passthrough_verbs(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = WorktreeIdentity(
                repo=repo,
                branch="feature/test",
                worktree_id="repo-0123456789",
                session_name="demo-wt-repo-0123456789",
                database_name="demo_repo_0123456789",
                portless_app_name="repo-0123456789.demo",
            )
            context = Context(repo, config, identity, {}, {})
            native_args = ["--help", "--json", "argument with spaces", "$(not-executed)"]

            for verb in ("test", "jstest", "lint", "check"):
                with (
                    self.subTest(verb=verb),
                    patch("alliance_platform.dev.cli.make_context", return_value=context),
                    patch("alliance_platform.dev.cli.CommandDelegates") as delegates,
                ):
                    result = dispatch([verb, *native_args])

                self.assertEqual(result, 0)
                getattr(delegates.return_value, verb).assert_called_once_with(native_args)

    def test_dispatch_supplies_run_with_the_live_command_environment(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = WorktreeIdentity(
                repo=repo,
                branch="feature/test",
                worktree_id="repo-0123456789",
                session_name="demo-wt-repo-0123456789",
                database_name="demo_repo_0123456789",
                portless_app_name="repo-0123456789.demo",
            )
            context = Context(repo, config, identity, {}, {})
            command_environment = {"DB_NAME": identity.database_name, "LIVE": "1"}

            with (
                patch("alliance_platform.dev.cli.make_context", return_value=context),
                patch("alliance_platform.dev.cli.DevEnvironment") as dev_environment,
                patch("alliance_platform.dev.cli.CommandDelegates") as delegates,
            ):
                dev_environment.return_value.command_environment.return_value = command_environment
                result = dispatch(["run", "--cwd", "django-root", "--", "./project-script", "--help"])

            self.assertEqual(result, 0)
            delegates.return_value.run.assert_called_once_with(
                ["./project-script", "--help"],
                cwd="django-root",
                environment=command_environment,
            )

    def test_dispatch_supplies_the_flushed_progress_reporter_to_up(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = WorktreeIdentity(
                repo=repo,
                branch="feature/test",
                worktree_id="repo-0123456789",
                session_name="demo-wt-repo-0123456789",
                database_name="demo_repo_0123456789",
                portless_app_name="repo-0123456789.demo",
            )
            context = Context(repo, config, identity, {}, {})

            with (
                patch("alliance_platform.dev.cli.make_context", return_value=context),
                patch("alliance_platform.dev.cli.DevEnvironment") as dev_environment,
                patch("alliance_platform.dev.cli.CommandDelegates"),
                patch("alliance_platform.dev.cli._print_start_result"),
            ):
                result = dispatch(["up"])

            self.assertEqual(result, 0)
            dev_environment.return_value.start.assert_called_once_with(
                no_portless=False,
                on_progress=_print_progress,
            )

    def test_dispatch_removes_an_environment_non_interactively(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = WorktreeIdentity(
                repo=repo,
                branch="feature/test",
                worktree_id="repo-0123456789",
                session_name="demo-wt-repo-0123456789",
                database_name="demo_repo_0123456789",
                portless_app_name="repo-0123456789.demo",
            )
            context = Context(repo, config, identity, {}, {})
            record = self.environment_record()
            removal = EnvironmentRemovalResult(record.environment_id, False, True, False, False)

            with (
                patch("alliance_platform.dev.cli.make_context", return_value=context),
                patch("alliance_platform.dev.cli.DevEnvironment") as dev_environment,
                patch("alliance_platform.dev.cli.CommandDelegates"),
                redirect_stdout(io.StringIO()),
            ):
                dev_environment.return_value.environment_record.return_value = record
                dev_environment.return_value.remove_environment.return_value = removal
                result = dispatch(["env", "remove", record.environment_id, "--yes"])

            self.assertEqual(result, 0)
            dev_environment.return_value.environment_record.assert_called_once_with(record.environment_id)
            dev_environment.return_value.remove_environment.assert_called_once_with(record.environment_id)

    def test_passthrough_command_has_discoverable_wrapper_help(self) -> None:
        output = io.StringIO()

        with redirect_stdout(output), self.assertRaises(SystemExit) as raised:
            main(["help", "test"])

        self.assertEqual(raised.exception.code, 0)
        self.assertIn("usage: alliance-dev test", output.getvalue())


class ExecCalled(Exception):
    pass


class CommandDelegateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.repo = make_repo(
            root / "repo",
            config=(
                'test_command = ["bin/run-tests-django.sh"]\n'
                'jstest_command = ["bin/run-tests-frontend.sh"]\n'
                'lint_command = ["bin/lint.sh"]\n'
                'check_command = ["bin/check.sh"]\n'
            ),
        )
        project_python = self.repo / ".venv" / "bin" / "python"
        project_python.parent.mkdir(parents=True)
        project_python.write_text("#!/bin/sh\n")
        project_python.chmod(0o755)
        self.config = load_config(self.repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
        self.identity = WorktreeIdentity(
            repo=self.repo,
            branch="feature/test",
            worktree_id="repo-0123456789",
            session_name="demo-wt-repo-0123456789",
            database_name="demo_repo_0123456789",
            portless_app_name="repo-0123456789.demo",
        )

    def delegates(self, environment: dict[str, str] | None = None) -> CommandDelegates:
        return CommandDelegates(
            self.repo,
            self.config,
            self.identity,
            environment
            or {
                "DB_NAME": "wrong-database",
                "PGDATABASE": "also-wrong",
                "DISABLE_SSR": "0",
                "PASSTHROUGH": "kept",
                "PATH": "/caller/bin",
            },
        )

    def assert_exec(
        self,
        invoke: Callable[[], object],
        expected: tuple[str, ...],
        *,
        expected_cwd: Path | None = None,
        verification: bool = False,
    ) -> None:
        captured: dict[str, object] = {}

        def execute(file: str, argv: list[str], environment: dict[str, str]) -> None:
            captured.update(file=file, argv=tuple(argv), environment=environment)
            raise ExecCalled

        with (
            patch("alliance_platform.dev.commands.os.chdir") as change_directory,
            patch("alliance_platform.dev.commands.os.execvpe", side_effect=execute),
            self.assertRaises(ExecCalled),
        ):
            invoke()

        self.assertEqual(captured["file"], expected[0])
        self.assertEqual(captured["argv"], expected)
        change_directory.assert_called_once_with(expected_cwd or self.repo)
        environment = captured["environment"]
        assert isinstance(environment, dict)
        self.assertEqual(environment["PASSTHROUGH"], "kept")
        self.assertEqual(environment["DB_NAME"], self.identity.database_name)
        self.assertEqual(environment["PGDATABASE"], self.identity.database_name)
        self.assertEqual(environment["DEV_PROJECT"], "demo-project")
        self.assertEqual(environment["DEV_WORKTREE"], str(self.repo))
        self.assertEqual(environment["DEV_WORKTREE_ID"], self.identity.worktree_id)
        self.assertEqual(environment["PYTHONPATH"], str(self.repo))
        if verification:
            self.assertEqual(environment["DISABLE_SSR"], "1")
            project_venv = (self.repo / ".venv").resolve()
            self.assertEqual(environment["VIRTUAL_ENV"], str(project_venv))
            self.assertEqual(
                environment["PATH"],
                f"{project_venv / 'bin'}{os.pathsep}/caller/bin",
            )
        else:
            self.assertEqual(environment["DISABLE_SSR"], "0")
            self.assertNotIn("VIRTUAL_ENV", environment)
            self.assertEqual(environment["PATH"], "/caller/bin")

    def test_django_test_preserves_native_arguments_and_injects_the_worktree_database(self) -> None:
        delegates = self.delegates()
        arguments = ["package.Case.test_name", "--keepdb", "argument with spaces"]

        self.assert_exec(
            lambda: delegates.test(arguments),
            ("bin/run-tests-django.sh", *arguments),
            verification=True,
        )

    def test_native_arguments_are_not_rebased_routed_or_reformatted(self) -> None:
        delegates = self.delegates()
        hostile = ["relative path.test.ts", "--help", "$(touch should-not-run)"]

        self.assert_exec(
            lambda: delegates.jstest(hostile),
            ("bin/run-tests-frontend.sh", *hostile),
        )
        self.assert_exec(
            lambda: delegates.lint(hostile),
            ("bin/lint.sh", *hostile),
            verification=True,
        )

    def test_check_delegates_to_the_authoritative_script_with_native_arguments(self) -> None:
        delegates = self.delegates()
        arguments = ["--all", "--step", "django"]

        self.assert_exec(
            lambda: delegates.check(arguments),
            ("bin/check.sh", *arguments),
            verification=True,
        )

    def test_disabled_verification_command_has_an_actionable_error(self) -> None:
        config = replace(self.config, check_command=())
        delegates = CommandDelegates(self.repo, config, self.identity, {})

        with self.assertRaisesRegex(
            DevError,
            "check is not configured.*Set check_command in config/dev.toml.*doctor",
        ):
            delegates.check([])

    def test_missing_project_virtualenv_fails_before_executing_verification_script(self) -> None:
        (self.repo / ".venv" / "bin" / "python").unlink()
        delegates = self.delegates()

        with (
            patch("alliance_platform.dev.commands.os.execvpe") as execute,
            self.assertRaisesRegex(DevError, "project virtualenv is not provisioned.*uv sync"),
        ):
            delegates.test(["package.Case"])

        execute.assert_not_called()

    def test_frontend_tests_do_not_require_the_python_virtualenv(self) -> None:
        (self.repo / ".venv" / "bin" / "python").unlink()

        self.assert_exec(
            lambda: self.delegates().jstest(["frontend.test.ts"]),
            ("bin/run-tests-frontend.sh", "frontend.test.ts"),
        )

    def test_delegated_command_uses_configured_argv_and_appends_arguments_literally(self) -> None:
        config = replace(self.config, test_command=("scripts/verify", "django"))
        delegates = CommandDelegates(
            self.repo,
            config,
            self.identity,
            {"PASSTHROUGH": "kept", "PATH": "/caller/bin"},
        )
        dangerous = "value with spaces; $(touch never-executed)"

        self.assert_exec(
            lambda: delegates.test([dangerous]),
            ("scripts/verify", "django", dangerous),
            verification=True,
        )

    def test_run_execs_literal_argv_from_a_valid_repository_directory(self) -> None:
        delegates = self.delegates()
        working_directory = self.repo / "scripts"
        working_directory.mkdir()
        environment = delegates._managed_environment()
        environment["DEV_BASE_HOST"] = "repo.test"
        arguments = ["./project-script", "value with spaces; $(touch never-executed)"]

        self.assert_exec(
            lambda: delegates.run(arguments, cwd="scripts", environment=environment),
            tuple(arguments),
            expected_cwd=working_directory.resolve(),
        )

    def test_run_rejects_empty_commands_and_working_directories_outside_the_repository(self) -> None:
        delegates = self.delegates()
        outside = self.repo.parent / "outside"
        outside.mkdir()
        outside_alias = self.repo / "outside-alias"
        outside_alias.symlink_to(outside, target_is_directory=True)

        with self.assertRaisesRegex(DevError, "Usage: alliance-dev run"):
            delegates.run([], cwd=".", environment={})
        for cwd in ("missing", str(outside), "outside-alias"):
            with (
                self.subTest(cwd=cwd),
                self.assertRaisesRegex(
                    DevError,
                    "working directory",
                ),
            ):
                delegates.run(["true"], cwd=cwd, environment={})


if __name__ == "__main__":
    unittest.main()
