from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from typing import Protocol
from typing import Sequence

from .errors import DevError


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""


class Runner(Protocol):
    def run(
        self,
        args: Sequence[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        capture: bool = False,
        input_text: str | None = None,
    ) -> CommandResult: ...

    def which(self, command: str, env: dict[str, str] | None = None) -> str | None: ...


class SubprocessRunner:
    def run(
        self,
        args: Sequence[str],
        *,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        capture: bool = False,
        input_text: str | None = None,
    ) -> CommandResult:
        try:
            result = subprocess.run(
                list(args),
                cwd=cwd,
                env=env,
                check=False,
                text=True,
                input=input_text,
                stdout=subprocess.PIPE if capture else None,
                stderr=subprocess.STDOUT if capture else None,
            )
        except FileNotFoundError as error:
            raise DevError(f"Missing command '{args[0]}'") from error
        return CommandResult(result.returncode, result.stdout or "")

    def which(self, command: str, env: dict[str, str] | None = None) -> str | None:
        return shutil.which(command, path=(env or {}).get("PATH"))


def require_success(result: CommandResult, description: str) -> None:
    if result.returncode != 0:
        detail = f"\n{result.stdout.rstrip()}" if result.stdout else ""
        raise DevError(f"{description} failed (exit {result.returncode}){detail}")
