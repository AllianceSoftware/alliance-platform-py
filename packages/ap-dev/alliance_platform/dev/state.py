from __future__ import annotations

from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import time
from typing import ContextManager
from typing import Iterator

from .errors import DevError
from .models import PersistedState


class StateStore:
    def __init__(self, repo: Path):
        self.directory = repo / ".dev-server"
        self.state_path = self.directory / "state.json"
        self.log_directory = self.directory / "logs"

    def ensure(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)

    def load(self) -> PersistedState | None:
        if not self.state_path.exists():
            return None
        try:
            value = json.loads(self.state_path.read_text())
            return PersistedState.from_dict(value)
        except (OSError, ValueError) as error:
            raise DevError(
                f"Invalid dev state in {self.state_path}: {error}. Clear this file after "
                "confirming no interrupted database setup needs recovery, then retry."
            ) from error

    def save(self, state: PersistedState) -> None:
        try:
            state.validate()
        except ValueError as error:
            raise DevError(f"Refusing to write invalid dev state to {self.state_path}: {error}") from error
        self.ensure()
        temporary = self.state_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(state.as_dict(), indent=2, sort_keys=True) + "\n")
        temporary.replace(self.state_path)

    def clear(self) -> None:
        self.state_path.unlink(missing_ok=True)

    def snapshot_path(self, name: str) -> Path:
        return self.log_directory / f"{name}.log"


@contextmanager
def _named_lock(project_slug: str, name: str, timeout: float) -> Iterator[None]:
    cache_home = Path(os.environ.get("XDG_CACHE_HOME", str(Path.home() / ".cache")))
    lock_path = cache_home / "alliance" / "dev" / project_slug / f"{name}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock_file:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise DevError(f"Timed out waiting for the {project_slug} dev lock ({name})")
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def worktree_lock(project_slug: str, worktree_id: str, timeout: float = 600.0) -> ContextManager[None]:
    return _named_lock(project_slug, f"worktree-{worktree_id}", timeout)


def allocation_lock(timeout: float = 30.0) -> ContextManager[None]:
    """Serialize port reservation across every project using this dev tool."""
    return _named_lock("_alliance", "port-allocation", timeout)
