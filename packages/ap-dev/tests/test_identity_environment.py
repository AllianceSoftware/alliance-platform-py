from __future__ import annotations

import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest

from alliance_platform.dev.config import load_config
from alliance_platform.dev.database import DatabaseManager
from alliance_platform.dev.environment import build_control_environment
from alliance_platform.dev.environment import build_managed_environment
from alliance_platform.dev.environment import build_process_environment
from alliance_platform.dev.environment import pane_environment
from alliance_platform.dev.identity import DATABASE_NAME_MAX_LENGTH
from alliance_platform.dev.identity import resolve_identity

from tests.helpers import RecordingRunner
from tests.helpers import init_git
from tests.helpers import make_repo


class WorktreeIdentityTests(unittest.TestCase):
    def test_explicit_project_ids_isolate_projects_with_the_same_package_name(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_repo = make_repo(
                root / "first" / "checkout",
                name="shared-package-name",
                config='project_id = "first-project"\n',
            )
            second_repo = make_repo(
                root / "second" / "checkout",
                name="shared-package-name",
                config='project_id = "second-project"\n',
            )
            environment = {"XDG_CONFIG_HOME": str(root / "xdg")}

            first_config = load_config(first_repo, environment)
            second_config = load_config(second_repo, environment)
            first = resolve_identity(first_repo, first_config)
            second = resolve_identity(second_repo, second_config)

            self.assertNotEqual(first_config.paths.global_, second_config.paths.global_)
            self.assertNotEqual(first.session_name, second.session_name)
            self.assertNotEqual(first.database_name, second.database_name)
            self.assertTrue(first.portless_app_name.endswith(".first-project"))
            self.assertTrue(second.portless_app_name.endswith(".second-project"))

    def test_machine_identity_is_stable_across_branch_changes_and_detached_head(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "checkout")
            init_git(repo, "feature/foo")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})

            initial = resolve_identity(repo, config)
            subprocess.run(["git", "branch", "-m", "feature-foo"], cwd=repo, check=True)
            renamed = resolve_identity(repo, config)
            subprocess.run(["git", "checkout", "--detach", "--quiet"], cwd=repo, check=True)
            detached = resolve_identity(repo, config)

            self.assertEqual(initial.branch, "feature/foo")
            self.assertEqual(renamed.branch, "feature-foo")
            self.assertIsNone(detached.branch)
            for identity in (renamed, detached):
                self.assertEqual(identity.worktree_id, initial.worktree_id)
                self.assertEqual(identity.session_name, initial.session_name)
                self.assertEqual(identity.database_name, initial.database_name)
                self.assertEqual(identity.portless_app_name, initial.portless_app_name)

    def test_canonical_and_symlinked_paths_have_the_same_identity(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "checkout")
            init_git(repo, "main")
            alias = root / "checkout-alias"
            alias.symlink_to(repo, target_is_directory=True)
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})

            canonical = resolve_identity(repo, config)
            through_alias = resolve_identity(alias, config)

            self.assertEqual(through_alias, canonical)

    def test_slug_colliding_branches_in_same_named_directories_remain_distinct(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_repo = make_repo(root / "first" / "checkout")
            second_repo = make_repo(root / "second" / "checkout")
            init_git(first_repo, "feature/foo")
            init_git(second_repo, "feature-foo")
            environment = {"XDG_CONFIG_HOME": str(root / "xdg")}

            first = resolve_identity(first_repo, load_config(first_repo, environment))
            second = resolve_identity(second_repo, load_config(second_repo, environment))

            self.assertNotEqual(first.worktree_id, second.worktree_id)
            self.assertNotEqual(first.session_name, second.session_name)
            self.assertNotEqual(first.database_name, second.database_name)
            self.assertRegex(first.worktree_id, r"^checkout-[0-9a-f]{10}$")
            self.assertRegex(second.worktree_id, r"^checkout-[0-9a-f]{10}$")

    def test_database_names_stay_safe_and_distinct_after_truncation(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            project_id = ("project-" + "very-long-" * 10).rstrip("-")
            config_body = f'project_id = "{project_id}"\n'
            first_repo = make_repo(root / "first" / ("checkout-" + "a" * 50), config=config_body)
            second_repo = make_repo(root / "second" / ("checkout-" + "a" * 50), config=config_body)
            environment = {"XDG_CONFIG_HOME": str(root / "xdg")}

            first = resolve_identity(first_repo, load_config(first_repo, environment))
            second = resolve_identity(second_repo, load_config(second_repo, environment))

            self.assertLessEqual(len(first.database_name), DATABASE_NAME_MAX_LENGTH)
            self.assertLessEqual(len("test_" + first.database_name + "_9999"), 63)
            self.assertRegex(first.database_name, r"^[a-z0-9_]+$")
            self.assertNotEqual(first.database_name, second.database_name)

    def test_managed_database_environment_reserves_parallel_django_clone_suffixes(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(
                root / "cleanbins-bin-dev-long-worktree-name",
                config='project_id = "clean-bins-waste-comp-platform"\n',
            )
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = resolve_identity(repo, config)

            environment = build_managed_environment(repo, config.project_slug, identity, {})

            test_database = f"test_{environment['DB_NAME']}"
            clone_databases = [f"{test_database}_{worker}" for worker in range(1, 5)]
            self.assertEqual(environment["PGDATABASE"], environment["DB_NAME"])
            self.assertLessEqual(len(test_database), 63)
            self.assertTrue(all(len(name) <= 63 for name in clone_databases))
            self.assertEqual(len({test_database, *clone_databases}), 5)


class EnvironmentBoundaryTests(unittest.TestCase):
    def test_launcher_runtime_does_not_leak_into_application_environment(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            launcher_environment = {
                "PATH": "/repo/tools/dev/.venv/bin:/original/bin",
                "VIRTUAL_ENV": "/repo/tools/dev/.venv",
                "UV_RUN_RECURSION_DEPTH": "1",
                "DEV_INVOKE_PATH": "/original/bin",
                "DEV_INVOKE_VIRTUAL_ENV": "/original/.venv",
                "DEV_INVOKE_VIRTUAL_ENV_SET": "1",
                "DEV_INVOKE_UV_RUN_RECURSION_DEPTH": "",
                "DEV_INVOKE_UV_RUN_RECURSION_DEPTH_SET": "0",
                "ALLIANCE_DEV_PROJECT_DIR": str(repo),
                "ALLIANCE_DEV_INVOCATION_NAME": "bin/dev",
                "ALLIANCE_DEV_UV_CACHE_DIR": "/tmp/launcher-only-cache",
            }

            process = build_process_environment(config, inherited=launcher_environment)
            control = build_control_environment(repo, config, inherited=launcher_environment)

            for environment in (process, control):
                self.assertEqual(environment["PATH"], "/original/bin")
                self.assertEqual(environment["VIRTUAL_ENV"], "/original/.venv")
                self.assertNotIn("UV_RUN_RECURSION_DEPTH", environment)
                launcher_markers = set(launcher_environment) - {
                    "PATH",
                    "VIRTUAL_ENV",
                    "UV_RUN_RECURSION_DEPTH",
                }
                self.assertTrue(
                    launcher_markers.isdisjoint(environment),
                    launcher_markers & set(environment),
                )

    def test_process_and_control_environments_have_explicit_precedence_and_separation(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(
                root / "repo",
                config="""
[environment]
CONFIG_ONLY = "config"
SHARED = "config"
DB_HOST = "toml-db.local"
""".lstrip(),
            )
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            (repo / ".env").write_text(
                "ENV_ONLY=env\n"
                "SHARED=env\n"
                "DB_HOST=dotenv-db.local\n"
                "DB_PORT=5433\n"
                "DB_USER=dotenv-user\n"
                "DB_PASSWORD=dotenv-password\n"
                'QUOTED="value # retained"\n'
                "PLAIN=value # removed\n"
            )

            process = build_process_environment(config, inherited={})
            control = build_control_environment(repo, config, inherited={})
            shell_control = build_control_environment(
                repo,
                config,
                inherited={
                    "SHARED": "shell",
                    "SHELL_ONLY": "shell",
                    "DB_HOST": "shell-db.local",
                    "PGHOST": "explicit-pg.local",
                },
            )

            self.assertEqual(process["CONFIG_ONLY"], "config")
            self.assertEqual(process["SHARED"], "config")
            self.assertNotIn("ENV_ONLY", process)
            self.assertNotIn("QUOTED", process)
            self.assertEqual(control["ENV_ONLY"], "env")
            self.assertEqual(control["SHARED"], "config")
            self.assertEqual(control["DB_HOST"], "toml-db.local")
            self.assertEqual(control["PGHOST"], "toml-db.local")
            self.assertEqual(control["PGPORT"], "5433")
            self.assertEqual(control["PGUSER"], "dotenv-user")
            self.assertEqual(control["PGPASSWORD"], "dotenv-password")
            self.assertEqual(control["QUOTED"], "value # retained")
            self.assertEqual(control["PLAIN"], "value")
            self.assertEqual(shell_control["SHARED"], "shell")
            self.assertEqual(shell_control["SHELL_ONLY"], "shell")
            self.assertEqual(shell_control["DB_HOST"], "shell-db.local")
            self.assertEqual(shell_control["PGHOST"], "explicit-pg.local")

    def test_pane_environment_removes_tmux_client_state(self) -> None:
        environment = pane_environment(
            {
                "TERM": "xterm-256color",
                "TMUX": "/tmp/client",
                "TMUX_PANE": "%1",
                "TMUX_TMPDIR": "/tmp/tmux",
                "KEEP": "value",
            }
        )

        self.assertEqual(environment, {"KEEP": "value"})

    def test_managed_environment_has_one_identity_contract_for_foreground_and_panes(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = resolve_identity(repo, config)
            inherited = {
                "DB_NAME": "wrong",
                "PGDATABASE": "wrong",
                "DEV_BASE_HOST": "wrong",
                "DEV_PROJECT": "wrong",
                "DEV_WORKTREE": "/wrong",
                "DEV_WORKTREE_ID": "wrong",
                "DEV_DJANGO_PORT": "9999",
                "DEV_VITE_PORT": "9998",
                "PYTHONPATH": "/existing/pythonpath",
                "TERM": "xterm-256color",
                "TMUX": "/tmp/client",
                "KEEP": "value",
            }

            foreground = build_managed_environment(
                repo,
                config.project_slug,
                identity,
                inherited,
            )
            pane = build_managed_environment(
                repo,
                config.project_slug,
                identity,
                inherited,
                dev_base_host="repo.test",
                django_port=8001,
                vite_port=5174,
                for_pane=True,
            )

            for environment in (foreground, pane):
                self.assertEqual(environment["DB_NAME"], identity.database_name)
                self.assertEqual(environment["PGDATABASE"], identity.database_name)
                self.assertEqual(environment["DEV_PROJECT"], config.project_slug)
                self.assertEqual(environment["DEV_WORKTREE"], str(repo))
                self.assertEqual(environment["DEV_WORKTREE_ID"], identity.worktree_id)
                self.assertEqual(
                    environment["PYTHONPATH"],
                    f"{repo}{os.pathsep}/existing/pythonpath",
                )
                self.assertEqual(environment["KEEP"], "value")
            self.assertEqual(foreground["DEV_BASE_HOST"], "")
            self.assertNotIn("DEV_DJANGO_PORT", foreground)
            self.assertNotIn("DEV_VITE_PORT", foreground)
            self.assertEqual(foreground["TERM"], "xterm-256color")
            self.assertEqual(foreground["TMUX"], "/tmp/client")
            self.assertEqual(pane["DEV_BASE_HOST"], "repo.test")
            self.assertEqual(pane["DEV_DJANGO_PORT"], "8001")
            self.assertEqual(pane["DEV_VITE_PORT"], "5174")
            self.assertNotIn("TERM", pane)
            self.assertNotIn("TMUX", pane)

    def test_generated_database_values_replace_inherited_process_values(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = resolve_identity(repo, config)
            process_environment = build_process_environment(
                config,
                inherited={
                    "DB_NAME": "wrong",
                    "PGDATABASE": "wrong",
                    "DEV_BASE_HOST": "wrong",
                },
            )
            manager = DatabaseManager(
                RecordingRunner(),
                repo,
                config,
                identity,
                process_environment,
                {},
            )
            managed = manager.managed_environment("correct.localhost")

            self.assertEqual(managed["DB_NAME"], identity.database_name)
            self.assertEqual(managed["PGDATABASE"], identity.database_name)
            self.assertEqual(managed["DEV_BASE_HOST"], "correct.localhost")


if __name__ == "__main__":
    unittest.main()
