from __future__ import annotations

from contextlib import redirect_stdout
import io
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from alliance_platform.dev.cli import build_parser
from alliance_platform.dev.cli import dispatch
from alliance_platform.dev.cli import main
from alliance_platform.dev.cli import repository_root
from alliance_platform.dev.config import load_config
from alliance_platform.dev.errors import ConfigError

from tests.helpers import make_repo


class RepositoryResolutionTests(unittest.TestCase):
    def test_resolution_precedence_is_explicit_then_launcher_then_discovery(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            explicit = make_repo(root / "explicit")
            launched = make_repo(root / "launched")
            discovered = make_repo(root / "discovered")
            nested = discovered / "one" / "two"
            nested.mkdir(parents=True)
            environment = {"ALLIANCE_DEV_PROJECT_DIR": str(launched)}

            self.assertEqual(repository_root(explicit, environ=environment, cwd=nested), explicit.resolve())
            self.assertEqual(repository_root(environ=environment, cwd=nested), launched.resolve())
            self.assertEqual(repository_root(environ={}, cwd=nested), discovered.resolve())

    def test_bad_controlled_paths_fail_without_falling_back(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            discovered = make_repo(root / "project")
            nested = discovered / "nested"
            nested.mkdir()
            bad = root / "bad"
            bad.mkdir()

            for project_dir, environment in (
                (bad, {}),
                (None, {"ALLIANCE_DEV_PROJECT_DIR": str(bad)}),
            ):
                with (
                    self.subTest(project_dir=project_dir),
                    self.assertRaisesRegex(ConfigError, "missing config/dev.toml, pyproject.toml"),
                ):
                    repository_root(project_dir, environ=environment, cwd=nested)

    def test_discovery_error_names_both_required_markers(self) -> None:
        with (
            TemporaryDirectory() as temporary,
            self.assertRaisesRegex(ConfigError, "config/dev.toml, pyproject.toml"),
        ):
            repository_root(environ={}, cwd=Path(temporary))


class ConsoleBoundaryTests(unittest.TestCase):
    def test_help_and_version_do_not_resolve_a_project(self) -> None:
        for arguments in (["--help"], ["--version"]):
            output = io.StringIO()
            with (
                self.subTest(arguments=arguments),
                patch("alliance_platform.dev.cli.repository_root", side_effect=AssertionError("no project")),
                redirect_stdout(output),
                self.assertRaises(SystemExit) as raised,
            ):
                main(arguments)
            self.assertEqual(raised.exception.code, 0)
            self.assertTrue(output.getvalue())

    def test_project_dir_precedes_passthrough_command_and_native_help_is_literal(self) -> None:
        parser = build_parser()
        with patch("alliance_platform.dev.cli.make_context") as make_context:
            make_context.side_effect = RuntimeError("context reached")
            with self.assertRaisesRegex(RuntimeError, "context reached"):
                dispatch(["--project-dir", "/project", "test", "--help", "value with spaces"], parser)
        make_context.assert_called_once_with(project_dir="/project", node_environment=False)

    def test_launcher_invocation_name_is_used_in_help(self) -> None:
        with patch.dict(os.environ, {"ALLIANCE_DEV_INVOCATION_NAME": "bin/dev"}):
            self.assertEqual(build_parser().prog, "bin/dev")


class ConfigurationBoundaryTests(unittest.TestCase):
    def test_project_layout_and_delegated_commands_are_configurable_argv(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(
                root / "repo",
                config="""
django_cwd = "backend"
vite_cwd = "frontend"
manage_command = ["project-python", "manage.py"]
test_command = ["scripts/test", "--mode", "django"]
jstest_command = ["scripts/test", "--mode", "frontend"]
lint_command = ["scripts/lint"]
check_command = ["scripts/check"]
""".lstrip(),
            )
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})

            self.assertEqual(config.django_cwd, "backend")
            self.assertEqual(config.vite_cwd, "frontend")
            self.assertEqual(config.manage_command, ("project-python", "manage.py"))
            self.assertEqual(config.test_command, ("scripts/test", "--mode", "django"))
            self.assertEqual(config.jstest_command, ("scripts/test", "--mode", "frontend"))
            self.assertEqual(config.lint_command, ("scripts/lint",))
            self.assertEqual(config.check_command, ("scripts/check",))


if __name__ == "__main__":
    unittest.main()
