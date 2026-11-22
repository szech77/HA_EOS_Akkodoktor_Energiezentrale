"""CI-generated versions, immutable source snapshots and safe publication retries."""
import base64
from copy import deepcopy
import json
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from urllib.error import HTTPError

import pytest

from tools import release
from test_energy import temporary_project_directory

BASE, SOURCE = 'b'*40, 'a'*40
EMPTY = {key:[] for key in release.SECTIONS}
NOTES = {**EMPTY, 'Features':['- Adds automatic releases.']}
DRAFT = '# Changelog\n\n## New Version\n\n'+release.render_notes(NOTES)+'\n## 0.19.0 - 2026-11-16\n\n'+release.render_notes(EMPTY)


class Repository:
    def __init__(self):
        self.files = {(SOURCE,'CHANGELOG.md'):DRAFT, (SOURCE,release.MANIFEST):'{"version":"0.0.0","requirements":["example==1"]}',
                      (BASE,'CHANGELOG.md'):'# Changelog\n\n## 0.19.0\n\n'+release.render_notes(EMPTY)}
        self.commits = {value:{'sha':value,'tree':{'sha':'1'*40},'parents':[]} for value in (SOURCE,BASE)}
        self.tags = {'v0.19.0':BASE}
        self.releases = [{'tag_name':'v0.19.0','draft':False,'prerelease':False,'body':'old notes'}]
        self.writes = []
        self.trees = {}
        self.comparison = 'ahead'
        self.comparison_commits = []
        self.comparison_files = ['CHANGELOG.md']
        self.branches = {'feature/releases':SOURCE}
        self.concurrent_head = None
        self.fail_dispatch = False

    def tag_commit(self, tag):
        return self.tags.get(tag)

    def request(self, path, method='GET', data=None):
        if method != 'GET':
            self.writes.append((path,deepcopy(data)))
        if path == '/releases/latest':
            return next((row for row in reversed(self.releases) if not row['prerelease']),None)
        if path.startswith('/contents/'):
            parsed=urlsplit(path);ref=parse_qs(parsed.query)['ref'][0]
            value=self.files.get((ref,unquote(parsed.path.removeprefix('/contents/'))))
            return {'type':'file','encoding':'base64','content':base64.b64encode(value.encode()).decode()} if value is not None else None
        if path.startswith('/compare/'):
            page = int(parse_qs(urlsplit(path).query).get('page', ['1'])[0])
            return {'status':self.comparison, 'commits':self.comparison_commits[(page-1)*100:page*100],
                    'files':[{'filename':name} for name in self.comparison_files]}
        if path.startswith('/git/ref/heads/'):
            return {'object':{'sha':self.branches[unquote(path.removeprefix('/git/ref/heads/'))]}}
        if path.startswith('/git/refs/heads/') and method == 'PATCH':
            branch = unquote(path.removeprefix('/git/refs/heads/'))
            assert data['force'] is False
            if self.concurrent_head:
                self.branches[branch] = self.concurrent_head
            if self.branches[branch] not in [row['sha'] for row in self.commits[data['sha']]['parents']]:
                raise HTTPError(path, 422, 'Not a fast forward', {}, None)
            self.branches[branch] = data['sha']
            return {}
        if path == '/actions/workflows/ci.yml/dispatches' and method == 'POST':
            if self.fail_dispatch:
                raise HTTPError(path, 503, 'Temporary dispatch failure', {}, None)
            return None
        if path == '/git/matching-refs/tags/v':
            return [{'ref':'refs/tags/'+tag,'object':{'sha':sha,'type':'commit'}} for tag,sha in self.tags.items()]
        if path == '/git/trees':
            sha=f'{len(self.trees)+100:040x}';self.trees[sha]=data
            return {'sha':sha}
        if path == '/git/commits' and method == 'POST':
            sha=f'{len(self.commits)+200:040x}'
            self.commits[sha]={'sha':sha,'parents':[{'sha':value} for value in data['parents']], 'tree':{'sha':data['tree']}}
            for (ref, path), content in list(self.files.items()):
                if ref == data['parents'][0]:
                    self.files[sha, path] = content
            for item in self.trees[data['tree']]['tree']:
                self.files[sha,item['path']]=item['content']
            return self.commits[sha]
        if path.startswith('/git/commits/'):
            return self.commits[path.rsplit('/',1)[1]]
        if path == '/git/refs':
            assert data['ref'].startswith('refs/tags/')
            self.tags[data['ref'].removeprefix('refs/tags/')]=data['sha']
            return {}
        if path.startswith('/releases/tags/'):
            return next((row for row in self.releases if row['tag_name']==path.rsplit('/',1)[1]),None)
        if path == '/releases' and method == 'POST':
            self.releases.append(data);return data
        raise AssertionError((path,method,data))


@pytest.fixture
def project():
    with temporary_project_directory() as root:
        path=root/release.MANIFEST;path.parent.mkdir(parents=True)
        path.write_text('{"version":"0.0.0"}',encoding='utf-8')
        (root/'CHANGELOG.md').write_text(DRAFT,encoding='utf-8')
        yield root


def plan(root, github, channel='beta', build='123', source=SOURCE):
    return release.build_plan(root,github,source,channel,build,
                              'main' if channel=='stable' else 'feature/releases',today='2026-11-17')


def test_draft_has_no_manual_release_version(project):
    version,notes=release.release_metadata(project)
    assert version is None
    assert 'automatic releases' in notes


@pytest.mark.parametrize('sections,expected',[
    ({**EMPTY,'Features':['- New feature.']},'0.20.0'),
    ({**EMPTY,'Bugfixes':['- Correction.']},'0.19.1'),
    ({**EMPTY,'Security':['- Security fix.']},'0.19.1'),
    ({**NOTES,'Breaking Changes':['- Incompatible API.']},'1.0.0'),
])
def test_version_increment_uses_only_new_category_entries(sections, expected):
    assert release.next_version('0.19.0',sections)==expected


def test_two_branch_builds_have_distinct_beta_versions_and_do_not_replace_latest_stable(project):
    github=Repository()
    for build in ('123','124'):
        build_plan=plan(project,github,build=build)
        assert build_plan['version']=='0.20.0b'+build
        result=release.publish_build(github,build_plan)
        assert result['prerelease'] is True
        assert result['make_latest']=='false'
    assert github.request('/releases/latest')['tag_name']=='v0.19.0'
    assert not any(path.endswith('/heads/main') for path,_ in github.writes)


@pytest.mark.parametrize('channel', ['stable', 'beta'])
def test_generated_tag_has_matching_manifest_date_history_and_checked_source_parent(project, channel):
    github=Repository();build_plan=plan(project,github,channel)
    version = '0.20.0' if channel == 'stable' else '0.20.0b123'
    result=release.publish_build(github,build_plan)
    target=github.tags['v'+version]
    assert target!=SOURCE
    assert github.commits[target]['parents']==[{'sha':SOURCE}]
    manifest=json.loads(github.files[target,release.MANIFEST])
    assert manifest=={'version':version,'requirements':['example==1']}
    assert '## '+version+' - 2026-11-17' in github.files[target,'CHANGELOG.md']
    assert '## 0.19.0' in github.files[target,'CHANGELOG.md']
    assert '## New Version' not in github.files[target,'CHANGELOG.md']
    assert result['prerelease'] is (channel == 'beta')
    assert result['make_latest'] == ('true' if channel == 'stable' else 'false')
    assert (project/'CHANGELOG.md').read_text(encoding='utf-8')==DRAFT
    assert json.loads((project/release.MANIFEST).read_text())['version']=='0.0.0'


@pytest.mark.parametrize('channel',['stable','beta'])
def test_retry_reuses_version_release_and_metadata_commit_even_on_a_different_day(project,channel):
    github=Repository();first=plan(project,github,channel)
    release.publish_build(github,first)
    count=len(github.writes)
    second=release.build_plan(project,github,SOURCE,channel,'123',first['origin']['branch'],today='2026-11-18')
    assert second['version']==first['version']
    assert second['origin']['date']=='2026-11-17'
    release.publish_build(github,second)
    assert len(github.writes)==count


def test_next_release_does_not_repeat_old_draft_bullets_or_feature_increment(project):
    github=Repository();release.publish_build(github,plan(project,github,'stable'))
    following='d'*40
    updated={**NOTES,'Bugfixes':['- Fix the next problem.']}
    text='# Changelog\n\n## New Version\n\n'+release.render_notes(updated)
    (project/'CHANGELOG.md').write_text(text,encoding='utf-8')
    github.files[following,'CHANGELOG.md']=text
    github.commits[following]={'sha':following,'tree':{'sha':'1'*40},'parents':[{'sha':SOURCE}]}
    build_plan=plan(project,github,'stable',source=following)
    assert build_plan['version']=='0.20.1'
    assert 'automatic releases' not in build_plan['notes']
    assert 'Fix the next problem' in build_plan['notes']
    assert '## 0.20.0' in build_plan['changelog']


def test_unreleased_tag_collision_is_skipped_without_retargeting_it(project):
    github=Repository();other='e'*40
    github.tags['v0.20.0']=other
    github.commits[other]={'sha':other,'parents':[]}
    assert plan(project,github,'stable')['version']=='0.21.0'
    assert github.tags['v0.20.0']==other


def test_working_copy_notes_cannot_be_published_under_an_older_source_sha(project):
    github=Repository();build_plan=plan(project,github)
    github.files[SOURCE,'CHANGELOG.md'] += '\nChanged source\n'
    with pytest.raises(ValueError,match='checked source'):
        release.publish_build(github,build_plan)
    assert not github.writes


def test_protected_main_and_fork_publication_are_not_bypassed_by_workflow():
    workflow=(Path(__file__).resolve().parents[1]/'.github/workflows/ci.yml').read_text()
    assert "github.event_name == 'push'" in workflow
    assert "github.repository == 'szech77/HA_EOS_Akkodoktor_Energiezentrale'" in workflow
    assert 'pull_request_target' not in workflow
    assert 'persist-credentials: false' in workflow
    github=release.GitHub('owner/repo','',read_only=True)
    with pytest.raises(ValueError,match='must not modify'):
        github.request('/releases','POST',{})


def test_missing_notes_divergent_sources_and_stable_branch_misuse_fail_closed(project):
    github=Repository();github.comparison='diverged'
    with pytest.raises(ValueError,match='latest stable source'):
        plan(project,github)
    with pytest.raises(ValueError,match='only originate from main'):
        release.build_plan(project,github,SOURCE,'stable',branch='feature/releases')
    (project/'CHANGELOG.md').write_text('# Changelog\n\n## New Version\n\n'+release.render_notes(EMPTY),encoding='utf-8')
    github.comparison='ahead'
    with pytest.raises(ValueError,match='no changes'):
        plan(project,github)


def test_squash_merged_stable_snapshot_allows_following_branch_release(project):
    github = Repository()
    release.publish_build(github, plan(project, github, 'stable'))
    following = 'd'*40
    text = '# Changelog\n\n## New Version\n\n'+release.render_notes(
        {**NOTES, 'Bugfixes':['- Fix the next problem.']})
    (project/'CHANGELOG.md').write_text(text, encoding='utf-8')
    github.files[following, 'CHANGELOG.md'] = text
    github.commits[following] = {'sha':following, 'tree':{'sha':'2'*40}, 'parents':[]}
    github.comparison = 'diverged'
    github.comparison_commits = [
        {'sha':'c'*40, 'commit':{'tree':github.commits[SOURCE]['tree']}},
        {'sha':following, 'commit':{'tree':github.commits[following]['tree']}},
    ]
    build_plan = plan(project, github, source=following)
    assert build_plan['version'] == '0.20.1b123'
    assert 'automatic releases' not in build_plan['notes']
    assert 'Fix the next problem' in build_plan['notes']
    assert '## New Version' not in build_plan['changelog']
    assert '## 0.20.0 - 2026-11-17' in build_plan['changelog']


@pytest.mark.parametrize('status,trees', [
    ('diverged', ['2'*40]),  # Stable changes are absent from every branch snapshot.
    ('diverged', [None]),  # Missing tree data must not count as equivalence.
    ('behind', ['1'*40]),  # An older branch still needs the stable source.
    ('unknown', ['1'*40]),
])
def test_non_equivalent_branch_snapshots_remain_blocked(project, status, trees):
    github = Repository()
    github.comparison = status
    github.comparison_commits = [{'commit':{'tree':{'sha':tree}}} for tree in trees]
    with pytest.raises(ValueError, match='latest stable source'):
        plan(project, github)
    assert not github.writes


def test_equivalent_snapshot_is_found_after_first_comparison_page(project):
    github = Repository()
    github.comparison = 'diverged'
    github.comparison_commits = [{'commit':{'tree':{'sha':'2'*40}}} for _ in range(100)]
    github.comparison_commits.append({'commit':{'tree':github.commits[BASE]['tree']}})
    assert plan(project, github)['version'] == '0.20.0b123'
    github.comparison_commits.pop()
    with pytest.raises(ValueError, match='latest stable source'):
        plan(project, github)


def test_first_publication_preserves_version_floor_from_archived_history(project):
    github=Repository();github.releases=[];github.tags={}
    assert plan(project,github,'stable')['version']=='0.20.0'


def test_partial_publication_resumes_existing_tag_without_creating_another_commit(project):
    github=Repository();first=plan(project,github)
    release.publish_build(github,first)
    github.releases.pop()  # A release API failure after creating the tag.
    count=len(github.commits)
    second=plan(project,github)
    release.publish_build(github,second)
    assert len(github.commits)==count
    assert github.releases[-1]['tag_name']=='v0.20.0b123'


def test_published_notes_and_source_parent_cannot_be_replaced(project):
    github=Repository();first=plan(project,github)
    release.publish_build(github,first)
    github.releases[-1]['body']='Different published notes'
    with pytest.raises(ValueError,match='not overwritten'):
        release.publish_build(github,plan(project,github))
    target=github.tags['v0.20.0b123']
    github.commits[target]['parents']=[{'sha':BASE}]
    with pytest.raises(ValueError,match='directly follow'):
        plan(project,github)


@pytest.mark.parametrize('text',[
    '## New Version\n### Features\n- Feature\n',
    DRAFT+'\n## New Version\n'+release.render_notes(NOTES),
    DRAFT.replace('### Security','### Features'),
])
def test_malformed_draft_is_rejected(text):
    with pytest.raises(ValueError,match='New Version'):
        release.draft_sections(text)


WORKFLOW = 'steps:\n  - uses: actions/checkout@{sha} # v{version}\n'


def dependencies(root, github, old, new, path='requirements-test.txt'):
    github.files[(BASE, path)] = old
    target = root/path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(new, encoding='utf-8')


def only_released_draft(root):
    (root/'CHANGELOG.md').write_text('# Changelog\n\n## New Version\n\n'+release.render_notes(EMPTY)
                                     +'\n## 0.19.0 - 2026-11-16\n\n'+release.render_notes(EMPTY), encoding='utf-8')


def test_dependency_patch_update_without_entry_gets_an_automatic_bugfix_note(project):
    github = Repository()
    only_released_draft(project)
    with pytest.raises(ValueError, match='no changes'):
        plan(project, github)
    # The Dependabot case: only the pin changes, nobody wrote a changelog entry.
    dependencies(project, github, 'homeassistant==2026.11.1\npytest==9.2.0\n', 'homeassistant==2026.11.2\npytest==9.2.0\n')
    result = plan(project, github, 'stable')
    assert result['version'] == '0.19.1'
    assert ('- Abhängigkeit `homeassistant` von 2026.11.1 auf 2026.11.2 aktualisiert '
            '(`requirements-test.txt`); automatisch erfasst.') in result['notes']


def test_own_entry_wins_and_minor_updates_and_actions_are_covered_once(project):
    github = Repository()
    only_released_draft(project)
    dependencies(project, github, 'bandit==1.9.4\npip-audit==2.10.1\n', 'bandit==1.10.0\npip-audit==2.10.1\n', 'requirements-dev.txt')
    old, new = WORKFLOW.format(sha='1'*40, version='7.0.1'), WORKFLOW.format(sha='2'*40, version='7.0.2')
    for name in ('ci.yml', 'other.yml'):
        dependencies(project, github, old, new, '.github/workflows/'+name)
    notes = plan(project, github)['notes']
    assert '`bandit` von 1.9.4 auf 1.10.0' in notes
    assert notes.count('GitHub Action `actions/checkout` von 7.0.1 auf 7.0.2 aktualisiert (CI)') == 1
    # A written entry naming the dependency replaces the generated one.
    text = (project/'CHANGELOG.md').read_text(encoding='utf-8').replace(
        '### Bugfixes\n\n- Keine.', '### Bugfixes\n\n- Bandit 1.10.0 meldet zusätzlich unsichere Temporärdateien.', 1)
    (project/'CHANGELOG.md').write_text(text, encoding='utf-8')
    notes = plan(project, github, build='124')['notes']
    assert 'Bandit 1.10.0 meldet' in notes and '`bandit` von' not in notes


@pytest.mark.parametrize('old,new', [('homeassistant==2026.11.2', 'homeassistant==2026.12.0'),
                                     ('pytest==9.2.0', 'pytest==10.0.0'), ('pytest==9.2.0', 'pytest==main')])
def test_major_or_unreadable_dependency_updates_need_an_own_entry(project, old, new):
    github = Repository()
    only_released_draft(project)
    dependencies(project, github, old+'\n', new+'\n')
    with pytest.raises(ValueError, match='needs its own changelog entry'):
        plan(project, github)
    name = old.split('==')[0]
    text = (project/'CHANGELOG.md').read_text(encoding='utf-8').replace(
        '### Bugfixes\n\n- Keine.', f'### Bugfixes\n\n- {name} auf die neue Hauptversion umgestellt.', 1)
    (project/'CHANGELOG.md').write_text(text, encoding='utf-8')
    assert 'neue Hauptversion' in plan(project, github)['notes']


def test_added_removed_or_unchanged_dependencies_create_no_entry():
    previous = {'requirements-test.txt': 'pytest==9.2.0\nold==1.0\n', '.github/workflows/ci.yml': WORKFLOW.format(sha='1'*40, version='7.0.1')}
    current = {'requirements-test.txt': 'pytest==9.2.0\nnew==2.0\n', '.github/workflows/ci.yml': WORKFLOW.format(sha='1'*40, version='7.0.1')}
    assert release.dependency_changes(current, previous) == []


def test_dependency_notes_keep_the_checked_changelog_for_publication(project):
    github = Repository()
    only_released_draft(project)
    dependencies(project, github, 'pytest==9.2.0\n', 'pytest==9.2.1\n')
    workflow = '.github/workflows/ci.yml'
    dependencies(project, github, WORKFLOW.format(sha='1'*40, version='7.0.1'), WORKFLOW.format(sha='1'*40, version='7.0.1'), workflow)
    text = (project/'CHANGELOG.md').read_text(encoding='utf-8')
    github.files[(SOURCE, 'CHANGELOG.md')] = text
    result = plan(project, github)
    # The provenance must hash the source changelog, not a dependency file read for the comparison.
    assert result['origin']['source_changelog_sha256'] == release.hashlib.sha256(text.encode()).hexdigest()
    release.publish_build(github, result)
    assert github.tags['v'+result['version']]


def package(**versions):
    return json.dumps({'dependencies':{'vue':versions.get('vue', '3.5.45')},
                       'devDependencies':{'vite':versions.get('vite', '8.3.6'), 'local':'file:../tool'}})


def test_frontend_package_updates_get_automatic_notes_and_majors_need_an_entry(project):
    github = Repository()
    only_released_draft(project)
    dependencies(project, github, package(), package(vue='3.5.46'), release.FRONTEND_PACKAGE)
    assert '`vue` von 3.5.45 auf 3.5.46 aktualisiert (`frontend/package.json`)' in plan(project, github)['notes']
    dependencies(project, github, package(), package(vite='9.0.0'), release.FRONTEND_PACKAGE)
    with pytest.raises(ValueError, match='vite 8.3.6 -> 9.0.0 needs its own changelog entry'):
        plan(project, github, build='124')


def test_npm_ranges_and_invalid_package_files_are_not_treated_as_pins():
    assert release._npm('{"dependencies":{"a":"^1.0.0","b":"1.2.3","c":"file:../c"}}') == {'b':'1.2.3'}
    assert release._npm(json.dumps({'devDependencies': {
        'ranged': 'npm:typescript@^7.0.2', 'tagged': 'npm:typescript@latest',
        'scoped_range': 'npm:@typescript/typescript6@~6.0.2',
        'missing_version': 'npm:@typescript/typescript6', 'invalid': 'npm:typescript@7.0.2/extra',
    }})) == {}
    assert release._npm('not json') == {}


@pytest.mark.parametrize('name,target,old,new', [
    ('typescript', '@typescript/typescript6', '6.0.2', '6.0.3'),
    ('@typescript/native', 'typescript', '7.0.2', '7.1.0'),
])
def test_exact_npm_alias_updates_get_automatic_release_notes(project, name, target, old, new):
    github = Repository()
    only_released_draft(project)
    dependencies(project, github,
                 json.dumps({'devDependencies': {name: f'npm:{target}@{old}'}}),
                 json.dumps({'devDependencies': {name: f'npm:{target}@{new}'}}),
                 release.FRONTEND_PACKAGE)
    result = plan(project, github, 'stable')
    assert result['version'] == '0.19.1'
    assert f'`{name}` von {old} auf {new} aktualisiert (`frontend/package.json`)' in result['notes']


@pytest.mark.parametrize('name,old,new', [
    ('typescript', '5.9.3', 'npm:@typescript/typescript6@6.0.2'),
    ('@typescript/native', 'npm:typescript@7.0.2', 'npm:typescript@8.0.0'),
])
def test_npm_alias_major_updates_need_an_own_entry(project, name, old, new):
    github = Repository()
    only_released_draft(project)
    dependencies(project, github,
                 json.dumps({'devDependencies': {name: old}}),
                 json.dumps({'devDependencies': {name: new}}), release.FRONTEND_PACKAGE)
    with pytest.raises(ValueError, match='needs its own changelog entry'):
        plan(project, github)
    text = (project/'CHANGELOG.md').read_text(encoding='utf-8').replace(
        '### Bugfixes\n\n- Keine.', f'### Bugfixes\n\n- {name} auf die neue Hauptversion umgestellt.', 1)
    (project/'CHANGELOG.md').write_text(text, encoding='utf-8')
    assert 'neue Hauptversion' in plan(project, github)['notes']


def built(root, files={'eos-vue.js':'globalThis.EosForecast={};'}):
    folder = root/release.BUNDLE_DIR
    folder.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (folder/name).write_text(content, encoding='utf-8')


def test_publishing_requires_the_built_frontend_bundle(project):
    with pytest.raises(ValueError, match='npm run build'):
        release.bundle_files(project)
    built(project, {'notes.txt':'ignored'})
    with pytest.raises(ValueError, match='npm run build'):
        release.bundle_files(project)
    built(project)
    assert release.bundle_files(project) == {release.BUNDLE_ENTRY:'globalThis.EosForecast={};'}


def test_the_release_commit_ships_the_built_bundle_with_its_provenance(project):
    github = Repository()
    built(project)
    bundle = release.bundle_files(project)
    result = plan(project, github)
    release.publish_build(github, result, bundle)
    target = github.tags['v'+result['version']]
    assert github.files[target, release.BUNDLE_ENTRY] == 'globalThis.EosForecast={};'
    origin = json.loads(github.files[target, release.ORIGIN])
    assert origin['bundle_sha256'] == release._bundle_digest(bundle)
    # A retry of the same run resumes the published release instead of building a second one.
    writes = len(github.writes)
    release.publish_build(github, plan(project, github), bundle)
    assert not any(path in ('/git/trees', '/git/commits') for path, _ in github.writes[writes:])


def test_bundle_files_cannot_overwrite_other_release_paths(project):
    github = Repository()
    with pytest.raises(ValueError, match='inside the built frontend folder'):
        release.publish_build(github, plan(project, github), {release.MANIFEST:'{}'})
    assert not github.writes
