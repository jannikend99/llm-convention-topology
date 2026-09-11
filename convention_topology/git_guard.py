"""Campaign-writing CLIs fail on a dirty Git worktree."""

from __future__ import annotations

import subprocess
from pathlib import Path


class DirtyWorktreeError(Exception):
    """Counted campaign writes require a clean Git worktree."""


def require_clean_worktree(repo_root: Path | None = None) -> str:
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parent.parent
    try:
        output = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=root,
            text=True,
        )
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise DirtyWorktreeError("unable to read git worktree") from exc
    if output.strip():
        raise DirtyWorktreeError("campaign-writing CLI refuses a dirty Git worktree")
    return commit


def current_commit(repo_root: Path | None = None) -> str:
    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parent.parent
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"
