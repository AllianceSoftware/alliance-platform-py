from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler
from http.server import ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch
import zipfile

from alliance_platform.dev.cli import dispatch
from alliance_platform.dev.errors import DevError
from alliance_platform.dev.install_project import install_project
from alliance_platform.dev.install_project import resolve_install_root
from alliance_platform.dev.install_project import update_launcher
from rich.console import Console


class QuietSimpleHTTPRequestHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


class ProjectInstallationTests(unittest.TestCase):
    def make_launcher_test_wheel(self, directory: Path) -> Path:
        wheel = directory / "alliance_platform_dev-0.0.2-py3-none-any.whl"
        dist_info = "alliance_platform_dev-0.0.2.dist-info"
        files = {
            "launcher_test_fixture.py": (
                'def main():\n    print("alliance-platform-dev 0.0.2 (launcher test fixture)")\n'
            ),
            f"{dist_info}/METADATA": ("Metadata-Version: 2.1\nName: alliance-platform-dev\nVersion: 0.0.2\n"),
            f"{dist_info}/WHEEL": (
                "Wheel-Version: 1.0\n"
                "Generator: alliance-platform-dev tests\n"
                "Root-Is-Purelib: true\n"
                "Tag: py3-none-any\n"
            ),
            f"{dist_info}/entry_points.txt": (
                "[console_scripts]\nalliance-dev = launcher_test_fixture:main\n"
            ),
        }
        record = "".join(f"{name},,\n" for name in [*files, f"{dist_info}/RECORD"])
        with zipfile.ZipFile(wheel, "w") as archive:
            for name, contents in files.items():
                archive.writestr(name, contents)
            archive.writestr(f"{dist_info}/RECORD", record)
        return wheel

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
            gitignore = repo / ".gitignore"
            self.assertEqual(set(first.created), {launcher, config, gitignore})
            self.assertEqual(set(second.unchanged), {launcher, config, gitignore})
            self.assertEqual(settings.read_text(), "DEBUG = True\n")
            self.assertEqual(
                gitignore.read_text(),
                "# Worktree state managed by bin/dev\n.dev-server/\n",
            )
            self.assertIn("added .dev-server/ to .gitignore", output.getvalue())
            self.assertIn('project_id = "example-app"', config.read_text())
            self.assertIn('django_cwd = "django-root"', config.read_text())
            self.assertIn('vite_cwd = "."', config.read_text())
            self.assertIn('verification_virtualenv = ".venv"', config.read_text())
            self.assertIn(
                'test_command = ["uv", "run", "python", "django-root/manage.py", "test"]',
                config.read_text(),
            )
            self.assertIn("jstest_command = []", config.read_text())
            self.assertIn("lint_command = []", config.read_text())
            self.assertIn("check_command = []", config.read_text())
            self.assertIn("default_tool_source='/tmp/alliance platform dev'", launcher.read_text())
            self.assertIn("Verification commands", output.getvalue())
            self.assertIn("Full check:       not configured", output.getvalue())
            self.assertIn("CSRF_TRUSTED_ORIGINS = [", output.getvalue())
            self.assertIn("USE_X_FORWARDED_HOST = True", output.getvalue())
            self.assertIn("SECURE_PROXY_SSL_HEADER", output.getvalue())
            self.assertIn("preserves the browser hostname", output.getvalue())
            self.assertIn("run uv sync to provision .venv", output.getvalue())
            self.assertTrue(os.access(launcher, os.X_OK))
            subprocess.run(["bash", "-n", launcher], check=True)

    def test_install_prefers_existing_verification_wrappers(self) -> None:
        with TemporaryDirectory() as directory:
            repo = self.make_project(directory)
            (repo / "bin").mkdir()
            for name in (
                "run-tests-django.sh",
                "run-tests-frontend.sh",
                "lint.sh",
                "check.sh",
            ):
                script = repo / "bin" / name
                script.write_text("#!/bin/sh\n")
                script.chmod(0o755)

            install_project(repo, assume_yes=True, console=self.console())

            contents = (repo / "config" / "dev.toml").read_text()
            self.assertIn('test_command = ["bin/run-tests-django.sh"]', contents)
            self.assertIn('jstest_command = ["bin/run-tests-frontend.sh"]', contents)
            self.assertIn('lint_command = ["bin/lint.sh"]', contents)
            self.assertIn('check_command = ["bin/check.sh"]', contents)

    def test_install_detects_a_vitest_package_script_and_forces_single_run(self) -> None:
        with TemporaryDirectory() as directory:
            repo = self.make_project(directory)
            (repo / "package.json").write_text(
                json.dumps({"scripts": {"test": "cross-env NODE_ENV=test vitest"}})
            )

            install_project(repo, assume_yes=True, console=self.console())

            contents = (repo / "config" / "dev.toml").read_text()
            self.assertIn('jstest_command = ["yarn", "test", "--run"]', contents)

    def test_install_does_not_guess_from_an_unrelated_package_test_script(self) -> None:
        with TemporaryDirectory() as directory:
            repo = self.make_project(directory)
            (repo / "package.json").write_text(json.dumps({"scripts": {"test": "jest"}}))

            install_project(repo, assume_yes=True, console=self.console())

            self.assertIn("jstest_command = []", (repo / "config" / "dev.toml").read_text())

    def test_update_launcher_preserves_existing_project_configuration(self) -> None:
        with TemporaryDirectory() as directory:
            repo = self.make_project(directory)
            install_project(
                repo,
                assume_yes=True,
                tool_source="alliance-platform-dev==1.0.0",
                console=self.console(),
            )
            launcher_path = repo / "bin" / "dev"
            launcher_path.write_text(
                launcher_path.read_text().replace(
                    "# Generated by alliance-platform-dev. Update with `alliance-dev update-launcher`.\n",
                    "",
                )
            )
            config = repo / "config" / "dev.toml"
            config.write_text("project-owned configuration\n")

            result = update_launcher(
                repo,
                tool_source="alliance-platform-dev==1.1.0",
                console=self.console(),
            )

            self.assertEqual(result.state, "updated")
            self.assertEqual(result.previous_source, "alliance-platform-dev==1.0.0")
            self.assertEqual(result.source, "alliance-platform-dev==1.1.0")
            self.assertEqual(config.read_text(), "project-owned configuration\n")
            launcher = launcher_path.read_text()
            self.assertIn("default_tool_source=alliance-platform-dev==1.1.0", launcher)
            self.assertIn("Generated by alliance-platform-dev", launcher)

    def test_update_launcher_refuses_an_unrecognized_script_without_force(self) -> None:
        with TemporaryDirectory() as directory:
            repo = self.make_project(directory)
            launcher = repo / "bin" / "dev"
            launcher.parent.mkdir()
            launcher.write_text("#!/bin/sh\necho custom\n")

            with self.assertRaisesRegex(DevError, "unrecognized.*pass --force"):
                update_launcher(repo, tool_source="alliance-platform-dev==1.1.0", console=self.console())

            self.assertEqual(launcher.read_text(), "#!/bin/sh\necho custom\n")

    def test_update_launcher_command_can_create_or_force_replace_only_bin_dev(self) -> None:
        with TemporaryDirectory() as directory:
            repo = self.make_project(directory)

            created = dispatch(
                [
                    "update-launcher",
                    str(repo),
                    "--tool-source",
                    "alliance-platform-dev==1.1.0",
                ]
            )
            self.assertEqual(created, 0)
            self.assertFalse((repo / "config" / "dev.toml").exists())

            (repo / "bin" / "dev").write_text("custom launcher\n")
            updated = dispatch(
                [
                    "update-launcher",
                    str(repo),
                    "--tool-source",
                    "alliance-platform-dev==1.2.0",
                    "--force",
                ]
            )
            self.assertEqual(updated, 0)
            self.assertIn(
                "default_tool_source=alliance-platform-dev==1.2.0",
                (repo / "bin" / "dev").read_text(),
            )
            self.assertFalse((repo / "config" / "dev.toml").exists())

    def test_launcher_uses_a_stable_cache_for_pypi_git_and_local_tool_sources(self) -> None:
        sources = {
            "pypi": ("alliance-platform-dev==1.2.3", False),
            "git": (
                "git+https://github.com/example/project.git@branch#subdirectory=packages/ap-dev",
                False,
            ),
            "local": ("/tmp/local-ap-dev", True),
            "file-url": ("file:///tmp/local-ap-dev", True),
        }
        for source_type, (source, uses_editable_local_source) in sources.items():
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
                    (
                        "uv",
                        '#!/bin/sh\n{ printf "uv\\n"; printf "%s\\n" "$@"; } > "$CAPTURE_FILE"\n',
                    ),
                    (
                        "uvx",
                        '#!/bin/sh\n{ printf "uvx\\n"; printf "%s\\n" "$@"; } > "$CAPTURE_FILE"\n',
                    ),
                ):
                    executable = fake_bin / name
                    executable.write_text(contents)
                    executable.chmod(0o755)
                capture = repo / "uvx-args"
                environment = dict(os.environ)
                environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
                environment["CAPTURE_FILE"] = str(capture)
                environment["TMPDIR"] = str(repo / "sandbox-tmp")
                environment["XDG_CACHE_HOME"] = str(repo / "cache-home")
                environment.pop("ALLIANCE_DEV_UV_CACHE_DIR", None)
                environment.pop("UV_CACHE_DIR", None)

                subprocess.run([repo / "bin" / "dev", "doctor"], env=environment, check=True)

                runner, *arguments = capture.read_text().splitlines()
                expected_cache = repo / "cache-home" / "alliance-dev" / "uv-cache"
                cache_option = arguments.index("--cache-dir")
                self.assertEqual(arguments[cache_option + 1], str(expected_cache))
                self.assertTrue(expected_cache.is_dir())
                self.assertEqual(expected_cache.stat().st_mode & 0o777, 0o700)
                self.assertEqual(expected_cache.parent.stat().st_mode & 0o777, 0o700)
                self.assertNotIn("--no-cache", arguments)
                self.assertIn("--isolated", arguments)
                self.assertIn("--no-env-file", arguments)
                self.assertIn(source, arguments)
                self.assertEqual(arguments[-2:], ["alliance-dev", "doctor"])
                if uses_editable_local_source:
                    self.assertEqual(runner, "uv")
                    self.assertIn("--no-project", arguments)
                    self.assertIn("--offline", arguments)
                    editable_option = arguments.index("--with-editable")
                    self.assertEqual(arguments[editable_option + 1], source)
                    self.assertNotIn("--from", arguments)
                else:
                    self.assertEqual(runner, "uvx")
                    self.assertNotIn("--no-project", arguments)
                    from_option = arguments.index("--from")
                    self.assertEqual(arguments[from_option + 1], source)
                    self.assertNotIn("--with-editable", arguments)

    def test_launcher_refreshes_a_local_runtime_source_override(self) -> None:
        with TemporaryDirectory() as directory:
            repo = self.make_project(directory)
            install_project(
                repo,
                assume_yes=True,
                tool_source="alliance-platform-dev==1.2.3",
                console=self.console(),
            )
            fake_bin = repo / "fake-bin"
            fake_bin.mkdir()
            for name, contents in (
                (
                    "uv",
                    '#!/bin/sh\n{ printf "uv\\n"; printf "%s\\n" "$@"; } > "$CAPTURE_FILE"\n',
                ),
                ("uvx", '#!/bin/sh\nprintf "%s\\n" "$@" > "$CAPTURE_FILE"\n'),
            ):
                executable = fake_bin / name
                executable.write_text(contents)
                executable.chmod(0o755)
            capture = repo / "uvx-args"
            local_source = repo / "local-ap-dev"
            environment = {
                **os.environ,
                "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                "CAPTURE_FILE": str(capture),
                "ALLIANCE_DEV_TOOL_SOURCE": str(local_source),
            }

            subprocess.run([repo / "bin" / "dev", "doctor"], env=environment, check=True)

            runner, *arguments = capture.read_text().splitlines()
            self.assertEqual(runner, "uv")
            self.assertIn("--offline", arguments)
            self.assertIn(str(local_source), arguments)
            editable_option = arguments.index("--with-editable")
            self.assertEqual(arguments[editable_option + 1], str(local_source))
            self.assertNotIn("--from", arguments)

    def test_local_launcher_falls_back_online_only_when_offline_bootstrap_fails(self) -> None:
        with TemporaryDirectory() as directory:
            repo = self.make_project(directory)
            install_project(
                repo,
                assume_yes=True,
                tool_source="/tmp/local-ap-dev",
                console=self.console(),
            )
            fake_bin = repo / "fake-bin"
            fake_bin.mkdir()
            uv = fake_bin / "uv"
            uv.write_text(
                "#!/bin/sh\n"
                'printf "%s\\n" "$*" >> "$CAPTURE_FILE"\n'
                'for argument in "$@"; do\n'
                '    if [ "$argument" = "--offline" ]; then\n'
                "        exit 1\n"
                "    fi\n"
                "done\n"
            )
            uv.chmod(0o755)
            capture = repo / "uv-calls"
            environment = {
                **os.environ,
                "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                "CAPTURE_FILE": str(capture),
            }

            subprocess.run([repo / "bin" / "dev", "doctor"], env=environment, check=True)

            probe, fallback = capture.read_text().splitlines()
            self.assertIn("--offline", probe)
            self.assertTrue(probe.endswith("alliance-dev --version"))
            self.assertNotIn("--offline", fallback)
            self.assertNotIn("--refresh-package", fallback)
            self.assertTrue(fallback.endswith("alliance-dev doctor"))

    @unittest.skipUnless(shutil.which("uvx"), "uvx is required for cache integration coverage")
    def test_published_launcher_rebuilds_a_real_incomplete_uv_cache(self) -> None:
        with TemporaryDirectory() as directory:
            repo = self.make_project(directory)
            package_index = repo / "simple" / "alliance-platform-dev"
            package_index.mkdir(parents=True)
            wheel = self.make_launcher_test_wheel(package_index)
            (package_index / "index.html").write_text(f'<a href="{wheel.name}">{wheel.name}</a>\n')
            handler = partial(QuietSimpleHTTPRequestHandler, directory=str(repo))
            server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            self.addCleanup(server.server_close)
            self.addCleanup(server.shutdown)
            install_project(
                repo,
                assume_yes=True,
                tool_source="alliance-platform-dev==0.0.2",
                console=self.console(),
            )
            cache = repo / "launcher-cache"
            environment = {
                **os.environ,
                "ALLIANCE_DEV_UV_CACHE_DIR": str(cache),
                "UV_DEFAULT_INDEX": f"http://127.0.0.1:{server.server_port}/simple",
                "UV_PYTHON_DOWNLOADS": "never",
            }
            seeded = subprocess.run(
                [
                    "uvx",
                    "--cache-dir",
                    cache,
                    "--isolated",
                    "--no-env-file",
                    "--from",
                    "alliance-platform-dev==0.0.2",
                    "alliance-dev",
                    "--version",
                ],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(seeded.returncode, 0, seeded.stderr)

            environment_links = [path for path in (cache / "environments-v2").rglob("*") if path.is_symlink()]
            self.assertTrue(environment_links)
            # uv uses absolute environment links on macOS and may use relative
            # links on Linux. Normalize the fixture to the absolute-link cache
            # shape from the reported failure before removing archive files.
            for path in environment_links:
                target = path.resolve(strict=True)
                self.assertTrue(target.is_relative_to(cache / "archive-v0"))
                path.unlink()
                path.symlink_to(target, target_is_directory=True)
            self.assertTrue(all(Path(os.readlink(path)).is_absolute() for path in environment_links))
            archive_files = [
                path for path in (cache / "archive-v0").rglob("*") if path.is_file() and not path.is_symlink()
            ]
            self.assertTrue(archive_files)
            for path in archive_files:
                path.unlink()
            package_links = [
                path
                for path in (cache / "wheels-v6").rglob("*")
                if path.is_symlink() and "alliance-platform-dev" in str(path)
            ]
            self.assertTrue(package_links)
            for path in package_links:
                path.unlink()
            # A local test index retains enough HTTP data to reconstruct a wheel
            # offline. Remove those regular files while retaining the directory
            # shells and environments-v2 symlink from the damaged cache.
            for cache_section in ("wheels-v6", "simple-v20"):
                for path in (cache / cache_section).rglob("*"):
                    if path.is_file() and not path.is_symlink():
                        path.unlink()

            broken_probe = subprocess.run(
                [
                    "uvx",
                    "--cache-dir",
                    cache,
                    "--isolated",
                    "--no-env-file",
                    "--from",
                    "alliance-platform-dev==0.0.2",
                    "--offline",
                    "alliance-dev",
                    "--version",
                ],
                env=environment,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(broken_probe.returncode, 0)

            repaired = subprocess.run(
                [repo / "bin" / "dev", "--version"],
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertIn("bootstrap cache is unavailable or incomplete", repaired.stderr)
            self.assertIn("Moved the incomplete cache", repaired.stderr)
            self.assertIn("launcher test fixture", repaired.stdout)
            rotated_caches = list(repo.glob("launcher-cache.broken-*-*"))
            self.assertEqual(len(rotated_caches), 1)
            rebuilt_archive_files = [
                path for path in (cache / "archive-v0").rglob("*") if path.is_file() and not path.is_symlink()
            ]
            self.assertTrue(rebuilt_archive_files)

            offline = subprocess.run(
                [repo / "bin" / "dev", "--version"],
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("launcher test fixture", offline.stdout)
            self.assertNotIn("rebuilding it", offline.stderr)

    def test_launcher_falls_back_when_the_durable_cache_is_not_a_directory(self) -> None:
        with TemporaryDirectory() as directory:
            repo = self.make_project(directory)
            install_project(
                repo,
                assume_yes=True,
                tool_source="alliance-platform-dev==1.2.3",
                console=self.console(),
            )
            fake_bin = repo / "fake-bin"
            fake_bin.mkdir()
            uvx = fake_bin / "uvx"
            uvx.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$CAPTURE_FILE"\n')
            uvx.chmod(0o755)
            blocked_cache_home = repo / "blocked-cache-home"
            blocked_cache_home.write_text("not a directory")
            temporary_root = repo / "sandbox-tmp"
            capture = repo / "uvx-args"
            environment = {
                **os.environ,
                "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                "CAPTURE_FILE": str(capture),
                "XDG_CACHE_HOME": str(blocked_cache_home),
                "TMPDIR": str(temporary_root),
            }
            environment.pop("ALLIANCE_DEV_UV_CACHE_DIR", None)
            environment.pop("UV_CACHE_DIR", None)

            subprocess.run([repo / "bin" / "dev", "doctor"], env=environment, check=True)

            arguments = capture.read_text().splitlines()
            expected_cache = temporary_root / f"alliance-dev-{os.getuid()}" / "uv-cache"
            self.assertEqual(arguments[arguments.index("--cache-dir") + 1], str(expected_cache))
            self.assertTrue(expected_cache.is_dir())

    def test_local_launcher_does_not_retry_a_failed_delegated_command(self) -> None:
        with TemporaryDirectory() as directory:
            repo = self.make_project(directory)
            install_project(
                repo,
                assume_yes=True,
                tool_source="/tmp/local-ap-dev",
                console=self.console(),
            )
            fake_bin = repo / "fake-bin"
            fake_bin.mkdir()
            uv = fake_bin / "uv"
            uv.write_text(
                "#!/bin/sh\n"
                'printf "%s\\n" "$*" >> "$CAPTURE_FILE"\n'
                'case "$*" in\n'
                '    *"alliance-dev --version") exit 0 ;;\n'
                "    *) exit 23 ;;\n"
                "esac\n"
            )
            uv.chmod(0o755)
            capture = repo / "uv-calls"
            environment = {
                **os.environ,
                "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                "CAPTURE_FILE": str(capture),
            }

            completed = subprocess.run(
                [repo / "bin" / "dev", "doctor"],
                env=environment,
                check=False,
            )

            self.assertEqual(completed.returncode, 23)
            probe, delegated = capture.read_text().splitlines()
            self.assertIn("--offline", probe)
            self.assertTrue(probe.endswith("alliance-dev --version"))
            self.assertIn("--offline", delegated)
            self.assertTrue(delegated.endswith("alliance-dev doctor"))

    def test_launcher_respects_uv_cache_overrides(self) -> None:
        with TemporaryDirectory() as directory:
            repo = self.make_project(directory)
            install_project(
                repo,
                assume_yes=True,
                tool_source="alliance-platform-dev==1.2.3",
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
            environment = {
                **os.environ,
                "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                "CAPTURE_FILE": str(capture),
                "UV_CACHE_DIR": str(repo / "standard-uv-cache"),
            }

            subprocess.run([repo / "bin" / "dev", "doctor"], env=environment, check=True)
            arguments = capture.read_text().splitlines()
            self.assertEqual(
                arguments[arguments.index("--cache-dir") + 1],
                str(repo / "standard-uv-cache" / "alliance-dev-bootstrap"),
            )

            environment["ALLIANCE_DEV_UV_CACHE_DIR"] = str(repo / "launcher-uv-cache")
            subprocess.run([repo / "bin" / "dev", "doctor"], env=environment, check=True)
            arguments = capture.read_text().splitlines()
            self.assertEqual(
                arguments[arguments.index("--cache-dir") + 1],
                str(repo / "launcher-uv-cache"),
            )

    def test_repair_does_not_rotate_the_shared_uv_cache(self) -> None:
        with TemporaryDirectory() as directory:
            repo = self.make_project(directory)
            install_project(
                repo,
                assume_yes=True,
                tool_source="alliance-platform-dev==1.2.3",
                console=self.console(),
            )
            fake_bin = repo / "fake-bin"
            fake_bin.mkdir()
            uvx = fake_bin / "uvx"
            uvx.write_text(
                '#!/bin/sh\ncase "$*" in\n    *"--offline alliance-dev --version") exit 1 ;;\nesac\n'
            )
            uvx.chmod(0o755)
            shared_cache = repo / "shared-uv-cache"
            bootstrap_cache = shared_cache / "alliance-dev-bootstrap"
            bootstrap_cache.mkdir(parents=True)
            (bootstrap_cache / "damaged-entry").write_text("damaged\n")
            shared_entry = shared_cache / "another-tool-entry"
            shared_entry.write_text("keep\n")
            environment = {
                **os.environ,
                "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                "UV_CACHE_DIR": str(shared_cache),
            }
            environment.pop("ALLIANCE_DEV_UV_CACHE_DIR", None)

            subprocess.run([repo / "bin" / "dev", "doctor"], env=environment, check=True)

            self.assertEqual(shared_entry.read_text(), "keep\n")
            self.assertTrue(bootstrap_cache.is_dir())
            rotated = list(shared_cache.glob("alliance-dev-bootstrap.broken-*-*"))
            self.assertEqual(len(rotated), 1)
            self.assertEqual((rotated[0] / "damaged-entry").read_text(), "damaged\n")

    def test_install_ignores_dev_server_state_without_duplicating_existing_entries(self) -> None:
        with TemporaryDirectory() as directory:
            repo = self.make_project(directory)
            gitignore = repo / ".gitignore"
            gitignore.write_text("node_modules/")

            result = install_project(repo, assume_yes=True, console=self.console())

            self.assertIn(gitignore, result.updated)
            self.assertEqual(
                gitignore.read_text(),
                "node_modules/\n\n# Worktree state managed by bin/dev\n.dev-server/\n",
            )

        for existing in (".dev-server", ".dev-server/", "/.dev-server", "/.dev-server/", "**/.dev-server/"):
            with self.subTest(existing=existing), TemporaryDirectory() as directory:
                repo = self.make_project(directory)
                gitignore = repo / ".gitignore"
                contents = f"node_modules/\n  {existing}  \n"
                gitignore.write_text(contents)

                result = install_project(repo, assume_yes=True, console=self.console())

                self.assertIn(gitignore, result.unchanged)
                self.assertEqual(gitignore.read_text(), contents)

        with TemporaryDirectory() as directory:
            repo = self.make_project(directory)
            gitignore = repo / ".gitignore"
            gitignore.write_text("# .dev-server/\n!.dev-server/\n")

            result = install_project(repo, assume_yes=True, console=self.console())

            self.assertIn(gitignore, result.updated)
            self.assertEqual(
                gitignore.read_text(),
                "# .dev-server/\n!.dev-server/\n\n# Worktree state managed by bin/dev\n.dev-server/\n",
            )

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
                    side_effect=["example-app", "", "", ""],
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
