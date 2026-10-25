"""Command-line interface and conservative output handling."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile
import webbrowser

from . import __version__
from .core import GitTrailError, _git, collect_history, render_html, repository_root


def _check_output(output: Path, root: Path, force: bool) -> Path:
    output = output.expanduser().absolute()
    if output.is_symlink():
        raise GitTrailError("Refusing to write through an output symlink.")
    resolved = output.resolve()
    if any(part.lower() == ".git" for part in resolved.parts + output.parts):
        raise GitTrailError("The output must not be inside .git.")
    # Worktrees may store their Git metadata outside a directory named .git.
    for flag in ("--git-dir", "--git-common-dir"):
        path = _git(root, "rev-parse", "--path-format=absolute", flag).stdout.decode().strip()
        if resolved.is_relative_to(Path(path).resolve()):
            raise GitTrailError("The output must not be inside Git metadata.")
    parent = resolved.parent
    while not parent.exists():
        parent = parent.parent
    target_root_result = _git(parent, "rev-parse", "--show-toplevel", check=False)
    roots = {root}
    if target_root_result.returncode == 0:
        roots.add(Path(target_root_result.stdout.decode().rstrip("\r\n")).resolve())
    for candidate in roots:
        if resolved.is_relative_to(candidate):
            relative = resolved.relative_to(candidate).as_posix()
            tracked = _git(candidate, "ls-files", "--error-unmatch", "--", relative, check=False)
            if tracked.returncode == 0:
                raise GitTrailError("Refusing to overwrite a Git-tracked file, even with --force.")
    if resolved.exists() and not force:
        raise GitTrailError(f"Output already exists: {output}. Use --force to replace it.")
    return resolved


def _write_output(output: Path, html: str, force: bool) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".git-trail-", suffix=".tmp", dir=output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(html)
        if force:
            os.replace(temporary, output)
        else:
            # Linking makes the absence check atomic: never clobber an existing file.
            os.link(temporary, output)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export a local Git history as an offline HTML timeline.")
    parser.add_argument("repo", nargs="?", default=".", help="Git working tree (default: current directory)")
    parser.add_argument("-o", "--output", default="git-trail.html", help="output HTML path")
    parser.add_argument("--limit", type=int, default=500, help="maximum commits, 1–10000 (default: 500)")
    parser.add_argument("--force", action="store_true", help="replace an existing untracked output file")
    parser.add_argument("--open", action="store_true", help="open the generated file in your browser")
    parser.add_argument("--version", action="version", version=f"git-trail {__version__}")
    args = parser.parse_args(argv)
    try:
        root = repository_root(Path(args.repo))
        output = _check_output(Path(args.output), root, args.force)
        data = collect_history(root, args.limit)
        _write_output(output, render_html(data), args.force)
    except (GitTrailError, OSError, UnicodeError) as exc:
        print(f"git-trail: {exc}", file=sys.stderr)
        return 1
    scope = " (history truncated; increase --limit for more)" if data["truncated"] else ""
    print(f"Exported {len(data['commits'])} commits{scope}: {output}")
    if args.open:
        try:
            if not webbrowser.open(output.as_uri()):
                print("Could not open a browser. Open the HTML file manually.", file=sys.stderr)
        except webbrowser.Error:
            print("Could not open a browser. Open the HTML file manually.", file=sys.stderr)
    return 0
