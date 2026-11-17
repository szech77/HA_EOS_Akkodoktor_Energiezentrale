"""Working-branch draft cleanup, immutable history and checks for the new head."""
from copy import deepcopy
from pathlib import Path
from urllib.error import HTTPError
from unittest.mock import MagicMock

import pytest
import yaml

from tools import release
from test_release_builds import SOURCE, DRAFT, EMPTY, NOTES, Repository, plan, project


def branch_after_stable(project, notes=None):
    github = Repository()
    release.publish_build(github, plan(project, github, 'stable'))
    source = 'd'*40
    text = DRAFT.replace(release.render_notes(NOTES), release.render_notes(notes or {
        **NOTES, 'Bugfixes':['- Fix the next problem.']}))
    github.files[source, 'CHANGELOG.md'] = text
    github.files[source, release.MANIFEST] = github.files[SOURCE, release.MANIFEST]
    github.commits[source] = {'sha':source, 'tree':{'sha':'2'*40}, 'parents':[{'sha':SOURCE}]}
    github.branches['feature/releases'] = source
    github.writes.clear()
    return github, source, text


def test_cleanup_removes_only_released_bullets_and_preserves_history_and_manifest(project):
    github, source, text = branch_after_stable(project)
    releases, tags = deepcopy(github.releases), dict(github.tags)
    target = release.clean_branch_changelog(github, source, 'feature/releases')
    cleaned = github.files[target, 'CHANGELOG.md']
    assert release.draft_sections(cleaned) == {**EMPTY, 'Bugfixes':['- Fix the next problem.']}
    assert release.version_history(cleaned) == release.version_history(text)
    assert github.files[target, release.MANIFEST] == github.files[source, release.MANIFEST]
    assert github.commits[target]['parents'] == [{'sha':source}]
    assert github.branches['feature/releases'] == target
    assert github.writes[-1] == ('/actions/workflows/ci.yml/dispatches', {'ref':'feature/releases'})
    assert github.releases == releases and github.tags == tags
    cleanup_tree = github.trees[github.commits[target]['tree']['sha']]
    assert [row['path'] for row in cleanup_tree['tree']] == ['CHANGELOG.md']
    github.writes.clear()
    assert release.clean_branch_changelog(github, target, 'feature/releases') is None
    assert not github.writes


def test_cleanup_keeps_new_and_reworded_notes_and_does_not_consume_beta_notes(project):
    github, source, _ = branch_after_stable(project, {
        **EMPTY, 'Features':['- Adds improved automatic releases.'], 'Security':['- Fix a security issue.']})
    assert release.clean_branch_changelog(github, source, 'feature/releases') is None
    assert not github.writes
    github.releases.append({'tag_name':'v0.21.0b999', 'prerelease':True})
    assert release.clean_branch_changelog(github, source, 'feature/releases') is None
    assert not github.writes


def test_cleanup_can_leave_all_four_categories_empty(project):
    github, source, _ = branch_after_stable(project, NOTES)
    target = release.clean_branch_changelog(github, source, 'feature/releases')
    assert release.draft_sections(github.files[target, 'CHANGELOG.md']) == EMPTY


@pytest.mark.parametrize('branch', ['main', 'dependabot/pip/example', 'refs/heads/main', 'feature/bad\nref'])
def test_cleanup_never_writes_main_or_other_branch_families(project, branch):
    github, source, _ = branch_after_stable(project)
    with pytest.raises(ValueError, match='working branches'):
        release.clean_branch_changelog(github, source, branch)
    assert not github.writes


def test_cleanup_does_nothing_before_first_stable_release(project):
    github = Repository()
    github.releases.clear()
    assert release.clean_branch_changelog(github, SOURCE, 'feature/releases') is None
    assert not github.writes


def test_cleanup_refuses_a_newer_branch_head_without_writes(project):
    github, source, text = branch_after_stable(project)
    newer = 'e'*40
    github.branches['feature/releases'] = newer
    github.commits[newer] = {'parents':[{'sha':source}]}
    github.files[newer, 'CHANGELOG.md'] = text+'\n- A newer edit.\n'
    with pytest.raises(ValueError, match='Branch advanced'):
        release.clean_branch_changelog(github, source, 'feature/releases')
    assert github.branches['feature/releases'] == newer
    assert not github.writes


def test_cleanup_never_overwrites_a_concurrent_push_or_dispatches_failed_update(project):
    github, source, _ = branch_after_stable(project)
    github.concurrent_head = 'e'*40
    with pytest.raises(HTTPError, match='Not a fast forward'):
        release.clean_branch_changelog(github, source, 'feature/releases')
    assert github.branches['feature/releases'] == 'e'*40
    assert not any(path.endswith('/dispatches') for path, _ in github.writes)


def test_retry_after_dispatch_failure_reuses_cleanup_commit(project):
    github, source, _ = branch_after_stable(project)
    github.fail_dispatch = True
    with pytest.raises(HTTPError, match='Temporary dispatch failure'):
        release.clean_branch_changelog(github, source, 'feature/releases')
    target = github.branches['feature/releases']
    writes = len(github.writes)
    github.fail_dispatch = False
    assert release.clean_branch_changelog(github, source, 'feature/releases') == target
    assert len(github.writes) == writes+1


def test_retry_rejects_a_commit_that_also_changes_application_code(project):
    github, source, _ = branch_after_stable(project)
    target = release.clean_branch_changelog(github, source, 'feature/releases')
    github.comparison_files.append(release.MANIFEST)
    github.writes.clear()
    with pytest.raises(ValueError, match='Branch advanced'):
        release.clean_branch_changelog(github, source, 'feature/releases')
    assert github.branches['feature/releases'] == target
    assert not github.writes


def test_old_bullets_stay_excluded_after_later_stable_source_drafts_are_cleaned(project):
    github, source, _ = branch_after_stable(project)
    cleaned_source = release.clean_branch_changelog(github, source, 'feature/releases')
    text = github.files[cleaned_source, 'CHANGELOG.md']
    (project/'CHANGELOG.md').write_text(text, encoding='utf-8')
    release.publish_build(github, plan(project, github, 'stable', source=cleaned_source))
    next_source = 'f'*40
    next_notes = {**NOTES, 'Bugfixes':['- Another new fix.']}
    (project/'CHANGELOG.md').write_text('## New Version\n\n'+release.render_notes(next_notes), encoding='utf-8')
    next_plan = plan(project, github, 'stable', source=next_source)
    assert next_plan['version'] == '0.20.2'
    assert 'automatic releases' not in next_plan['notes']
    assert 'Another new fix' in next_plan['notes']


def test_workflow_dispatch_accepts_empty_success_response():
    github = release.GitHub('owner/repo', 'example-test-token')
    github.opener = MagicMock()
    github.opener.open.return_value.__enter__.return_value.status = 204
    assert github.request('/actions/workflows/ci.yml/dispatches', 'POST', {'ref':'feature/releases'}) is None


def test_cleanup_workflow_checks_new_head_without_publishing_a_second_beta():
    workflow = yaml.safe_load((Path(__file__).resolve().parents[1]/'.github/workflows/ci.yml').read_text())
    jobs = workflow['jobs']
    cleanup = jobs['clean_changelog']
    assert set(cleanup['needs']) == {'tests', 'security', 'integration'}
    assert cleanup['permissions'] == {'contents':'write', 'actions':'write'}
    assert "github.event_name == 'push'" in cleanup['if']
    assert "github.repository == 'szech77/HA_EOS_Akkodoktor_Energiezentrale'" in cleanup['if']
    assert "refs/heads/main" not in cleanup['if']
    assert 'clean_changelog' in jobs['required']['needs']
    enforce = jobs['required']['steps'][0]['run']
    assert 'test "$CLEANUP" = success' in enforce
    assert 'test "$CLEANUP" = skipped' in enforce
    assert "github.event_name == 'push'" in jobs['publish']['if']
