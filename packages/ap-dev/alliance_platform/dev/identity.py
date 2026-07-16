from __future__ import annotations

import hashlib
from pathlib import Path
import re
import subprocess

from .models import DevConfig
from .models import WorktreeIdentity


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


def database_name(project_slug: str, stem: str, path_hash: str) -> str:
    prefix = slugify(project_slug).replace("-", "_")
    readable = slugify(stem).replace("-", "_")[:24]
    suffix = f"{readable}_{path_hash}"
    name = f"{prefix}_{suffix}"
    if len(name) > 58:
        name = f"{name[:49]}_{path_hash}"
    return name[:58]


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
