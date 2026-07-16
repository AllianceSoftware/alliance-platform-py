from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
from typing import Sequence

from alliance_platform.dev.runner import CommandResult


def make_repo(
    root: Path,
    *,
    name: str = "demo-project",
    config: str = "",
    include_project_id: bool = True,
) -> Path:
    repo = root
    (repo / "config").mkdir(parents=True, exist_ok=True)
    (repo / "django-root").mkdir(exist_ok=True)
    (repo / "pyproject.toml").write_text(f'[project]\nname = "{name}"\n')
    if include_project_id and re.search(r"(?m)^project_id\s*=", config) is None:
        project_id = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        config = f'project_id = "{project_id}"\n{config}'
    (repo / "config" / "dev.toml").write_text(config)
    return repo


def init_git(repo: Path, branch: str) -> None:
    commands = [
        ["git", "init", "--quiet"],
        ["git", "config", "user.email", "dev-tests@example.invalid"],
        ["git", "config", "user.name", "Dev Tests"],
        ["git", "config", "core.hooksPath", "/dev/null"],
        ["git", "symbolic-ref", "HEAD", f"refs/heads/{branch}"],
        ["git", "add", "pyproject.toml", "config/dev.toml"],
        ["git", "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "initial"],
    ]
    for command in commands:
        subprocess.run(command, cwd=repo, check=True, capture_output=True, text=True)


@dataclass(frozen=True)
class RecordedCall:
    args: tuple[str, ...]
    cwd: Path | None
    env: dict[str, str] | None
    capture: bool
    input_text: str | None


class RecordingRunner:
    def __init__(
        self,
        results: Sequence[CommandResult] = (),
        available: Sequence[str] = (),
    ) -> None:
        self.results = list(results)
        self.available = set(available)
        self.calls: list[RecordedCall] = []

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
        if self.results:
            return self.results.pop(0)
        return CommandResult(0, "")

    def which(self, command: str, env: dict[str, str] | None = None) -> str | None:
        del env
        return f"/fake/{command}" if command in self.available else None
