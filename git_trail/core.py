"""Read local Git metadata and render a portable timeline. No network calls."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path

MAX_LIMIT = 10_000

# Repository-local variables listed by `git rev-parse --local-env-vars`, plus
# namespace/worktree overrides. A caller's Git hook must not redirect -C.
_LOCAL_GIT_ENV = {
    "GIT_ALTERNATE_OBJECT_DIRECTORIES", "GIT_CONFIG", "GIT_CONFIG_PARAMETERS",
    "GIT_CONFIG_COUNT", "GIT_OBJECT_DIRECTORY", "GIT_DIR", "GIT_WORK_TREE",
    "GIT_IMPLICIT_WORK_TREE", "GIT_GRAFT_FILE", "GIT_INDEX_FILE",
    "GIT_NO_REPLACE_OBJECTS", "GIT_REPLACE_REF_BASE", "GIT_PREFIX",
    "GIT_INTERNAL_SUPER_PREFIX", "GIT_SHALLOW_FILE", "GIT_COMMON_DIR", "GIT_NAMESPACE",
}


class GitTrailError(Exception):
    """An actionable input or Git error, safe to show without a traceback."""


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {key: value for key, value in os.environ.items()
           if key not in _LOCAL_GIT_ENV
           and not key.startswith(("GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_"))}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_NO_LAZY_FETCH="1",
               GIT_ALLOW_PROTOCOL="")
    try:
        result = subprocess.run(
            ["git", "--no-pager", "--literal-pathspecs", "-C", str(repo), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            timeout=60,
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitTrailError("Git was not found. Install Git and try again.") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitTrailError("Git took longer than 60 seconds. Try a smaller --limit.") from exc
    if check and result.returncode:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise GitTrailError(message or "Git could not read this repository.")
    return result


def repository_root(repo: Path) -> Path:
    repo = Path(repo).expanduser().resolve()
    if not repo.is_dir():
        raise GitTrailError(f"Repository directory does not exist: {repo}")
    result = _git(repo, "rev-parse", "--show-toplevel", check=False)
    if result.returncode:
        raise GitTrailError("Choose a Git working tree (bare repositories are not supported).")
    return Path(result.stdout.decode("utf-8", errors="replace").rstrip("\r\n"))


def _refs(repo: Path) -> dict[str, list[str]]:
    result = _git(
        repo, "for-each-ref", "--format=%(objectname)%00%(*objectname)%00%(refname)",
        "refs/heads", "refs/tags",
    )
    refs: dict[str, list[str]] = {}
    for line in result.stdout.decode("utf-8", errors="replace").splitlines():
        object_hash, peeled_hash, name = line.split("\0", 2)
        label = name.removeprefix("refs/heads/")
        if name.startswith("refs/tags/"):
            label = "tag: " + name.removeprefix("refs/tags/")
        refs.setdefault(peeled_hash or object_hash, []).append(label)
    return refs


def collect_history(repo: Path, limit: int = 500) -> dict:
    """Collect at most ``limit`` commits reachable from HEAD, newest first.

    Read author names and timestamps, never emails, remote URLs, source or diffs.
    The extra commit only determines whether this export has been truncated.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise GitTrailError(f"--limit must be an integer between 1 and {MAX_LIMIT}.")
    root = repository_root(repo)
    branch_result = _git(root, "symbolic-ref", "--quiet", "--short", "HEAD", check=False)
    branch = branch_result.stdout.decode("utf-8", errors="replace").strip() or "detached HEAD"
    head_result = _git(root, "rev-parse", "--verify", "--quiet", "HEAD", check=False)
    head = head_result.stdout.decode("ascii").strip()
    result = {
        "schemaVersion": 1,
        "repository": {"name": root.name, "branch": branch, "head": head},
        "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "limit": limit,
        "truncated": False,
        "commits": [],
    }
    if not head:
        # Only an unborn branch is an empty history; detached/corrupt HEAD is an error.
        if branch_result.returncode:
            raise GitTrailError("HEAD does not resolve to a commit or an unborn branch.")
        full_ref = _git(root, "symbolic-ref", "HEAD").stdout.decode("utf-8").strip()
        if _git(root, "show-ref", "--verify", "--quiet", full_ref, check=False).returncode != 1:
            raise GitTrailError("HEAD points to an unreadable branch.")
        return result
    log = _git(
        root, "log", "-z", "--no-patch", "--no-show-signature", "--no-decorate",
        "--encoding=UTF-8", "--date-order", f"--max-count={limit + 1}",
        "--format=%H%x00%h%x00%P%x00%an%x00%aI%x00%s", head, "--",
    )
    fields = log.stdout.decode("utf-8", errors="replace").split("\0")
    if fields and fields[-1] == "":
        fields.pop()
    if len(fields) % 6:
        raise GitTrailError("Git returned an unexpected history format.")
    refs = _refs(root)
    commits = []
    for i in range(0, len(fields), 6):
        commit_hash, short_hash, parents, author, date, subject = fields[i:i + 6]
        commits.append({
            "hash": commit_hash, "shortHash": short_hash, "parents": parents.split(),
            "author": author, "date": date, "subject": subject,
            "refs": refs.get(commit_hash, []),
        })
    result["truncated"] = len(commits) > limit
    result["commits"] = commits[:limit]
    return result


def render_html(data: dict) -> str:
    """Embed JSON as inert text, including adversarial commit messages."""
    template = files("git_trail").joinpath("template.html").read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=True, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return template.replace("__GIT_TRAIL_DATA__", payload)
