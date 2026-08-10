from __future__ import annotations

import hashlib
from pathlib import Path
import re
import subprocess

from .models import DevConfig
from .models import WorktreeIdentity

POSTGRES_IDENTIFIER_MAX_LENGTH = 63
DJANGO_TEST_DATABASE_PREFIX = "test_"
# Django appends ``_<worker number>`` when cloning its test database for
# parallel execution. Four digits is comfortably beyond a practical local
# worker count while retaining useful project/worktree context in the name.
DJANGO_PARALLEL_CLONE_SUFFIX_LENGTH = len("_9999")
DATABASE_NAME_MAX_LENGTH = (
    POSTGRES_IDENTIFIER_MAX_LENGTH - len(DJANGO_TEST_DATABASE_PREFIX) - DJANGO_PARALLEL_CLONE_SUFFIX_LENGTH
)
LEGACY_DATABASE_NAME_MAX_LENGTH = 58


def slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9-]+", "-", value)
    return re.sub(r"-+", "-", value).strip("-")


def _git_output(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def worktree_stem(repo: Path) -> str:
    git_dir = _git_output(repo, "rev-parse", "--git-dir")
    candidate = Path(git_dir).name if git_dir else repo.name
    if candidate == ".git":
        candidate = repo.name
    return slugify(candidate) or "worktree"


def current_branch(repo: Path) -> str | None:
    branch = _git_output(repo, "symbolic-ref", "--short", "HEAD")
    return branch or None


def _database_name_parts(project_slug: str, stem: str, path_hash: str) -> str:
    prefix = slugify(project_slug).replace("-", "_")
    readable = slugify(stem).replace("-", "_")[:24]
    return f"{prefix}_{readable}_{path_hash}"


def database_name(project_slug: str, stem: str, path_hash: str) -> str:
    name = _database_name_parts(project_slug, stem, path_hash)
    if len(name) <= DATABASE_NAME_MAX_LENGTH:
        return name
    hash_suffix = f"_{path_hash}"
    return f"{name[: DATABASE_NAME_MAX_LENGTH - len(hash_suffix)]}{hash_suffix}"


def legacy_database_name(project_slug: str, stem: str, path_hash: str) -> str:
    """Return the pre-parallel-test-safe database identity for cleanup only."""
    name = _database_name_parts(project_slug, stem, path_hash)
    if len(name) > LEGACY_DATABASE_NAME_MAX_LENGTH:
        name = f"{name[:49]}_{path_hash}"
    return name[:LEGACY_DATABASE_NAME_MAX_LENGTH]


def resolve_identity(repo: Path, config: DevConfig) -> WorktreeIdentity:
    canonical = repo.resolve()
    stem = worktree_stem(canonical)
    path_hash = hashlib.blake2s(str(canonical).encode(), digest_size=5).hexdigest()
    worktree_id = f"{stem[:24]}-{path_hash}"
    session = f"{config.project_slug}-wt-{worktree_id}"
    db_name = database_name(config.project_slug, stem, path_hash)
    portless_app_name = f"{worktree_id}.{config.project_slug}"
    return WorktreeIdentity(
        repo=canonical,
        branch=current_branch(canonical),
        worktree_id=worktree_id,
        session_name=session,
        database_name=db_name,
        portless_app_name=portless_app_name,
    )
