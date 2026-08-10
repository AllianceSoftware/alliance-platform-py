from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Sequence
import unittest
from unittest.mock import patch

from alliance_platform.dev.config import load_config
from alliance_platform.dev.database import DATABASE_CLONE_DOCS_URL
from alliance_platform.dev.database import DatabaseManager
from alliance_platform.dev.environment import build_control_environment
from alliance_platform.dev.environment import build_process_environment
from alliance_platform.dev.errors import DevError
from alliance_platform.dev.models import WorktreeIdentity
from alliance_platform.dev.runner import CommandResult

from tests.helpers import RecordedCall
from tests.helpers import RecordingRunner
from tests.helpers import make_repo


class DatabaseRunner(RecordingRunner):
    def __init__(
        self,
        existence: Sequence[bool],
        *,
        fail_manage: str | None = None,
        fail_createdb: bool = False,
        supports_force_drop: bool = True,
    ) -> None:
        super().__init__(available=("psql", "createdb", "dropdb"))
        self.existence = list(existence)
        self.fail_manage = fail_manage
        self.fail_createdb = fail_createdb
        self.supports_force_drop = supports_force_drop

    def run(
        self,
        args: Sequence[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        capture: bool = False,
        input_text: str | None = None,
    ) -> CommandResult:
        self.calls.append(
            RecordedCall(tuple(args), cwd, dict(env) if env is not None else None, capture, input_text)
        )
        if tuple(args[:2]) == ("dropdb", "--help"):
            output = "  --force  try to terminate other connections\n" if self.supports_force_drop else ""
            return CommandResult(0, output)
        if args[0] == "psql":
            return CommandResult(0, "1\n" if self.existence.pop(0) else "")
        if args[0] == "createdb" and self.fail_createdb:
            return CommandResult(1, "connection lost after request")
        if self.fail_manage and self.fail_manage in args:
            return CommandResult(1, "managed failure")
        return CommandResult(0, "")


class DatabaseLifecycleTests(unittest.TestCase):
    def manager(
        self,
        root: Path,
        runner: DatabaseRunner,
        *,
        config_body: str = "",
    ) -> DatabaseManager:
        repo = make_repo(root / "repo", config=config_body)
        config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
        identity = WorktreeIdentity(
            repo=repo,
            branch="feature/example",
            worktree_id="repo-0123456789",
            session_name="demo-project-wt-repo-0123456789",
            database_name="demo_project_repo_0123456789",
            portless_app_name="repo-0123456789.demo-project",
        )
        return DatabaseManager(
            runner,
            repo,
            config,
            identity,
            {
                "PROCESS_ONLY": "process",
                "DB_NAME": "must-not-win",
                "PGDATABASE": "must-not-win",
            },
            {
                "CONTROL_ONLY": "control",
                "PGHOST": "db.local",
                "PGUSER": "developer",
                "PGDATABASE": "must-not-win",
            },
        )

    def test_existing_database_is_migrated_without_seeding(self) -> None:
        with TemporaryDirectory() as temporary:
            runner = DatabaseRunner([True])
            manager = self.manager(Path(temporary), runner)

            result = manager.ensure()

            self.assertFalse(result.created)
            manage_calls = [call for call in runner.calls if "manage.py" in call.args]
            self.assertEqual(
                [call.args for call in manage_calls],
                [("uv", "run", "python", "manage.py", "migrate", "--noinput")],
            )
            assert manage_calls[0].env is not None
            self.assertEqual(manage_calls[0].env["DB_NAME"], "demo_project_repo_0123456789")
            self.assertEqual(manage_calls[0].env["PGDATABASE"], "demo_project_repo_0123456789")
            self.assertEqual(manage_calls[0].env["DEV_BASE_HOST"], "")
            self.assertEqual(manage_calls[0].env["PROCESS_ONLY"], "process")
            self.assertNotIn("CONTROL_ONLY", manage_calls[0].env)
            postgres_call = next(call for call in runner.calls if call.args[0] == "psql")
            assert postgres_call.env is not None
            self.assertEqual(postgres_call.env["CONTROL_ONLY"], "control")
            self.assertNotIn("PROCESS_ONLY", postgres_call.env)
            self.assertNotIn("PGDATABASE", postgres_call.env)

    def test_manage_uses_the_configured_argv_and_django_working_directory(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = DatabaseRunner([])
            manager = self.manager(
                root,
                runner,
                config_body=(
                    'django_cwd = "backend"\n'
                    'manage_command = ["project-python", "manage.py", "--settings=dev"]\n'
                ),
            )
            manager.project_dir.mkdir()

            manager.run_manage(["check", "--deploy"])

            self.assertEqual(
                runner.calls[-1].args,
                ("project-python", "manage.py", "--settings=dev", "check", "--deploy"),
            )
            self.assertEqual(runner.calls[-1].cwd, manager.project_dir)

    def test_dotenv_only_values_reach_postgres_but_not_manage_parent(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = make_repo(root / "repo")
            (repo / ".env").write_text("DOTENV_ONLY=database-control\nDB_HOST=dotenv-db.local\n")
            config = load_config(repo, {"XDG_CONFIG_HOME": str(root / "xdg")})
            identity = WorktreeIdentity(
                repo=repo,
                branch="feature/example",
                worktree_id="repo-0123456789",
                session_name="demo-project-wt-repo-0123456789",
                database_name="demo_project_repo_0123456789",
                portless_app_name="repo-0123456789.demo-project",
            )
            runner = DatabaseRunner([True])
            manager = DatabaseManager(
                runner,
                repo,
                config,
                identity,
                build_process_environment(config, inherited={}),
                build_control_environment(repo, config, inherited={}),
            )

            manager.ensure()

            postgres_call = next(call for call in runner.calls if call.args[0] == "psql")
            manage_call = next(call for call in runner.calls if "manage.py" in call.args)
            assert postgres_call.env is not None
            assert manage_call.env is not None
            self.assertEqual(postgres_call.env["DOTENV_ONLY"], "database-control")
            self.assertEqual(postgres_call.env["PGHOST"], "dotenv-db.local")
            self.assertNotIn("DOTENV_ONLY", manage_call.env)
            self.assertNotIn("PGHOST", manage_call.env)

    def test_startup_requires_dropdb_before_it_can_create_or_modify_a_database(self) -> None:
        with TemporaryDirectory() as temporary:
            runner = DatabaseRunner([False])
            runner.available.remove("dropdb")
            manager = self.manager(Path(temporary), runner)

            with self.assertRaisesRegex(DevError, "dropdb"):
                manager.ensure()

            self.assertEqual(runner.calls, [])

    def test_startup_requires_forced_connection_termination_support(self) -> None:
        with TemporaryDirectory() as temporary:
            runner = DatabaseRunner([False], supports_force_drop=False)
            manager = self.manager(Path(temporary), runner)

            with self.assertRaisesRegex(DevError, "does not support --force.*Upgrade"):
                manager.ensure()

            self.assertFalse(any(call.args[0] in {"psql", "createdb"} for call in runner.calls))

    def test_fresh_database_runs_create_migrate_seed_and_prepare_in_order(self) -> None:
        with TemporaryDirectory() as temporary:
            runner = DatabaseRunner([False])
            manager = self.manager(
                Path(temporary),
                runner,
                config_body=(
                    'createdevdata_args = ["--size", "small value"]\n'
                    'db_prepare_command = ["prepare_worktree_db", "--safe"]\n'
                ),
            )

            marker_was_persisted: list[bool] = []

            def database_creation_started() -> None:
                marker_was_persisted.append(True)
                self.assertFalse(any(call.args[0] == "createdb" for call in runner.calls))

            result = manager.ensure(on_database_creation=database_creation_started)

            lifecycle = [call.args for call in runner.calls if call.args[0] in {"createdb", "uv"}]
            self.assertEqual(
                lifecycle,
                [
                    ("createdb", "demo_project_repo_0123456789"),
                    ("uv", "run", "python", "manage.py", "migrate", "--noinput"),
                    (
                        "uv",
                        "run",
                        "python",
                        "manage.py",
                        "createdevdata",
                        "--size",
                        "small value",
                    ),
                    ("uv", "run", "python", "manage.py", "prepare_worktree_db", "--safe"),
                ],
            )
            self.assertTrue(result.created)
            self.assertEqual(marker_was_persisted, [True])
            for call in (call for call in runner.calls if "manage.py" in call.args):
                assert call.env is not None
                self.assertEqual(call.env["DEV_BASE_HOST"], "")
            createdb = next(call for call in runner.calls if call.args[0] == "createdb")
            assert createdb.env is not None
            self.assertEqual(createdb.env["CONTROL_ONLY"], "control")
            self.assertNotIn("PROCESS_ONLY", createdb.env)

    def test_template_database_is_verified_and_never_seeded(self) -> None:
        with TemporaryDirectory() as temporary:
            runner = DatabaseRunner([False, True])
            manager = self.manager(
                Path(temporary),
                runner,
                config_body=(
                    'database_template = "seed template"\ndb_prepare_command = ["prepare_worktree_db"]\n'
                ),
            )

            result = manager.ensure()

            calls = [call.args for call in runner.calls]
            self.assertIn(
                ("createdb", "--template=seed template", "demo_project_repo_0123456789"),
                calls,
            )
            self.assertFalse(any("createdevdata" in call for call in calls))
            self.assertTrue(result.created)

    def test_template_clone_and_preparation_stages_report_timed_progress(self) -> None:
        with TemporaryDirectory() as temporary:
            runner = DatabaseRunner([False, True])
            manager = self.manager(
                Path(temporary),
                runner,
                config_body=(
                    'database_template = "seed_template"\ndb_prepare_command = ["prepare_worktree_db"]\n'
                ),
            )
            messages: list[str] = []

            with patch(
                "alliance_platform.dev.database.time.monotonic",
                side_effect=[10.0, 72.0, 80.0, 81.25, 90.0, 92.5],
            ):
                manager.ensure(on_progress=messages.append)

            self.assertEqual(
                messages,
                [
                    (
                        "Cloning database 'seed_template' → "
                        "'demo_project_repo_0123456789' "
                        "(strategy: PostgreSQL default; this may take a while)..."
                    ),
                    (
                        "Hint: For faster local template clones, consider "
                        'database_template_strategy = "file_copy". '
                        f"Learn about PostgreSQL copy-on-write setup: {DATABASE_CLONE_DOCS_URL}"
                    ),
                    "Database cloned (62.0s).",
                    "Running Django migrations...",
                    "Django migrations complete (1.2s).",
                    "Preparing the worktree database...",
                    "Worktree database prepared (2.5s).",
                ],
            )

    def test_explicit_template_strategy_is_passed_without_the_default_hint(self) -> None:
        with TemporaryDirectory() as temporary:
            runner = DatabaseRunner([False, True])
            manager = self.manager(
                Path(temporary),
                runner,
                config_body=(
                    'database_template = "seed_template"\ndatabase_template_strategy = "file_copy"\n'
                ),
            )
            messages: list[str] = []

            manager.ensure(on_progress=messages.append)

            self.assertIn(
                (
                    "createdb",
                    "--template=seed_template",
                    "--strategy=file_copy",
                    "demo_project_repo_0123456789",
                ),
                [call.args for call in runner.calls],
            )
            self.assertTrue(any("strategy: FILE_COPY" in message for message in messages))
            self.assertFalse(any(message.startswith("Hint:") for message in messages))

    def test_prepare_command_receives_the_selected_worktree_base_host(self) -> None:
        with TemporaryDirectory() as temporary:
            runner = DatabaseRunner([False])
            manager = self.manager(
                Path(temporary),
                runner,
                config_body='db_prepare_command = ["prepare_worktree_db"]\n',
            )

            manager.ensure(dev_base_host="checkout.demo.localhost")

            prepare = next(call for call in runner.calls if "prepare_worktree_db" in call.args)
            migrate = next(call for call in runner.calls if "migrate" in call.args)
            seed = next(call for call in runner.calls if "createdevdata" in call.args)
            assert prepare.env is not None
            assert migrate.env is not None
            assert seed.env is not None
            self.assertEqual(prepare.env["DEV_BASE_HOST"], "checkout.demo.localhost")
            self.assertEqual(migrate.env["DEV_BASE_HOST"], "")
            self.assertEqual(seed.env["DEV_BASE_HOST"], "")

    def test_failure_after_createdb_leaves_persisted_marker_as_cleanup_ownership(self) -> None:
        with TemporaryDirectory() as temporary:
            runner = DatabaseRunner([False], fail_manage="migrate")
            manager = self.manager(Path(temporary), runner)
            ownership_markers: list[bool] = []

            with self.assertRaisesRegex(DevError, "Django migrations failed"):
                manager.ensure(on_database_creation=lambda: ownership_markers.append(True))

            self.assertEqual(ownership_markers, [True])

    def test_uncertain_createdb_result_still_establishes_cleanup_ownership(self) -> None:
        with TemporaryDirectory() as temporary:
            runner = DatabaseRunner([False], fail_createdb=True)
            manager = self.manager(Path(temporary), runner)
            ownership_markers: list[bool] = []

            with self.assertRaisesRegex(DevError, "Creating database.*failed"):
                manager.ensure(on_database_creation=lambda: ownership_markers.append(True))

            self.assertEqual(ownership_markers, [True])
            self.assertFalse(any("manage.py" in call.args for call in runner.calls))

    def test_drop_uses_the_derived_identity_and_forces_connection_termination(self) -> None:
        with TemporaryDirectory() as temporary:
            runner = DatabaseRunner([True])
            manager = self.manager(Path(temporary), runner)

            manager.drop()

            self.assertIn(
                ("dropdb", "--if-exists", "--force", "demo_project_repo_0123456789"),
                [call.args for call in runner.calls],
            )


if __name__ == "__main__":
    unittest.main()
