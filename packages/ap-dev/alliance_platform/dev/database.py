from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from typing import Sequence

from .errors import DevError
from .models import DevConfig
from .models import WorktreeIdentity
from .runner import CommandResult
from .runner import Runner
from .runner import require_success


@dataclass(frozen=True)
class DatabasePreparationResult:
    created: bool


class DatabaseManager:
    def __init__(
        self,
        runner: Runner,
        repo: Path,
        config: DevConfig,
        identity: WorktreeIdentity,
        process_environment: dict[str, str],
        control_environment: dict[str, str],
    ):
        self.runner = runner
        self.repo = repo
        self.project_dir = (repo / config.django_cwd).resolve()
        self.config = config
        self.identity = identity
        self.process_environment = process_environment
        self.control_environment = control_environment
        self._force_drop_supported: bool | None = None

    def postgres_environment(self) -> dict[str, str]:
        environment = dict(self.control_environment)
        environment.pop("PGDATABASE", None)
        return environment

    def managed_environment(self, dev_base_host: str = "") -> dict[str, str]:
        environment = dict(self.process_environment)
        environment.update(
            {
                "DB_NAME": self.identity.database_name,
                "PGDATABASE": self.identity.database_name,
                "DEV_BASE_HOST": dev_base_host,
            }
        )
        return environment

    def require_tools(self) -> None:
        # dropdb is part of startup safety: a newly-created database must be
        # removable if migrations, seeding, or readiness later fails.
        commands = ["psql", "createdb", "dropdb"]
        missing = [
            command for command in commands if self.runner.which(command, self.control_environment) is None
        ]
        if missing:
            raise DevError(f"Missing PostgreSQL command(s): {', '.join(missing)}")
        self.require_force_drop_support()

    def require_force_drop_support(self) -> None:
        if self.runner.which("dropdb", self.control_environment) is None:
            raise DevError("Missing PostgreSQL command 'dropdb'")
        if not self.supports_force_drop():
            raise DevError(
                "Installed 'dropdb' does not support --force. Upgrade the PostgreSQL client tools; "
                "forced connection termination is required for safe database cleanup."
            )

    def supports_force_drop(self) -> bool:
        if self._force_drop_supported is None:
            if self.runner.which("dropdb", self.control_environment) is None:
                self._force_drop_supported = False
            else:
                result = self.runner.run(
                    ["dropdb", "--help"],
                    env=self.postgres_environment(),
                    capture=True,
                )
                self._force_drop_supported = result.returncode == 0 and "--force" in result.stdout
        return self._force_drop_supported

    def exists(self, name: str) -> bool:
        if self.runner.which("psql", self.control_environment) is None:
            raise DevError("Missing PostgreSQL command 'psql'")
        escaped = name.replace("'", "''")
        result = self.runner.run(
            [
                "psql",
                "--no-psqlrc",
                "--dbname=postgres",
                "--tuples-only",
                "--no-align",
                "--command",
                f"SELECT 1 FROM pg_database WHERE datname = '{escaped}'",
            ],
            env=self.postgres_environment(),
            capture=True,
        )
        if result.returncode != 0:
            raise DevError(f"Could not query PostgreSQL databases:\n{result.stdout.rstrip()}")
        return "1" in result.stdout.splitlines()

    def run_manage(
        self,
        args: Sequence[str],
        *,
        dev_base_host: str = "",
        capture: bool = False,
    ) -> CommandResult:
        if not self.project_dir.is_dir():
            raise DevError(f"Configured django_cwd does not exist: {self.config.django_cwd}")
        return self.runner.run(
            [*self.config.manage_command, *args],
            cwd=self.project_dir,
            env=self.managed_environment(dev_base_host),
            capture=capture,
        )

    def ensure(
        self,
        *,
        on_database_creation: Callable[[], None] | None = None,
        dev_base_host: str = "",
    ) -> DatabasePreparationResult:
        self.require_tools()
        name = self.identity.database_name
        created = False
        if not self.exists(name):
            if self.config.database_template:
                template = self.config.database_template
                if template == name:
                    raise DevError("database_template must not be the worktree database")
                if not self.exists(template):
                    raise DevError(f"Configured database template '{template}' does not exist")
                if on_database_creation:
                    on_database_creation()
                result = self.runner.run(
                    ["createdb", f"--template={template}", name],
                    env=self.postgres_environment(),
                )
                require_success(result, f"Creating database {name}")
                created = True
            else:
                if on_database_creation:
                    on_database_creation()
                result = self.runner.run(["createdb", name], env=self.postgres_environment())
                require_success(result, f"Creating database {name}")
                created = True

        # Migrations deliberately run on every startup. Seeding and the prepare
        # hook remain creation-only.
        require_success(
            self.run_manage(["migrate", "--noinput"]),
            "Django migrations",
        )
        if created and not self.config.database_template:
            require_success(
                self.run_manage(
                    ["createdevdata", *self.config.createdevdata_args],
                ),
                "Creating development data",
            )
        if created and self.config.db_prepare_command:
            require_success(
                self.run_manage(
                    list(self.config.db_prepare_command),
                    dev_base_host=dev_base_host,
                ),
                "Preparing worktree database",
            )
        return DatabasePreparationResult(created=created)

    def drop(self, name: str | None = None) -> bool:
        name = name or self.identity.database_name
        if not self.exists(name):
            return False
        self.require_force_drop_support()
        args = ["dropdb", "--if-exists", "--force", name]
        require_success(
            self.runner.run(args, env=self.postgres_environment()),
            f"Dropping database {name}",
        )
        return True
