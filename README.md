# Git Trail

**A repository's history, in one offline page.**

Turn a local Git repository into a searchable, interactive timeline. Git Trail generates a single HTML file you can open in your browser—no server, account, JavaScript build step, or runtime Python dependencies.

[简体中文](README.zh-CN.md) · [MIT license](LICENSE)

## Quick start

Requires **Python 3.10+** and **Git 2.31+** on your `PATH`.

```sh
git clone https://github.com/zhou-jianwen/git-trail.git
cd git-trail
python -m git_trail /path/to/your/repository -o trail.html --open
```

Or install the command from this checkout:

```sh
python -m pip install .
git-trail /path/to/your/repository -o trail.html
```

Open the generated file directly in a browser. It works offline and carries its own styles, scripts, and commit data. Installation above uses the source checkout; Git Trail is not published on PyPI.

For a quick look without exporting a repository, open [examples/demo.html](examples/demo.html) from the checkout. It contains explicitly fictional sample history. Regenerate it with `python examples/make_demo.py` after editing the template.

## Explore your history

- Search commit subjects, author names, and hashes.
- Filter by author and date, then reset to the full exported view.
- Browse activity and grouped commits, with local branch and tag labels.
- Copy a full commit hash for use with your usual Git tools.
- Read the same page on a wide screen or a phone.

The page is a snapshot of commits reachable from the selected working tree's **current `HEAD`**. It does not fetch remotes, include uncommitted changes, or show the full branch graph. Empty repositories produce an empty timeline. Dates are displayed in UTC; contributors are grouped by author name.

## Command line

```text
git-trail [repository] [-o OUTPUT] [--limit N] [--force] [--open] [--version]
```

| Option | Behavior |
| --- | --- |
| `repository` | Local repository path; defaults to the current directory. |
| `-o OUTPUT` | HTML destination; defaults to `git-trail.html`. |
| `--limit N` | Export up to N commits. Default: 500. Range: 1–10,000. |
| `--force` | Replace an existing, untracked output file. |
| `--open` | Open the generated page in your default browser. |
| `--version` | Print the installed version. |

The report identifies a truncated export. Its counts and activity describe the exported commits, not necessarily the entire repository.

```sh
# A larger snapshot; opening the browser is optional.
git-trail ../my-project --limit 2000 -o project-history.html

# Regenerate an existing report.
git-trail ../my-project -o project-history.html --force
```

Git Trail refuses to overwrite tracked files, write inside Git metadata directories, or use a symlink as the output file, including with `--force`.

## What the file contains

The HTML includes commit subjects, author names, timestamps, hashes, parent hashes, repository name, and local branch/tag labels. It does **not** export file contents, patches, author email addresses, or remote URLs. Commit subjects and names can still contain private information; review a report before sharing it.

Generation reads local Git history. The generated page makes no network requests and has no analytics, external fonts, or CDN dependencies.

## Development

```sh
python -m unittest discover -s tests -v
python -m pip install .
git-trail --version
```

Tests create temporary Git repositories to exercise real history extraction and command-line behavior. GitHub Actions is configured to run tests and an installed-package smoke check on Linux, macOS, and Windows with Python 3.10 and 3.13.

An additional browser job checks filtering, pagination, clipboard copying, hostile text, mobile layout, and the absence of external requests. To run it locally (Node.js 18+ required for development only):

```sh
npm install --no-save --package-lock=false playwright@1.62.1
npx playwright install chromium
node tests/browser-smoke.cjs examples/demo.html
```

Set `GIT_TRAIL_BROWSER` to a Chromium, Chrome, or Edge executable to use an existing browser. Screenshots from this test go to your system's temporary directory.

Git Trail intentionally focuses on readable history snapshots. It is not a Git client, a live dashboard, or a source-code browser.

## License

[MIT](LICENSE) © 2026 Git Trail contributors.
