from __future__ import annotations

import io
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from alliance_platform.dev.cli import dispatch
from alliance_platform.dev.errors import DevError
from alliance_platform.dev.install_project import install_project
from alliance_platform.dev.install_project import resolve_install_root
from rich.console import Console


class ProjectInstallationTests(unittest.TestCase):
    def make_project(self, directory: str, *, settings_name: str = "dev.py") -> Path:
        repo = Path(directory).resolve()
        (repo / "django-root" / "example" / "settings").mkdir(parents=True)
        (repo / "django-root" / "manage.py").write_text("#!/usr/bin/env python\n")
        (repo / "django-root" / "example" / "settings" / settings_name).write_text("DEBUG = True\n")
        (repo / "pyproject.toml").write_text('[project]\nname = "Example App"\n')
        (repo / "package.json").write_text("{}\n")
        return repo

    def console(self) -> Console:
        return Console(file=io.StringIO(), force_terminal=False, color_system=None)

    def test_install_creates_launcher_and_root_vite_config_idempotently(self) -> None:
        with TemporaryDirectory() as directory:
            repo = self.make_project(directory)
            settings = repo / "django-root" / "example" / "settings" / "dev.py"
            output = io.StringIO()
            console = Console(file=output, force_terminal=False, color_system=None)

            first = install_project(
                repo,
                assume_yes=True,
                tool_source="/tmp/alliance platform dev",
                console=console,
            )
            second = install_project(
                repo,
                assume_yes=True,
                tool_source="/tmp/alliance platform dev",
                console=console,
            )

            launcher = repo / "bin" / "dev"
            config = repo / "config" / "dev.toml"
            self.assertEqual(set(first.created), {launcher, config})
            self.assertEqual(set(second.unchanged), {launcher, config})
            self.assertEqual(settings.read_text(), "DEBUG = True\n")
            self.assertIn('project_id = "example-app"', config.read_text())
            self.assertIn('django_cwd = "django-root"', config.read_text())
            self.assertIn('vite_cwd = "."', config.read_text())
            self.assertIn("default_tool_source='/tmp/alliance platform dev'", launcher.read_text())
            self.assertIn("CSRF_TRUSTED_ORIGINS = [", output.getvalue())
            self.assertIn("USE_X_FORWARDED_HOST = True", output.getvalue())
            self.assertIn("SECURE_PROXY_SSL_HEADER", output.getvalue())
            self.assertIn("preserves the browser hostname", output.getvalue())
            self.assertTrue(os.access(launcher, os.X_OK))
            subprocess.run(["bash", "-n", launcher], check=True)

    def test_launcher_runs_with_pypi_git_and_local_tool_sources_under_nounset(self) -> None:
        sources = {
            "pypi": ("alliance-platform-dev==1.2.3", False),
            "git": (
                "git+https://github.com/example/project.git@branch#subdirectory=packages/ap-dev",
                True,
            ),
            "local": ("/tmp/local-ap-dev", True),
        }
        for source_type, (source, expect_no_cache) in sources.items():
            with self.subTest(source_type=source_type), TemporaryDirectory() as directory:
                repo = self.make_project(directory)
                install_project(
                    repo,
                    assume_yes=True,
                    tool_source=source,
                    console=self.console(),
                )
                fake_bin = repo / "fake-bin"
                fake_bin.mkdir()
                for name, contents in (
                    ("uv", "#!/bin/sh\nexit 0\n"),
                    ("uvx", '#!/bin/sh\nprintf "%s\\n" "$@" > "$CAPTURE_FILE"\n'),
                ):
                    executable = fake_bin / name
                    executable.write_text(contents)
                    executable.chmod(0o755)
                capture = repo / "uvx-args"
                environment = dict(os.environ)
                environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
                environment["CAPTURE_FILE"] = str(capture)

                subprocess.run([repo / "bin" / "dev", "doctor"], env=environment, check=True)

                arguments = capture.read_text().splitlines()
                self.assertEqual("--no-cache" in arguments, expect_no_cache)
                self.assertIn(source, arguments)
                self.assertEqual(arguments[-2:], ["alliance-dev", "doctor"])

    def test_existing_generated_file_is_not_replaced_without_force(self) -> None:
        with TemporaryDirectory() as directory:
            repo = self.make_project(directory)
            (repo / "bin").mkdir()
            (repo / "bin" / "dev").write_text("custom launcher\n")

            with self.assertRaisesRegex(DevError, "Refusing to overwrite"):
                install_project(repo, assume_yes=True, console=self.console())

            self.assertEqual((repo / "bin" / "dev").read_text(), "custom launcher\n")
            self.assertFalse((repo / "config" / "dev.toml").exists())

    def test_install_wraps_environment_sensitive_husky_hooks(self) -> None:
        with TemporaryDirectory() as directory:
            repo = self.make_project(directory)
            husky = repo / ".husky"
            husky.mkdir()
            pre_commit = husky / "pre-commit"
            pre_commit.write_text('#!/bin/sh\n. "$(dirname "$0")/_/husky.sh"\n\nyarn lint-staged --verbose\n')
            pre_push = husky / "pre-push"
            pre_push.write_text(
                '#!/bin/sh\n. "$(dirname "$0")/_/husky.sh"\n\n'
                'if [ "$1" = "skip" ]; then\n    exit 0\nfi\n'
                "exec ./bin/lint.sh --aggregate-only\n"
            )
            commit_msg = husky / "commit-msg"
            commit_msg.write_text('#!/bin/sh\n./bin/git-hooks/commit-msg "$1"\n')

            first = install_project(repo, assume_yes=True, console=self.console())
            second = install_project(repo, assume_yes=True, console=self.console())

            wrapper = repo / "bin" / "run-with-dev-env-if-managed"
            self.assertIn(wrapper, first.created)
            self.assertIn(pre_commit, first.updated)
            self.assertIn(pre_push, first.updated)
            self.assertIn(wrapper, second.unchanged)
            self.assertIn(pre_commit, second.unchanged)
            self.assertIn(pre_push, second.unchanged)
            self.assertIn(
                "exec ./bin/run-with-dev-env-if-managed yarn lint-staged --verbose",
                pre_commit.read_text(),
            )
            self.assertIn(
                "exec ./bin/run-with-dev-env-if-managed ./bin/lint.sh --aggregate-only",
                pre_push.read_text(),
            )
            self.assertEqual(commit_msg.read_text(), '#!/bin/sh\n./bin/git-hooks/commit-msg "$1"\n')
            self.assertTrue(os.access(wrapper, os.X_OK))
            subprocess.run(["bash", "-n", wrapper], check=True)

    def test_interactive_install_can_leave_husky_hooks_unchanged(self) -> None:
        with TemporaryDirectory() as directory:
            repo = self.make_project(directory)
            husky = repo / ".husky"
            husky.mkdir()
            pre_commit = husky / "pre-commit"
            original = "#!/bin/sh\nyarn lint-staged\n"
            pre_commit.write_text(original)
            console = Console(file=io.StringIO(), force_terminal=True, color_system=None)

            with (
                patch(
                    "alliance_platform.dev.install_project.Prompt.ask",
                    return_value="example-app",
                ),
                patch(
                    "alliance_platform.dev.install_project.Confirm.ask",
                    return_value=False,
                ) as confirm,
            ):
                install_project(repo, console=console)

            confirm.assert_called_once()
            self.assertEqual(pre_commit.read_text(), original)
            self.assertFalse((repo / "bin" / "run-with-dev-env-if-managed").exists())

    def test_hook_wrapper_selects_managed_inherited_and_opt_out_environments(self) -> None:
        with TemporaryDirectory() as directory:
            repo = self.make_project(directory)
            husky = repo / ".husky"
            husky.mkdir()
            (husky / "pre-commit").write_text("#!/bin/sh\n./bin/check-hook value\n")
            install_project(repo, assume_yes=True, console=self.console())
            wrapper = repo / "bin" / "run-with-dev-env-if-managed"
            capture = repo / "capture"
            command = repo / "bin" / "check-hook"
            command.write_text('#!/bin/sh\nprintf "direct:%s\\n" "$*" > "$CAPTURE_FILE"\n')
            command.chmod(0o755)
            environment = {**os.environ, "CAPTURE_FILE": str(capture)}

            subprocess.run([wrapper, command, "one"], env=environment, check=True)
            self.assertEqual(capture.read_text(), "direct:one\n")

            (repo / ".dev-server").mkdir()
            (repo / ".dev-server" / "state.json").write_text("{}\n")
            (repo / "bin" / "dev").write_text('#!/bin/sh\nprintf "managed:%s\\n" "$*" > "$CAPTURE_FILE"\n')
            (repo / "bin" / "dev").chmod(0o755)
            subprocess.run([wrapper, command, "two"], env=environment, check=True)
            self.assertEqual(capture.read_text(), f"managed:run -- {command} two\n")

            environment["BIN_DEV_HOOK_ENV"] = "off"
            subprocess.run([wrapper, command, "three"], env=environment, check=True)
            self.assertEqual(capture.read_text(), "direct:three\n")

    def test_resolve_install_root_only_requires_pyproject(self) -> None:
        with TemporaryDirectory() as directory:
            repo = self.make_project(directory)
            nested = repo / "django-root" / "example"

            self.assertEqual(resolve_install_root(cwd=nested, environ={}), repo)

    def test_install_is_available_before_project_configuration_exists(self) -> None:
        with TemporaryDirectory() as directory:
            repo = self.make_project(directory)

            exit_code = dispatch(["install", str(repo), "--yes", "--tool-source", "/tmp/local-ap-dev"])

            self.assertEqual(exit_code, 0)
            self.assertTrue((repo / "bin" / "dev").is_file())
            self.assertTrue((repo / "config" / "dev.toml").is_file())


if __name__ == "__main__":
    unittest.main()
