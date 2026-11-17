"""Semgrep completeness, stable Code Scanning metadata and private report content."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest

from tools.security_sarif import semgrep, semgrep_catalog, semgrep_targets, semgrep_version
from tools.semgrep_scan import checked_rule_tests, main
from test_energy import temporary_project_directory

FILE = 'custom_components/example.py'
RULE = 'eos.python.subprocess-shell'


def scan(findings=False):
    return {'version':semgrep_version(), 'eos_scan_exit_code':int(findings), 'errors':[], 'skipped_rules':[],
        'eos_core_exit_codes':[0], 'rules_by_engine':[[key,'OSS'] for key in semgrep_catalog()],
        'paths':{'scanned':[FILE]}, 'results':[{'check_id':RULE, 'path':FILE, 'start':{'line':8},
            'extra':{'message':'private-message', 'lines':'private-code', 'metavars':{'value':'private-secret'},
                     'metadata':{'security-severity':'10.0', 'help':'private-help'}, 'is_ignored':False}}] if findings else []}


def test_semgrep_reports_actionable_security_metadata_but_never_expanded_private_values():
    run = semgrep(scan(True), expected={FILE})['runs'][0]
    finding = run['results'][0]
    rule = next(value for value in run['tool']['driver']['rules'] if value['id'] == RULE)
    assert run['tool']['driver']['name'] == 'Semgrep'
    assert run['tool']['driver']['version'] == semgrep_version()
    assert run['automationDetails']['id'] == 'source-security/semgrep/'
    assert finding['ruleId'] == RULE and finding['level'] == 'error'
    assert finding['locations'][0]['physicalLocation']['region']['startLine'] == 8
    assert rule['properties']['security-severity'] == '8.8'
    assert rule['properties']['precision'] == 'high'
    assert 'external/cwe/cwe-78' in rule['properties']['tags']
    assert 'shell=False' in rule['help']['text']
    assert 'private-' not in json.dumps(run)


@pytest.mark.parametrize('change', [
    {'version':'0.0.0'}, {'eos_scan_exit_code':2}, {'eos_scan_exit_code':True},
    {'eos_scan_exit_code':1}, {'errors':[{'message':'private-error'}]}, {'skipped_rules':['invalid-rule']},
    {'paths':{'scanned':[]}}, {'paths':{'scanned':['../private.py']}},
    {'time':{'fixpoint_timeouts':['rule']}},
    {'time':None},
    {'eos_core_exit_codes':[2]}, {'eos_core_exit_codes':[]}, {'rules_by_engine':[]},
    {'rules_by_engine':[['unknown-rule','OSS']]}, {'rules_by_engine':[['unknown-rule','PRO']]},
])
def test_incomplete_scans_cannot_be_published_as_clean(change):
    with pytest.raises(ValueError):
        semgrep({**scan(), **change}, expected={FILE})


def test_missing_scan_fields_missing_target_and_ignored_findings_are_rejected():
    for field in ('results','errors','paths','skipped_rules','eos_scan_exit_code'):
        data = scan()
        data.pop(field)
        with pytest.raises(ValueError):
            semgrep(data, expected={FILE})
    with pytest.raises(ValueError):
        semgrep(scan(), expected={FILE,'tools/other.py'})
    with pytest.raises(ValueError):
        semgrep(scan(), expected=set())
    for changes in ({'check_id':'other-rule'}, {'path':'../private.py'}, {'start':{'line':0}},
                    {'path':'tools/unscanned.py'}, {'extra':None}, {'path':17}):
        data = scan(True)
        data['results'][0].update(changes)
        with pytest.raises(ValueError):
            semgrep(data, expected={FILE})


def test_nosemgrep_suppressions_remain_blocking_findings():
    data = scan(True)
    data['results'][0]['extra']['is_ignored'] = True
    results = semgrep(data, expected={FILE})['runs'][0]['results']
    assert [item['ruleId'] for item in results] == [RULE]


def test_windows_paths_and_empty_complete_reports_remain_stable_for_code_scanning():
    data = scan(True)
    data['paths']['scanned'] = [FILE.replace('/','\\')]
    data['results'][0]['path'] = FILE.replace('/','\\')
    output = semgrep(data, expected={FILE})
    assert output['runs'][0]['results'][0]['locations'][0]['physicalLocation']['artifactLocation']['uri'] == FILE
    assert semgrep(scan(), expected={FILE})['runs'][0]['results'] == []


def test_every_rule_needs_a_passing_positive_fixture_and_missing_tests_fail():
    known = set(semgrep_catalog())
    text = ''.join(f'# ruleid: {key}\nbad()\n# ok: {key}\ngood()\n' for key in sorted(known))
    results = [{'check_id':key,'start':{'line':index*4+2}} for index,key in enumerate(sorted(known))]
    with temporary_project_directory() as root:
        fixture = root/'fixture.py'
        fixture.write_text(text,encoding='utf-8')
        assert checked_rule_tests({'results':results},fixture,known) == 7
        for bad in ([], results[:-1], results+[{'check_id':RULE,'start':{'line':4}}]):
            with pytest.raises(ValueError):
                checked_rule_tests({'results':bad},fixture,known)
        fixture.write_text(text.replace('# ok:', '# removed:'),encoding='utf-8')
        with pytest.raises(ValueError):
            checked_rule_tests({'results':results},fixture,known)


@pytest.mark.parametrize('findings', [False, True])
def test_runner_keeps_findings_blocking_without_logging_code_and_disables_cloud_metrics(findings):
    def execute(command, **kwargs):
        assert isinstance(command,list) and kwargs.get('shell',False) is False
        assert kwargs['env']['SEMGREP_SEND_METRICS'] == 'off'
        assert 'SEMGREP_APP_TOKEN' not in kwargs['env']
        assert '-strict' in command and '-json_nodots' in command and '-timeout' in command
        language = command[command.index('-lang')+1]
        target = command[-1]
        assert command[-2] == language and target in semgrep_targets()
        calls.append(target)
        data = scan(findings and target == first_python)
        data['paths']['scanned'] = [target.replace('/','\\')]
        data['rules_by_engine'] = [[key,'OSS'] for key in semgrep_catalog() if key.startswith('eos.'+language+'.')]
        if data['results']:
            data['results'][0]['path'] = target
        kwargs['stdout'].write(json.dumps(data))
        kwargs['stderr'].write('private-stderr')
        return subprocess.CompletedProcess(command,0)
    calls = []
    first_python = min(value for value in semgrep_targets() if value.endswith('.py'))
    with temporary_project_directory() as root, patch('tools.semgrep_scan.subprocess.run',side_effect=execute):
        output = StringIO()
        with redirect_stdout(output), patch.dict('os.environ',{'SEMGREP_APP_TOKEN':'private-token'}):
            assert main(['--executable','scanner','--output',str(root/'scan.json')]) == int(findings)
        assert 'private-' not in output.getvalue()
        assert (root/'scan.json').is_file()
    # semgrep-core only supports one target per `-lang` run: every file is scanned once.
    assert sorted(calls) == sorted(semgrep_targets())


def test_engine_failure_or_malformed_output_is_not_a_clean_scan_or_a_raw_log():
    with temporary_project_directory() as root:
        target = root/'scan.json'
        target.write_text('stale report',encoding='utf-8')
        output = StringIO()
        with patch('tools.semgrep_scan.subprocess.run',side_effect=OSError('private-error')), redirect_stdout(output):
            assert main(['--executable','missing','--output',str(target)]) == 2
        assert not target.exists()
        assert 'private-error' not in output.getvalue()


def test_one_failing_file_run_fails_the_whole_scan_without_a_report():
    def execute(command, **kwargs):
        kwargs['stdout'].write('{}' if command[-1] == broken else json.dumps({
            **scan(), 'paths':{'scanned':[command[-1]]},
            'rules_by_engine':[[key,'OSS'] for key in semgrep_catalog()
                               if key.startswith('eos.'+command[command.index('-lang')+1]+'.')]}))
        return subprocess.CompletedProcess(command,0)
    broken = max(semgrep_targets())
    with temporary_project_directory() as root, patch('tools.semgrep_scan.subprocess.run',side_effect=execute):
        with redirect_stdout(StringIO()):
            assert main(['--executable','scanner','--output',str(root/'scan.json')]) == 2
        assert not (root/'scan.json').exists()
