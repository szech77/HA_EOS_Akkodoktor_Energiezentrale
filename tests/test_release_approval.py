"""Only an explicit, authorized release approval publishes; a no succeeds."""
from copy import deepcopy
from unittest.mock import Mock, patch
from urllib.error import HTTPError

import pytest

from tools import release_approval as approval

COMMIT = 'a' * 40


def comment(body, login='szech77', kind='User'):
    return {'body': body, 'user': {'login': login, 'type': kind}}


class GitHub:
    def __init__(self, comments=(), state='open'):
        self.comments = list(comments)
        self.state = state
        self.calls = []
        self.number = 100

    def request(self, path, method='GET', data=None):
        self.calls.append((path, method, deepcopy(data)))
        if path == '/issues' and method == 'POST':
            self.number += 1
            return {'number': self.number}
        if '/comments?' in path:
            page = int(path.rsplit('=', 1)[1])
            return self.comments[(page-1)*100:page*100]
        if method == 'PATCH':
            self.state = data['state']
        return {'state': self.state}


@pytest.mark.parametrize('body,expected', [('ja', 'approved'), (' YES\n', 'approved'),
                                          ('nein', 'denied'), ('No', 'denied')])
def test_only_exact_answers_of_the_configured_human_count(body, expected):
    github = GitHub([comment('ja', login='outsider'), comment('ja', kind='Bot'),
                     comment('Ich sage ja'), comment('`ja`'), comment(body, login='SZECH77')])
    assert approval.decision(github, 101, 'szech77') == expected


def test_a_comment_after_the_first_page_is_seen_and_the_first_decision_is_final():
    github = GitHub([comment('ja', login='outsider')] * 100 + [comment('nein'), comment('ja')])
    assert approval.decision(github, 101, 'szech77') == 'denied'
    assert github.calls[-1][0].endswith('page=2')


def test_closing_without_an_answer_skips_and_an_open_issue_keeps_waiting():
    assert approval.decision(GitHub(state='closed'), 101, 'szech77') == 'closed'
    assert approval.decision(GitHub(), 101, 'szech77') is None


def test_timeout_is_a_successful_skip_and_never_polls_after_the_deadline():
    github = GitHub()
    now = [0.]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    assert approval.wait_for_decision(github, 101, 'szech77', 25, 15,
                                     clock=lambda: now[0], sleep=sleep) == 'timeout'
    assert sleeps == [15, 10]
    assert len(github.calls) == 4


def test_api_failure_is_an_error_rather_than_a_no_or_an_approval():
    github = Mock()
    github.request.side_effect = OSError('private response must not be printed')
    with pytest.raises(OSError):
        approval.wait_for_decision(github, 101, 'szech77', 60, 15)


@pytest.mark.parametrize('response', [None, {}, 'invalid', [None], [{'user': 'invalid'}]])
def test_missing_or_invalid_comment_responses_cannot_approve(response):
    with pytest.raises(ValueError):
        approval.decision(Mock(request=Mock(return_value=response)), 101, 'szech77')


def request(github, tmp_path, **changes):
    return approval.request_decision(github, repository='owner/repo', commit=COMMIT,
                                    branch='feature/releases', run_id='123', attempt='1',
                                    approver='szech77', timeout_minutes=60, poll_seconds=15,
                                    output=tmp_path/'output', summary=tmp_path/'summary', **changes)


@pytest.mark.parametrize('result', ['approved', 'denied', 'closed', 'timeout'])
def test_outputs_bind_the_decision_to_the_checked_source_and_only_yes_publishes(tmp_path, result):
    github = GitHub()
    with patch.object(approval, 'wait_for_decision', return_value=result):
        assert request(github, tmp_path) == result
    payload = github.calls[0][2]
    assert COMMIT in payload['body']
    assert '/actions/runs/123' in payload['body']
    assert payload['assignees'] == ['szech77']
    output = (tmp_path/'output').read_text()
    assert 'issue_number=101\n' in output
    assert f'approved={str(result == "approved").lower()}\n' in output
    assert f'decision={result}\n' in output
    assert 'https://github.com/owner/repo/issues/101' in (tmp_path/'summary').read_text()


def test_failure_after_issue_creation_keeps_its_number_for_workflow_cleanup(tmp_path):
    with patch.object(approval, 'wait_for_decision', side_effect=OSError()):
        with pytest.raises(OSError):
            request(GitHub(), tmp_path)
    assert (tmp_path/'output').read_text() == 'issue_number=101\n'


def test_rerunning_needs_a_new_issue_instead_of_reusing_an_old_approval(tmp_path):
    github = GitHub()
    with patch.object(approval, 'wait_for_decision', return_value='approved'):
        request(github, tmp_path)
        request(github, tmp_path)
    assert [method for _, method, _ in github.calls] == ['POST', 'POST']
    assert 'issue_number=102' in (tmp_path/'output').read_text()


def test_invalid_context_cannot_create_an_issue(tmp_path):
    github = GitHub()
    with pytest.raises(ValueError):
        approval.request_decision(github, repository='owner/repo', commit='bad', branch='main',
                                  run_id='123', attempt='1', approver='szech77', timeout_minutes=60,
                                  poll_seconds=15, output=tmp_path/'output', summary=None)
    assert github.calls == []


def test_cleanup_closes_the_issue_without_creating_another_one():
    github = GitHub()
    with patch.object(approval, 'GitHub', return_value=github):
        assert approval.main(['--repository', 'owner/repo', '--close', '101']) == 0
    assert github.calls == [('/issues/101', 'PATCH', {'state': 'closed'})]


@pytest.mark.parametrize('answer,approved', [('ja', 'true'), ('nein', 'false')])
def test_cli_answers_complete_successfully_and_cleanup_closes_the_same_request(tmp_path, answer, approved):
    github = GitHub([comment(answer)])
    env = {'COMMIT': COMMIT, 'BRANCH': 'main', 'RUN_ID': '123', 'RUN_ATTEMPT': '2',
           'GITHUB_OUTPUT': str(tmp_path/'output'), 'GITHUB_STEP_SUMMARY': str(tmp_path/'summary')}
    with patch.object(approval, 'GitHub', return_value=github), patch.dict(approval.os.environ, env):
        assert approval.main(['--repository', 'owner/repo']) == 0
        assert approval.main(['--repository', 'owner/repo', '--close', '101']) == 0
    assert f'approved={approved}\n' in (tmp_path/'output').read_text()
    assert github.state == 'closed'
    assert 'Versuch 2' in github.calls[0][2]['body']


def test_request_link_is_available_before_the_separate_wait_step(tmp_path):
    github = GitHub([comment('nein')])
    env = {'COMMIT': COMMIT, 'BRANCH': 'main', 'RUN_ID': '123', 'RUN_ATTEMPT': '1',
           'GITHUB_OUTPUT': str(tmp_path/'output'), 'GITHUB_STEP_SUMMARY': str(tmp_path/'summary')}
    with patch.object(approval, 'GitHub', return_value=github), patch.dict(approval.os.environ, env):
        assert approval.main(['--repository', 'owner/repo', '--create-only']) == 0
        assert (tmp_path/'output').read_text() == 'issue_number=101\n'
        assert '/issues/101' in (tmp_path/'summary').read_text()
        assert len(github.calls) == 1
        assert approval.main(['--repository', 'owner/repo', '--wait-for', '101']) == 0
    assert 'approved=false\n' in (tmp_path/'output').read_text()


@pytest.mark.parametrize('error', [OSError('private response'),
                                  HTTPError('https://example.invalid', 403, 'private response', {}, None)])
def test_cli_failures_stay_failed_and_do_not_disclose_raw_errors(capsys, error):
    with patch.object(approval, 'GitHub', side_effect=error):
        assert approval.main(['--repository', 'owner/repo', '--close', '101']) == 1
    assert 'private response' not in capsys.readouterr().out
