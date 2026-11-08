"""Validate checked-out metadata even before GitHub recognizes the main license."""
import argparse
import hashlib
import json
from pathlib import Path
import re

# Canonical Apache-2.0 text from https://www.apache.org/licenses/LICENSE-2.0.txt.
# Ignore surrounding whitespace and platform line endings, not license clauses.
APACHE_2_0 = "283ea6cc2997a1a70da0049e09adf9317bb60ca1b51279b65196b83a69e1996b"


def repository_metadata(root):
    data = json.loads((root / ".github/repository-metadata.json").read_text(encoding="utf-8"))
    description, topics = data.get("description"), data.get("topics")
    if not isinstance(description, str) or not description.strip() or len(description) > 350:
        raise ValueError("A nonempty repository description is required")
    if (not isinstance(topics, list) or not 1 <= len(topics) <= 20
            or any(not isinstance(topic, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,49}", topic)
                   for topic in topics) or len(set(topics)) != len(topics)):
        raise ValueError("Repository topics must be unique lowercase GitHub topic names")
    return {"description": description.strip(), "topics": topics}


def validate(root):
    repository_metadata(root)
    for relative in ("LICENSE", "custom_components/eos_energiezentrale/LICENSE"):
        text = (root / relative).read_text(encoding="utf-8").replace("\r\n", "\n").strip()
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != APACHE_2_0:
            raise ValueError(relative + " must contain the full unmodified Apache-2.0 license")


def apply_metadata(api, desired):
    """Add missing metadata without replacing a maintainer's description/topics."""
    repo = api()
    existing = api("/topics").get("names", [])
    topics = sorted(set(existing) | set(desired["topics"]))
    if len(topics) > 20:
        raise ValueError("Adding the required topics would exceed GitHub's 20-topic limit")
    if not repo.get("description") or not repo["description"].strip():
        api(method="PATCH", data={"description": desired["description"]})
    if set(topics) != set(existing):
        api("/topics", "PUT", {"names": topics})
    confirmed, confirmed_topics = api(), api("/topics").get("names", [])
    if (not confirmed.get("description") or not confirmed["description"].strip()
            or not set(desired["topics"]) <= set(confirmed_topics)):
        raise ValueError("GitHub did not confirm repository metadata")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        validate(args.root)
    except (OSError, ValueError, TypeError) as error:
        parser.exit(1, f"HACS metadata validation failed: {error}\n")
    print("Local HACS metadata and Apache-2.0 license checked")


if __name__ == "__main__":
    main()
