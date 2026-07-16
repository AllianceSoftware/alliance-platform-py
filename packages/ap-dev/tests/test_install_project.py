from __future__ import annotations

import io
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from alliance_platform.dev.cli import dispatch
from alliance_platform.dev.errors import DevError
from alliance_platform.dev.install_project import PORTLESS_DJANGO_SETTINGS
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
            self.assertIn("uvx_cache_args=(--no-cache)", launcher.read_text())
            self.assertIn(PORTLESS_DJANGO_SETTINGS, output.getvalue())
            self.assertIn("preserves the browser hostname", output.getvalue())
            self.assertTrue(os.access(launcher, os.X_OK))
            subprocess.run(["bash", "-n", launcher], check=True)

    def test_existing_generated_file_is_not_replaced_without_force(self) -> None:
        with TemporaryDirectory() as directory:
            repo = self.make_project(directory)
            (repo / "bin").mkdir()
            (repo / "bin" / "dev").write_text("custom launcher\n")

            with self.assertRaisesRegex(DevError, "Refusing to overwrite"):
                install_project(repo, assume_yes=True, console=self.console())

            self.assertEqual((repo / "bin" / "dev").read_text(), "custom launcher\n")
            self.assertFalse((repo / "config" / "dev.toml").exists())

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
