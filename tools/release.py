"""Validate release metadata and publish a GitHub release after integration validation."""
import argparse
import base64
from collections import Counter
from datetime import datetime
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo


SECTIONS = ("Features", "Bugfixes", "Breaking Changes", "Security")
VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\Z")
BUILD_VERSION = re.compile(r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:b[1-9][0-9]*)?\Z')
MANIFEST = 'custom_components/eos_energiezentrale/manifest.json'
ORIGIN = '.release-source.json'


def draft_sections(text):
    """Only the first New Version section is editable release input."""
    headings = list(re.finditer(r'^## (.+)$', text, re.MULTILINE))
    drafts = [item for item in headings if item[1].strip() == 'New Version']
    if not drafts:
        return None
    if len(drafts) != 1 or headings[0] != drafts[0]:
        raise ValueError('New Version must occur once, before the released history')
    body = text[drafts[0].end():headings[1].start() if len(headings) > 1 else len(text)]
    categories = list(re.finditer(r'^### (.+)\s*$', body, re.MULTILINE))
    if len(categories) != len(SECTIONS) or {item[1].strip() for item in categories} != set(SECTIONS):
        raise ValueError('New Version needs all four unique changelog categories')
    result = {}
    for index, item in enumerate(categories):
        content = body[item.end():categories[index+1].start() if index+1 < len(categories) else len(body)].strip()
        if not content or not content.startswith('- '):
            raise ValueError('Changelog categories need bullet entries or - Keine.')
        entries = [entry.strip() for entry in re.split(r'(?m)(?=^- )', content) if entry.strip()]
        result[item[1].strip()] = [entry for entry in entries if entry not in ('- Keine.', '- None.')]
    return result


def render_notes(sections):
    return '\n\n'.join('### '+key+'\n\n'+('\n'.join(sections[key]) or '- Keine.') for key in SECTIONS)+'\n'


def added_notes(current, previous):
    """Already released draft bullets must not cause another feature bump."""
    result = {}
    for key in SECTIONS:
        old = Counter((previous or {}).get(key, []))
        result[key] = []
        for entry in current[key]:
            if old[entry]:
                old[entry] -= 1
            else:
                result[key].append(entry)
    return result


def next_version(base, sections):
    major, minor, patch = map(int, base.split('.'))
    if sections['Breaking Changes']:
        return f'{major+1}.0.0'
    if sections['Features']:
        return f'{major}.{minor+1}.0'
    return f'{major}.{minor}.{patch+1}'


def version_history(text):
    first = re.search(r'^## \d+\.\d+\.\d+', text, re.MULTILINE)
    return text[first.start():].strip() if first else ''


def file_at(github, ref, path):
    data = github.request('/contents/'+quote(path, safe='/')+'?ref='+quote(ref, safe=''))
    if data is None:
        return None
    if data.get('encoding') != 'base64' or data.get('type') != 'file':
        raise ValueError('GitHub did not return a versioned release input file')
    return base64.b64decode(''.join(data['content'].splitlines()), validate=True).decode('utf-8').replace('\r\n','\n')


def source_origin(github, tag, target):
    content = file_at(github, target, ORIGIN)
    if content is None:
        return {'source_commit': target}  # Releases created before CI versioning.
    origin = json.loads(content)
    if (origin.get('version') != tag.removeprefix('v')
            or not re.fullmatch(r'[0-9a-f]{40}', origin.get('source_commit', ''))):
        raise ValueError('Invalid release provenance')
    commit = github.request('/git/commits/'+target)
    if [parent['sha'] for parent in commit['parents']] != [origin['source_commit']]:
        raise ValueError('Release metadata commit must directly follow its checked source')
    return origin


def includes_stable_source(github, latest_source, source):
    """Accept ancestry or an identical full tree before a squash/rebase merge."""
    path = '/compare/'+latest_source+'...'+source
    comparison = github.request(path+'?per_page=100&page=1')
    if not comparison:
        return False
    if comparison.get('status') in ('ahead', 'identical'):
        return True
    if comparison.get('status') != 'diverged':
        return False
    stable = github.request('/git/commits/'+latest_source)
    tree = (stable or {}).get('tree', {}).get('sha', '')
    if not re.fullmatch(r'[0-9a-f]{40}', tree):
        return False
    page = 1
    while comparison:
        # Compare returns only commits reachable from source but not latest_source.
        # A matching full tree proves the branch contains the stable snapshot even
        # when GitHub assigned a different SHA while merging it into main.
        commits = comparison.get('commits', [])
        if any(item.get('commit', {}).get('tree', {}).get('sha') == tree for item in commits):
            return True
        if len(commits) < 100:
            return False
        page += 1
        comparison = github.request(path+'?per_page=100&page='+str(page))
    return False


def build_plan(root, github, source, channel, beta_number=None, branch='main', today=None):
    if not re.fullmatch(r'[0-9a-f]{40}', source or '') or channel not in ('stable', 'beta'):
        raise ValueError('Release needs a full source SHA and a stable/beta channel')
    if not isinstance(branch, str) or not branch or len(branch) > 255 or any(ord(char) < 32 for char in branch):
        raise ValueError('Invalid branch label')
    if channel == 'stable' and branch != 'main':
        raise ValueError('Stable releases may only originate from main')
    if channel == 'beta' and not re.fullmatch(r'[1-9][0-9]{0,24}', beta_number or ''):
        raise ValueError('Beta builds need the unique numeric GitHub run ID')
    text = (root/'CHANGELOG.md').read_text(encoding='utf-8')
    current = draft_sections(text)
    if current is None:
        raise ValueError('Automatic releases require a New Version changelog section')
    latest = github.request('/releases/latest')
    previous, base, history = None, '0.0.0', version_history(text)
    latest_source = None
    if latest is not None:
        tag = latest['tag_name']
        base = tag.removeprefix('v')
        if not VERSION.fullmatch(base) or latest.get('prerelease') or latest.get('draft'):
            raise ValueError('Latest stable release has invalid metadata')
        target = github.tag_commit(tag)
        origin = source_origin(github, tag, target)
        latest_source = origin['source_commit']
        previous_text = file_at(github, latest_source, 'CHANGELOG.md')
        if previous_text is None:
            raise ValueError('Previous release source changelog is missing')
        previous = draft_sections(previous_text)
        released_text = file_at(github, target, 'CHANGELOG.md')
        history = version_history(released_text or previous_text)
        if not includes_stable_source(github, latest_source, source):
            raise ValueError('Update the branch with the latest stable source before releasing')
    refs = github.request('/git/matching-refs/tags/v') or []
    versions = {item['ref'].removeprefix('refs/tags/v'):item['object']['sha'] for item in refs
                if item['ref'].startswith('refs/tags/v') and BUILD_VERSION.fullmatch(item['ref'][11:])}
    # Resume a complete or partially published run, including retries on a later day.
    for version, target in versions.items():
        candidate = (channel == 'beta' and version.endswith('b'+str(beta_number)) or
                     channel == 'stable' and VERSION.fullmatch(version) and
                     tuple(map(int, version.split('.'))) >= tuple(map(int, base.split('.'))))
        if not candidate:
            continue
        resolved_target = github.tag_commit('v'+version)
        origin = source_origin(github, 'v'+version, resolved_target)
        if origin.get('source_commit') == source and origin.get('channel') == channel:
            release_text = file_at(github, resolved_target, 'CHANGELOG.md')
            notes = notes_for_version(release_text, version)
            if hashlib.sha256(notes.encode()).hexdigest() != origin.get('notes_sha256'):
                raise ValueError('Release notes do not match their provenance')
            return {'version':version, 'notes':notes, 'origin':origin, 'target':resolved_target}
        if channel == 'beta':
            raise ValueError('This beta run number already belongs to a different source')
    sections = added_notes(current, previous)
    if not any(sections.values()):
        raise ValueError('New Version contains no changes beyond the last stable release')
    archived = re.findall(r'^## (\d+\.\d+\.\d+) - \d{4}-\d{2}-\d{2}\s*$', history, re.MULTILINE)
    floor = max([tuple(map(int, value.split('.'))) for value in [base, *archived]] +
                [tuple(map(int, value.split('.'))) for value in versions if VERSION.fullmatch(value)])
    version = next_version('.'.join(map(str, floor)), sections)
    if channel == 'beta':
        version += 'b'+beta_number
    notes = render_notes(sections)
    date = today or datetime.now(ZoneInfo('Europe/Berlin')).date().isoformat()
    origin = {'version':version, 'source_commit':source, 'channel':channel, 'branch':branch,
              'date':date, 'notes_sha256':hashlib.sha256(notes.encode()).hexdigest(),
              'source_changelog_sha256':hashlib.sha256(text.encode()).hexdigest()}
    changelog = '# Changelog\n\n## '+version+' - '+date+'\n\n'+notes+'\n'+history+'\n'
    return {'version':version, 'notes':notes, 'origin':origin, 'changelog':changelog, 'target':None}


def publish_build(github, plan):
    version, origin = plan['version'], plan['origin']
    tag = 'v'+version
    target = github.tag_commit(tag)
    if target is not None:
        if source_origin(github, tag, target) != origin:
            raise ValueError('Published version belongs to different release inputs')
    else:
        source = origin['source_commit']
        source_changelog = file_at(github,source,'CHANGELOG.md')
        if source_changelog is None or hashlib.sha256(source_changelog.encode()).hexdigest() != origin['source_changelog_sha256']:
            raise ValueError('Release notes must belong to the checked source commit')
        original = github.request('/git/commits/'+source)
        manifest = json.loads(file_at(github, source, MANIFEST))
        manifest['version'] = version
        files = {MANIFEST:json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',
                 'CHANGELOG.md':plan['changelog'], ORIGIN:json.dumps(origin,sort_keys=True,indent=2)+'\n'}
        tree = github.request('/git/trees','POST',{'base_tree':original['tree']['sha'], 'tree':[
            {'path':path,'mode':'100644','type':'blob','content':content} for path,content in files.items()]})
        commit = github.request('/git/commits','POST',{'message':'Release '+version,
            'tree':tree['sha'],'parents':[source]})
        target = commit['sha']
        try:
            github.request('/git/refs','POST',{'ref':'refs/tags/'+tag,'sha':target})
        except HTTPError as error:
            if error.code != 422:
                raise
            target = github.tag_commit(tag)
            if target is None or source_origin(github, tag, target) != origin:
                raise ValueError('Concurrent publication reserved this version') from error
    beta = origin['channel'] == 'beta'
    body = plan['notes']+'\nSource: `'+origin['source_commit']+'`\n'
    return publish_release(github,version,body,target,prerelease=beta,
                           title=tag+' ('+origin['branch']+')' if beta else tag)


def release_metadata(root):
    manifest = json.loads((root / "custom_components/eos_energiezentrale/manifest.json").read_text(encoding="utf-8"))
    version = manifest.get("version", "")
    if not isinstance(version, str) or BUILD_VERSION.fullmatch(version) is None:
        raise ValueError("The integration needs a major.minor.patch or beta version")
    text = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    draft = draft_sections(text)
    if draft is not None:
        return None, render_notes(draft)
    return version, notes_for_version(text, version)


def notes_for_version(text, version):
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
    return notes.strip() + "\n"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class GitHub:
    def __init__(self, repository, token, *, read_only=False):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) or not token and not read_only:
            raise ValueError("Repository and GitHub token are required")
        self.base = "https://api.github.com/repos/" + repository
        self.token = token
        self.read_only = read_only
        self.opener = build_opener(NoRedirect())

    def request(self, path, method="GET", data=None):
        if self.read_only and method != 'GET':
            raise ValueError('Version planning must not modify GitHub')
        body = json.dumps(data).encode() if data is not None else None
        request = Request(self.base + path, data=body, method=method,
                          headers={**({"Authorization":"Bearer "+self.token} if self.token else {}),
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
    if BUILD_VERSION.fullmatch(version) is None:
        raise ValueError('Invalid release version')
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


def publish_release(github, version, notes, commit, *, prerelease=False, title=None):
    check_target(github, version, commit)
    tag = "v" + version
    existing = github.request("/releases/tags/" + tag)
    if existing is not None:
        if existing.get("draft") or existing.get("prerelease", False) != prerelease:
            raise ValueError("An existing draft or prerelease requires manual review")
        if existing.get("body", "").strip() != notes.strip():
            raise ValueError("Existing release notes differ; published releases are not overwritten")
        return existing
    return github.request("/releases", "POST", {"tag_name": tag, "target_commitish": commit,
                          "name": title or tag, "body": notes, "draft": False,
                          "prerelease": prerelease, "make_latest":"false" if prerelease else "true"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "prepare", "publish", "plan"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--notes", type=Path)
    parser.add_argument("--repository")
    parser.add_argument("--commit")
    parser.add_argument("--check-local-tag", action="store_true")
    parser.add_argument('--channel', choices=('stable','beta'))
    parser.add_argument('--beta-number')
    parser.add_argument('--branch', default='main')
    args = parser.parse_args()
    try:
        version, notes = release_metadata(args.root)
        if args.check_local_tag and not re.fullmatch(r'[0-9a-f]{40}', args.commit or ''):
            raise ValueError('Release target must be a full commit SHA')
        if args.check_local_tag and version is not None:
            check_local_tag(args.root, version, args.commit or "")
        if args.command == 'plan' or (args.command == 'publish' and args.channel):
            github = GitHub(args.repository or '', os.environ.get('GH_TOKEN',''), read_only=args.command == 'plan')
            plan = build_plan(args.root,github,args.commit,args.channel or 'stable',args.beta_number,args.branch)
            version, notes = plan['version'], plan['notes']
            if args.command == 'publish':
                publish_build(github,plan)
        elif args.command in {"prepare", "publish"}:
            if version is None:
                raise ValueError('Use --channel for automatic New Version publishing')
            github = GitHub(args.repository or "", os.environ.get("GH_TOKEN", ""))
            if args.command == "prepare":
                check_target(github, version, args.commit or "")
            else:
                publish_release(github, version, notes, args.commit)
        if args.notes:
            args.notes.write_text(notes, encoding="utf-8")
        output = os.environ.get("GITHUB_OUTPUT")
        if output and version is not None:
            with open(output, "a", encoding="utf-8") as stream:
                stream.write(f"version={version}\ntag=v{version}\n")
        print("Release metadata checked:", version or 'New Version (assigned by CI)')
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Release stopped: {type(error).__name__}: {error}\n")


if __name__ == "__main__":
    main()
