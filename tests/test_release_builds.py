"""CI-generated versions, immutable source snapshots and safe publication retries."""
import base64
from copy import deepcopy
import json
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

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
            return {'status':self.comparison}
        if path == '/git/matching-refs/tags/v':
            return [{'ref':'refs/tags/'+tag,'object':{'sha':sha,'type':'commit'}} for tag,sha in self.tags.items()]
        if path == '/git/trees':
            sha=f'{len(self.trees)+100:040x}';self.trees[sha]=data
            return {'sha':sha}
        if path == '/git/commits' and method == 'POST':
            sha=f'{len(self.commits)+200:040x}'
            self.commits[sha]={'sha':sha,'parents':[{'sha':value} for value in data['parents']], 'tree':{'sha':data['tree']}}
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


def test_generated_tag_has_matching_manifest_date_history_and_checked_source_parent(project):
    github=Repository();build_plan=plan(project,github,'stable')
    result=release.publish_build(github,build_plan)
    target=github.tags['v0.20.0']
    assert target!=SOURCE
    assert github.commits[target]['parents']==[{'sha':SOURCE}]
    manifest=json.loads(github.files[target,release.MANIFEST])
    assert manifest=={'version':'0.20.0','requirements':['example==1']}
    assert '## 0.20.0 - 2026-11-17' in github.files[target,'CHANGELOG.md']
    assert '## 0.19.0' in github.files[target,'CHANGELOG.md']
    assert '## New Version' not in github.files[target,'CHANGELOG.md']
    assert result['prerelease'] is False and result['make_latest']=='true'
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
