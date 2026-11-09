"""Configure HACS repository metadata and optionally the main ruleset."""
import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from validate_hacs_metadata import apply_metadata, repository_metadata


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def configure(repository, token, *, metadata_only=False):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Repository must have the form owner/name")
    root = Path(__file__).resolve().parents[1]
    base = "https://api.github.com/repos/" + repository
    opener = build_opener(NoRedirect())

    def api(path="", method="GET", data=None):
        payload = json.dumps(data).encode() if data is not None else None
        request = Request(base + path, data=payload, method=method,
                          headers={"Authorization": "Bearer " + token,
                                   "Accept": "application/vnd.github+json",
                                   "X-GitHub-Api-Version": "2022-11-28",
                                   "Content-Type": "application/json"})
        with opener.open(request, timeout=15) as response:
            return json.load(response)

    apply_metadata(api, repository_metadata(root))
    print("GitHub description and topics checked")
    if metadata_only:
        return
    rules = json.loads((root / ".github/main-ruleset.json").read_text(encoding="utf-8"))
    repo = api()
    api("/branches/main")
    if repo["default_branch"] != "main":
        api(method="PATCH", data={"default_branch": "main"})
    existing = []
    page = 1
    while True:
        batch = api(f"/rulesets?includes_parents=false&per_page=100&page={page}")
        existing.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    matching = [item for item in existing if item["name"] == rules["name"]]
    if len(matching) > 1:
        raise ValueError("Multiple matching rulesets exist; review them in GitHub first")
    path = "/rulesets/" + str(matching[0]["id"]) if matching else "/rulesets"
    result = api(path, "PUT" if matching else "POST", rules)
    if result.get("enforcement") != "active":
        raise ValueError("GitHub did not activate the ruleset")
    print("Main ruleset active:", result["name"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="GitHub owner/repository")
    parser.add_argument("--metadata-only", action="store_true", help="Set missing description and add HACS topics without changing branches or rulesets")
    args = parser.parse_args()
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        parser.error("Set GH_TOKEN to a token with repository administration permission")
    try:
        configure(args.repo, token, metadata_only=args.metadata_only)
    except HTTPError as error:
        print(f"GitHub rejected the request (HTTP {error.code}). Check repository administration permission and plan support.",
              file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError) as error:
        print(f"Setup failed: {type(error).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
