"""Integration tests against real, disposable Git repositories."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from git_trail.core import GitTrailError, collect_history, render_html


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(shutil.which("git"), "Git is required for integration tests")
class GitTrailTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="git-trail-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "a repository with spaces 空间"
        self.repo.mkdir()
        self.env = os.environ.copy()
        # Avoid reading user identity, signing, hooks, or global Git configuration.
        self.env.update(
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_AUTHOR_NAME="Trail 作者",
            GIT_AUTHOR_EMAIL="private-author@example.invalid",
            GIT_COMMITTER_NAME="Trail Committer",
            GIT_COMMITTER_EMAIL="private-committer@example.invalid",
            GIT_AUTHOR_DATE="2026-01-02T12:00:00+08:00",
            GIT_COMMITTER_DATE="2026-01-02T12:00:00+08:00",
        )
        self.git("init", "--initial-branch=main")
        self.git("config", "commit.gpgsign", "false")
        self.git("config", "core.hooksPath", str(self.root / "no-hooks"))
        self.commit_count = 0

    def git(self, *args):
        return self.git_at(self.repo, *args)

    def git_at(self, repo, *args):
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            env=self.env,
            text=True,
            capture_output=True,
            check=True,
        )
        return result.stdout.strip()

    def commit(self, subject="Add an example", *, body=None):
        self.commit_count += 1
        filename = self.repo / f"example-{self.commit_count}.txt"
        filename.write_text(f"Example {self.commit_count}\n", encoding="utf-8")
        self.git("add", "--", filename.name)
        args = ["commit", "-m", subject]
        if body is not None:
            args.extend(["-m", body])
        self.git(*args)
        return self.git("rev-parse", "HEAD")

    def cli(self, *args, cwd=None, extra_env=None):
        env = self.env.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT)
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, "-m", "git_trail", *map(str, args)],
            cwd=cwd or self.root,
            env=env,
            text=True,
            capture_output=True,
        )

    def test_commit_metadata_and_parents(self):
        first = self.commit("Start the trail")
        second = self.commit("Add Unicode: 你好 🌱")
        history = collect_history(self.repo)
        self.assertEqual(history["schemaVersion"], 1)
        self.assertEqual(history["repository"]["name"], self.repo.name)
        self.assertEqual(history["repository"]["branch"], "main")
        self.assertEqual(history["repository"]["head"], second)
        self.assertTrue(history["generatedAt"])
        self.assertFalse(history["truncated"])
        self.assertEqual(len(history["commits"]), 2)
        latest, initial = history["commits"]
        self.assertEqual(latest["hash"], second)
        self.assertTrue(second.startswith(latest["shortHash"]))
        self.assertEqual(latest["parents"], [first])
        self.assertEqual(initial["parents"], [])
        self.assertEqual(latest["author"], "Trail 作者")
        self.assertEqual(latest["subject"], "Add Unicode: 你好 🌱")
        self.assertTrue(latest["date"].startswith("2026-01-02T"))
        self.assertIsInstance(latest["refs"], list)

    def test_unborn_repository_is_an_empty_export(self):
        history = collect_history(self.repo)
        self.assertEqual(history["commits"], [])
        self.assertEqual(history["repository"]["branch"], "main")
        self.assertFalse(history["truncated"])
        self.assertIn("<!doctype html", render_html(history).lower())

    def test_limit_detects_more_history_without_off_by_one(self):
        self.commit("One")
        self.commit("Two")
        third = self.commit("Three")
        limited = collect_history(self.repo, limit=2)
        self.assertEqual(limited["limit"], 2)
        self.assertTrue(limited["truncated"])
        self.assertEqual(len(limited["commits"]), 2)
        self.assertEqual(limited["commits"][0]["hash"], third)
        exact = collect_history(self.repo, limit=3)
        self.assertFalse(exact["truncated"])
        self.assertEqual(len(exact["commits"]), 3)

    def test_invalid_limits_fail_cleanly(self):
        self.commit()
        for limit in (0, -1):
            with self.subTest(limit=limit):
                with self.assertRaises((GitTrailError, ValueError)):
                    collect_history(self.repo, limit=limit)

    def test_only_current_head_history_is_exported(self):
        self.commit("Common ancestor")
        self.git("checkout", "-b", "side-project")
        side_hash = self.commit("Not on main")
        self.git("checkout", "main")
        history = collect_history(self.repo)
        self.assertEqual(len(history["commits"]), 1)
        self.assertNotIn(side_hash, [c["hash"] for c in history["commits"]])

    def test_detached_head_is_supported(self):
        first = self.commit("Original")
        self.commit("Later")
        self.git("checkout", "--detach", first)
        history = collect_history(self.repo)
        self.assertEqual(history["repository"]["head"], first)
        self.assertIsInstance(history["repository"]["branch"], str)
        self.assertEqual([c["hash"] for c in history["commits"]], [first])

    def test_tag_is_preserved_as_a_ref(self):
        self.commit("Release")
        self.git("tag", "v0.1.0")
        refs = collect_history(self.repo)["commits"][0]["refs"]
        self.assertTrue(any("v0.1.0" in ref for ref in refs), refs)

    def test_email_remote_and_commit_body_are_not_exported(self):
        self.commit("A public subject", body="Private body marker: BODY_SECRET_41")
        self.git("remote", "add", "origin", "https://secret-user:REMOTE_SECRET_72@example.invalid/repo")
        history = collect_history(self.repo)
        serialized = json.dumps(history)
        html = render_html(history)
        for output in (serialized, html):
            for private_text in (
                "private-author@example.invalid",
                "private-committer@example.invalid",
                "BODY_SECRET_41",
                "REMOTE_SECRET_72",
                str(self.repo),
            ):
                self.assertNotIn(private_text, output)

    def test_html_embeds_json_without_allowing_script_breakout(self):
        subject = '</script><script>window.__gitTrailInjected=true</script> & "你好"'
        self.commit(subject)
        history = collect_history(self.repo)
        html = render_html(history)
        self.assertNotIn(subject, html)
        match = re.search(
            r'<script\b(?=[^>]*\bid=[\'"]trail-data[\'"])[^>]*>(.*?)</script\s*>',
            html,
            flags=re.DOTALL | re.IGNORECASE,
        )
        self.assertIsNotNone(match, "The export needs its trail-data JSON script")
        embedded = json.loads(match.group(1))
        self.assertEqual(embedded["commits"][0]["subject"], subject)
        self.assertNotIn("__GIT_TRAIL_DATA__", html)
        self.assertNotRegex(html, r'<(?:script|link)\b[^>]*(?:src|href)=[\'"]https?://')

    def test_non_repository_is_a_domain_error(self):
        plain_directory = self.root / "not a git repository"
        plain_directory.mkdir()
        with self.assertRaises(GitTrailError):
            collect_history(plain_directory)

    def test_missing_repository_is_a_domain_error(self):
        with self.assertRaises(GitTrailError):
            collect_history(self.root / "does not exist")

    def test_export_is_read_only_for_source_repository(self):
        self.commit()
        (self.repo / "local-notes.txt").write_text("Do not change me", encoding="utf-8")
        before = self.git("status", "--porcelain=v1")
        head = self.git("rev-parse", "HEAD")
        collect_history(self.repo)
        self.assertEqual(self.git("status", "--porcelain=v1"), before)
        self.assertEqual(self.git("rev-parse", "HEAD"), head)

    def test_cli_exports_to_path_with_spaces(self):
        self.commit("An exported commit")
        output = self.root / "my offline timeline.html"
        result = self.cli(self.repo, "-o", output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("An exported commit", output.read_text(encoding="utf-8"))

    def test_cli_exports_unicode_path_with_legacy_stdout_encoding(self):
        self.commit("Unicode report on a legacy terminal")
        output = self.root / "时间线报告.html"
        result = self.cli(
            self.repo, "-o", output,
            extra_env={"PYTHONIOENCODING": "cp1252:strict"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertIn("Exported 1 commits", result.stdout)
        html = output.read_text(encoding="utf-8")
        self.assertIn("<!doctype html", html.lower())
        self.assertIn("Unicode report on a legacy terminal", html)

    def test_cli_reports_unicode_error_path_with_legacy_stderr_encoding(self):
        output = self.root / "should-not-exist.html"
        result = self.cli(
            self.root / "不存在的仓库", "-o", output,
            extra_env={"PYTHONIOENCODING": "cp1252:strict"},
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("git-trail:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(output.exists())

    def test_cli_defaults_to_current_repository_and_output(self):
        self.commit()
        result = self.cli(cwd=self.repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.repo / "git-trail.html").is_file())

    def test_cli_refuses_existing_file_unless_forced(self):
        self.commit()
        output = self.root / "existing.html"
        output.write_text("Do not overwrite", encoding="utf-8")
        result = self.cli(self.repo, "-o", output)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output.read_text(encoding="utf-8"), "Do not overwrite")
        result = self.cli(self.repo, "-o", output, "--force")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("<!doctype html", output.read_text(encoding="utf-8").lower())

    def test_cli_never_overwrites_tracked_file_even_with_force(self):
        self.commit()
        output = self.repo / "example-1.txt"
        original = output.read_bytes()
        result = self.cli(self.repo, "-o", output, "--force")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output.read_bytes(), original)

    def test_cli_never_writes_into_git_metadata(self):
        self.commit()
        output = self.repo / ".git" / "timeline.html"
        result = self.cli(self.repo, "-o", output, "--force")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())
        config = self.repo / ".git" / "config"
        original = config.read_bytes()
        result = self.cli(self.repo, "-o", config, "--force")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(config.read_bytes(), original)

    def test_cli_reports_invalid_repository_without_traceback(self):
        result = self.cli(self.root / "missing", "-o", self.root / "output.html")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse((self.root / "output.html").exists())

    def make_other_repo(self):
        other = self.root / "another repository"
        other.mkdir()
        self.git_at(other, "init", "--initial-branch=other")
        self.git_at(other, "config", "commit.gpgsign", "false")
        (other / "tracked.txt").write_text("Keep this other repository intact", encoding="utf-8")
        self.git_at(other, "add", "tracked.txt")
        self.git_at(other, "commit", "-m", "Other repository private history")
        return other

    def test_repository_environment_cannot_redirect_explicit_input(self):
        expected_head = self.commit("Requested repository")
        other = self.make_other_repo()
        overrides = {
            "GIT_DIR": str(other / ".git"),
            "GIT_WORK_TREE": str(other),
            "GIT_INDEX_FILE": str(other / ".git" / "index"),
            "GIT_OBJECT_DIRECTORY": str(other / ".git" / "objects"),
        }
        with patch.dict(os.environ, overrides):
            history = collect_history(self.repo)
        self.assertEqual(history["repository"]["name"], self.repo.name)
        self.assertEqual(history["repository"]["head"], expected_head)
        self.assertEqual(history["commits"][0]["subject"], "Requested repository")

    def test_repository_environment_cannot_bypass_tracked_output_protection(self):
        self.commit()
        other = self.make_other_repo()
        output = self.repo / "example-1.txt"
        original = output.read_bytes()
        result = self.cli(
            self.repo, "-o", output, "--force",
            extra_env={"GIT_DIR": str(other / ".git"), "GIT_WORK_TREE": str(other)},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output.read_bytes(), original)

    def test_tracked_output_in_another_repository_is_protected(self):
        self.commit()
        other = self.make_other_repo()
        output = other / "tracked.txt"
        original = output.read_bytes()
        result = self.cli(self.repo, "-o", output, "--force")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(output.read_bytes(), original)

    def test_linked_worktree_external_git_metadata_is_protected(self):
        self.commit()
        metadata = self.root / "external metadata"
        self.git("init", "--separate-git-dir", str(metadata))
        linked = self.root / "linked working tree"
        self.git("worktree", "add", "-b", "linked", str(linked))
        history = collect_history(linked)
        self.assertEqual(history["repository"]["name"], linked.name)
        self.assertEqual(len(history["commits"]), 1)
        worktree_metadata = Path(self.git_at(linked, "rev-parse", "--absolute-git-dir"))
        for directory in (metadata, worktree_metadata):
            with self.subTest(metadata=directory):
                output = directory / "timeline.html"
                result = self.cli(linked, "-o", output, "--force")
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(output.exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "Symlinks are unavailable")
    def test_cli_refuses_output_symlink_even_with_force(self):
        self.commit()
        target = self.root / "valuable.txt"
        target.write_text("Do not replace me", encoding="utf-8")
        output = self.root / "report.html"
        try:
            output.symlink_to(target)
        except OSError as exc:
            self.skipTest(f"Cannot create symlink on this system: {exc}")
        result = self.cli(self.repo, "-o", output, "--force")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(output.is_symlink())
        self.assertEqual(target.read_text(encoding="utf-8"), "Do not replace me")

    def test_cli_rejects_invalid_limit_before_creating_output(self):
        self.commit()
        for value in ("0", "-1", "not-a-number"):
            with self.subTest(limit=value):
                output = self.root / "invalid-limit.html"
                result = self.cli(self.repo, "--limit", value, "-o", output)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
