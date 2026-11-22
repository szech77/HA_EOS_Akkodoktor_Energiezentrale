"""Wait for an explicit release decision; a deliberate no is a successful skip."""
import argparse
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError

if __package__:
    from .release import GitHub
else:
    from release import GitHub

ANSWERS = {'ja': 'approved', 'yes': 'approved', 'nein': 'denied', 'no': 'denied'}


def decision(github, issue, approver):
    """Read all comments in order. Only the named human's first exact answer counts."""
    for page in range(1, 101):
        comments = github.request(f'/issues/{issue}/comments?per_page=100&page={page}')
        if not isinstance(comments, list):
            raise ValueError('GitHub did not return issue comments')
        for comment in comments:
            if not isinstance(comment, dict) or not isinstance(comment.get('user'), dict):
                raise ValueError('GitHub returned an invalid issue comment')
            user = comment.get('user') or {}
            body = comment.get('body')
            if (user.get('type') == 'User' and str(user.get('login', '')).casefold() == approver.casefold()
                    and isinstance(body, str) and body.strip().casefold() in ANSWERS):
                return ANSWERS[body.strip().casefold()]
        if len(comments) < 100:
            break
    else:
        raise ValueError('Too many comments to verify the release decision')
    state = github.request(f'/issues/{issue}')
    if not isinstance(state, dict) or state.get('state') not in ('open', 'closed'):
        raise ValueError('GitHub did not return the decision issue')
    return 'closed' if state['state'] == 'closed' else None


def wait_for_decision(github, issue, approver, timeout, poll, *, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + timeout
    while clock() < deadline:
        answer = decision(github, issue, approver)
        if answer is not None:
            return answer
        sleep(min(poll, max(0., deadline-clock())))
    return 'timeout'


def append(path, text):
    if path:
        with Path(path).open('a', encoding='utf-8') as output:
            output.write(text)


def request_decision(github, *, repository, commit, branch, run_id, attempt, approver,
                     timeout_minutes, poll_seconds, output, summary, create_only=False):
    if (not re.fullmatch(r'[0-9a-f]{40}', commit)
            or not re.fullmatch(r'[1-9][0-9]*', run_id)
            or not re.fullmatch(r'[1-9][0-9]*', attempt)
            or not re.fullmatch(r'[A-Za-z0-9-]{1,39}', approver)
            or not re.fullmatch(r'(?:main|(?:feature|bug|bugfix)/[^\s`\x00-\x1f]{1,240})', branch)
            or not 1 <= timeout_minutes <= 60 or not 1 <= poll_seconds <= 60):
        raise ValueError('Invalid release decision context')
    run_url = f'https://github.com/{repository}/actions/runs/{run_id}'
    until = datetime.now(timezone.utc) + timedelta(minutes=timeout_minutes)
    body = (f'Release für `{branch}` veröffentlichen?\n\n'
            f'- Geprüfter Quellcommit: [{commit}](https://github.com/{repository}/commit/{commit})\n'
            f'- [CI-Lauf {run_id}, Versuch {attempt}]({run_url})\n'
            f'- Kanal: {"stabil" if branch == "main" else "Beta"}\n\n'
            f'@{approver}: Bitte als eigenen Kommentar exakt **ja** oder **nein** antworten '
            f'(auch **yes** / **no**). Nur deine erste eindeutige Antwort zählt.\n\n'
            f'**ja** veröffentlicht diesen geprüften Stand. **nein**, das Schließen des Issues '
            f'oder keine Antwort bis {until:%Y-%m-%d %H:%M UTC} überspringt das Release erfolgreich. '
            'Technische Fehler bleiben Fehler. Die Anfrage gilt nur für diesen Lauf und Versuch.')
    created = github.request('/issues', 'POST', {
        'title': f'Release entscheiden: {branch} ({run_id}/{attempt})',
        'body': body, 'assignees': [approver]})
    issue = created.get('number') if isinstance(created, dict) else None
    if type(issue) is not int or issue <= 0:
        raise ValueError('GitHub did not create a decision issue')
    # Persist immediately so the workflow's always() step can close an abandoned request.
    append(output, f'issue_number={issue}\n')
    url = f'https://github.com/{repository}/issues/{issue}'
    append(summary, f'### Release-Entscheidung\n\n[{branch} · {commit[:12]}: ja / nein]({url})\n\n')
    print('Release decision:', url, flush=True)
    if create_only:
        return issue
    return finish_decision(github, issue, approver, timeout_minutes, poll_seconds, output, summary)


def finish_decision(github, issue, approver, timeout_minutes, poll_seconds, output, summary):
    if (type(issue) is not int or issue <= 0 or not re.fullmatch(r'[A-Za-z0-9-]{1,39}', approver)
            or not 1 <= timeout_minutes <= 60 or not 1 <= poll_seconds <= 60):
        raise ValueError('Invalid release decision parameters')
    result = wait_for_decision(github, issue, approver, timeout_minutes*60, poll_seconds)
    append(output, f'approved={str(result == "approved").lower()}\ndecision={result}\n')
    append(summary, f'Ergebnis: **{result}**. '
                    f'{"Release freigegeben." if result == "approved" else "Kein Release; Entscheidungsschritt erfolgreich."}\n')
    print('Release decision:', result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', required=True)
    operation = parser.add_mutually_exclusive_group()
    operation.add_argument('--close', type=int, help='Close a decision issue, including after a cancellation or error')
    operation.add_argument('--create-only', action='store_true', help='Create the request and show its link before waiting')
    operation.add_argument('--wait-for', type=int, help='Wait for the issue created by the preceding workflow step')
    parser.add_argument('--commit', default=os.environ.get('COMMIT', ''))
    parser.add_argument('--branch', default=os.environ.get('BRANCH', ''))
    parser.add_argument('--run-id', default=os.environ.get('RUN_ID', ''))
    parser.add_argument('--attempt', default=os.environ.get('RUN_ATTEMPT', ''))
    parser.add_argument('--approver', default='szech77')
    parser.add_argument('--timeout-minutes', type=int, default=60)
    parser.add_argument('--poll-seconds', type=int, default=15)
    args = parser.parse_args(argv)
    try:
        github = GitHub(args.repository, os.environ.get('GH_TOKEN', ''))
        if args.close is not None:
            if args.close <= 0:
                raise ValueError('Invalid decision issue number')
            github.request(f'/issues/{args.close}', 'PATCH', {'state': 'closed'})
        elif args.wait_for is not None:
            finish_decision(github, args.wait_for, args.approver, args.timeout_minutes, args.poll_seconds,
                            os.environ.get('GITHUB_OUTPUT'), os.environ.get('GITHUB_STEP_SUMMARY'))
        else:
            request_decision(github, repository=args.repository, commit=args.commit, branch=args.branch,
                             run_id=args.run_id, attempt=args.attempt, approver=args.approver,
                             timeout_minutes=args.timeout_minutes, poll_seconds=args.poll_seconds,
                             output=os.environ.get('GITHUB_OUTPUT'), summary=os.environ.get('GITHUB_STEP_SUMMARY'),
                             create_only=args.create_only)
    except HTTPError as error:
        print(f'Release decision failed: GitHub HTTP {error.code}')
        return 1
    except (OSError, ValueError, KeyError, TypeError) as error:
        # Never expose raw responses, comments, credentials or exception messages.
        print('Release decision failed:', type(error).__name__)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
