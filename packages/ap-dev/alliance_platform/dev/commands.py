from __future__ import annotations

import os
from pathlib import Path
from typing import NoReturn
from typing import Sequence

from . import invocation_name
from .environment import build_managed_environment
from .environment import build_verification_environment
from .errors import DevError
from .models import DevConfig
from .models import WorktreeIdentity


class CommandDelegates:
    """Exec foreground commands without interpreting their arguments."""

    def __init__(
        self,
        repo: Path,
        config: DevConfig,
        identity: WorktreeIdentity,
        environment: dict[str, str],
    ):
        self.repo = repo
        self.config = config
        self.identity = identity
        self.environment = dict(environment)

    def _managed_environment(
        self,
        *,
        verification: bool = False,
        python_verification: bool = False,
    ) -> dict[str, str]:
        environment = build_managed_environment(
            self.repo,
            self.config.project_slug,
            self.identity,
            self.environment,
        )
        if verification:
            environment["DISABLE_SSR"] = "1"
        if python_verification:
            environment = build_verification_environment(
                self.repo,
                self.config.verification_virtualenv,
                environment,
            )
        return environment

    def _working_directory(self, value: str) -> Path:
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = self.repo / candidate
        candidate = candidate.resolve()
        try:
            candidate.relative_to(self.repo.resolve())
        except ValueError as error:
            raise DevError(f"Run working directory must be inside the repository: {value}") from error
        if not candidate.is_dir():
            raise DevError(f"Run working directory does not exist or is not a directory: {value}")
        return candidate

    def _exec_argv(
        self,
        configured: Sequence[str],
        args: Sequence[str] = (),
        *,
        cwd: Path | None = None,
        environment: dict[str, str] | None = None,
        verification: bool = False,
        python_verification: bool = False,
    ) -> NoReturn:
        argv = [*configured, *args]
        command_environment = (
            dict(environment)
            if environment is not None
            else self._managed_environment(
                verification=verification,
                python_verification=python_verification,
            )
        )
        try:
            os.chdir(self.repo if cwd is None else cwd)
            os.execvpe(argv[0], argv, command_environment)
        except FileNotFoundError as error:
            raise DevError(f"Missing command '{argv[0]}'") from error
        raise AssertionError("exec unexpectedly returned")

    def _verification_command(self, name: str, configured: Sequence[str]) -> Sequence[str]:
        if not configured:
            raise DevError(
                f"{name} is not configured for this project. "
                f"Set {name}_command in config/dev.toml, then run {invocation_name()} doctor."
            )
        return configured

    def test(self, args: Sequence[str]) -> NoReturn:
        self._exec_argv(
            self._verification_command("test", self.config.test_command),
            args,
            verification=True,
            python_verification=True,
        )

    def jstest(self, args: Sequence[str]) -> NoReturn:
        self._exec_argv(self._verification_command("jstest", self.config.jstest_command), args)

    def lint(self, args: Sequence[str]) -> NoReturn:
        self._exec_argv(
            self._verification_command("lint", self.config.lint_command),
            args,
            verification=True,
            python_verification=True,
        )

    def check(self) -> NoReturn:
        self._exec_argv(
            self._verification_command("check", self.config.check_command),
            verification=True,
            python_verification=True,
        )

    def run(
        self,
        args: Sequence[str],
        *,
        cwd: str,
        environment: dict[str, str],
    ) -> NoReturn:
        if not args:
            raise DevError(f"Usage: {invocation_name()} run [--cwd PATH] -- <command> [args...]")
        self._exec_argv(
            tuple(args),
            cwd=self._working_directory(cwd),
            environment=environment,
        )
