"""Regenerate the demo with explicitly fictional history; no repository access."""

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from git_trail.core import render_html


SUBJECTS = [
    "Ship the autumn field guide",
    "Make keyboard navigation feel natural",
    "Remember the last reading position",
    "Add a quiet mode for focused writing",
    "Fix date filters across time zones",
    "Bring small-screen layouts into focus",
    "Merge the notebook search improvements",
    "Search notes by title and tag",
    "Keep exported notes readable offline",
    "Translate the welcome screen: 你好，世界",
    "Show a helpful empty state for new notebooks",
    "Add a print-friendly reading view",
    "Give every notebook a little more breathing room",
    "Fix long titles wrapping on mobile",
    "Introduce notebook collections",
    "Keep draft notes safe during navigation",
    "Improve contrast for quiet interface text",
    "Document the plain-text export format",
    "Add a quick switcher for recent notebooks",
    "Make search work with accented characters",
    "Render code examples without syntax surprises",
    "Add links between related field notes",
    "Support drag-and-drop note ordering",
    "Keep dates consistent in exported files",
    "Add integration coverage for notebook imports",
    "Restore focus after closing a dialog",
    "Create a simple getting-started notebook",
    "Add author names to shared exports",
    "Make empty searches return all notes",
    "Test notes containing <script> as plain text",
    "Support multiline notebook descriptions",
    "Choose warmer colors for long reading sessions",
    "Add the first local notebook store",
    "Sketch the two-column workspace",
    "Write down the small, offline-first scope",
    "Plant the first seed",
]


def main():
    end = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
    hashes = [hashlib.sha256(f"fictional-demo-{i}".encode()).hexdigest()[:40]
              for i in range(len(SUBJECTS))]
    commits = []
    for i, subject in enumerate(SUBJECTS):
        parents = hashes[i + 1:i + 2]
        if i == 6:
            parents = hashes[i + 1:i + 3]
        commits.append({
            "hash": hashes[i], "shortHash": hashes[i][:7], "parents": parents,
            "author": ["Mira Chen", "Sam Rivera", "Kai Ito"][i % 3],
            "date": (end - timedelta(days=i * 2 + i // 4)).isoformat(),
            "subject": subject,
            "refs": ["main", "tag: v0.3.0"] if i == 0 else ["tag: v0.2.0"] if i == 14 else [],
        })
    data = {
        "schemaVersion": 1,
        "repository": {"name": "fieldnotes (fictional demo)", "branch": "main", "head": hashes[0]},
        "generatedAt": end.isoformat(), "limit": 500, "truncated": False, "commits": commits,
    }
    output = Path(__file__).with_name("demo.html")
    output.write_text(render_html(data), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
