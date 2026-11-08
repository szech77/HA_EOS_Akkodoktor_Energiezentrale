"""Validate release metadata and publish a GitHub release after the image build."""
import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener


SECTIONS = ("Features", "Bugfixes", "Breaking Changes", "Security")
VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")


def release_metadata(root):
    config = (root / "eos_energiezentrale/config.yaml").read_text(encoding="utf-8")
    match = re.search(r'^version:\s*["\']?([0-9]+\.[0-9]+\.[0-9]+)["\']?\s*$', config, re.MULTILINE)
    if match is None or VERSION.fullmatch(match[1]) is None:
        raise ValueError("The add-on needs a stable major.minor.patch version")
    version = match[1]
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    if text != (root / "eos_energiezentrale/CHANGELOG.md").read_text(encoding="utf-8"):
        raise ValueError("Root and add-on changelogs must match")
    heading = re.search(r"^## (?:\[)?" + re.escape(version) + r"(?:\])?(?: - \d{4}-\d{2}-\d{2})?\s*$",
                        text, re.MULTILINE)
    if heading is None:
        raise ValueError("No changelog entry for version " + version)
    following = text[heading.end():]
    end = re.search(r"^## ", following, re.MULTILINE)
    notes = following[:end.start()] if end else following
    for section in SECTIONS:
        found = re.search(r"^### " + re.escape(section) + r"\s*\n(.*?)(?=^### |\Z)",
                          notes, re.MULTILINE | re.DOTALL)
        if not found or not found[1].strip():
            raise ValueError("Missing or empty changelog section: " + section)
    return version, notes.strip() + "\n"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class GitHub:
    def __init__(self, repository, token):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or not token:
            raise ValueError("Repository and GitHub token are required")
        self.base = "https://api.github.com/repos/" + repository
        self.token = token
        self.opener = build_opener(NoRedirect())

    def request(self, path, method="GET", data=None):
        body = json.dumps(data).encode() if data is not None else None
        request = Request(self.base + path, data=body, method=method,
                          headers={"Authorization": "Bearer " + self.token,
                                   "Accept": "application/vnd.github+json",
                                   "X-GitHub-Api-Version": "2022-11-28",
                                   "Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=15) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code == 404 and method == "GET":
                return None
            raise

    def tag_commit(self, tag):
        ref = self.request("/git/ref/tags/" + tag)
        if ref is None:
            return None
        obj = ref["object"]
        for _ in range(5):
            if obj["type"] == "commit":
                return obj["sha"]
            if obj["type"] != "tag":
                break
            obj = self.request("/git/tags/" + obj["sha"])["object"]
        raise ValueError("Release tag does not point to a commit")


def check_target(github, version, commit):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Release target must be a full commit SHA")
    existing = github.tag_commit("v" + version)
    if existing is not None and existing != commit:
        raise ValueError("This version already belongs to a different commit; increase the version in a pull request")


def check_local_tag(root, version, commit):
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Release target must be a full commit SHA")
    result = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify",
                             "refs/tags/v" + version + "^{commit}"],
                            capture_output=True, text=True, check=False)
    if result.returncode == 0 and result.stdout.strip() != commit:
        raise ValueError("Version is already tagged; increase the version and add a changelog entry")
    if result.returncode not in {0, 128}:
        raise ValueError("Could not inspect local release tags")


def publish_release(github, version, notes, commit):
    check_target(github, version, commit)
    tag = "v" + version
    existing = github.request("/releases/tags/" + tag)
    if existing is not None:
        if existing.get("draft") or existing.get("prerelease"):
            raise ValueError("An existing draft or prerelease requires manual review")
        if existing.get("body", "").strip() != notes.strip():
            raise ValueError("Existing release notes differ; published releases are not overwritten")
        return existing
    return github.request("/releases", "POST", {"tag_name": tag, "target_commitish": commit,
                          "name": tag, "body": notes, "draft": False, "prerelease": False})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "prepare", "publish"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--notes", type=Path)
    parser.add_argument("--repository")
    parser.add_argument("--commit")
    parser.add_argument("--check-local-tag", action="store_true")
    args = parser.parse_args()
    try:
        version, notes = release_metadata(args.root)
        if args.check_local_tag:
            check_local_tag(args.root, version, args.commit or "")
        if args.command in {"prepare", "publish"}:
            github = GitHub(args.repository or "", os.environ.get("GH_TOKEN", ""))
            if args.command == "prepare":
                check_target(github, version, args.commit or "")
            else:
                publish_release(github, version, notes, args.commit)
        if args.notes:
            args.notes.write_text(notes, encoding="utf-8")
        output = os.environ.get("GITHUB_OUTPUT")
        if output:
            with open(output, "a", encoding="utf-8") as stream:
                stream.write(f"version={version}\ntag=v{version}\n")
        print("Release metadata checked:", version)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Release stopped: {type(error).__name__}: {error}\n")


if __name__ == "__main__":
    main()
