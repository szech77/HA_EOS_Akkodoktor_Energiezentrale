"""Run local Semgrep CE without exposing matched code or parser diagnostics."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory

import yaml

if __package__:
    from .security_sarif import ROOT, semgrep, semgrep_catalog, semgrep_targets, semgrep_version
else:
    from security_sarif import ROOT, semgrep, semgrep_catalog, semgrep_targets, semgrep_version


def rule_groups():
    groups = []
    for path in sorted((ROOT/'.semgrep/rules').iterdir()):
        if path.suffix not in ('.yml','.yaml'):
            continue
        rules = yaml.safe_load(path.read_text(encoding='utf-8'))['rules']
        languages = {tuple(rule['languages']) for rule in rules}
        if len(languages) != 1 or next(iter(languages)) not in (('python',),('javascript',)):
            raise ValueError('Rule groups must use one supported language')
        language = next(iter(languages))[0]
        groups.append({'path':path.relative_to(ROOT).as_posix(), 'language':language,
                       'suffix':'.py' if language == 'python' else '.js', 'rules':{rule['id'] for rule in rules}})
    if {key for group in groups for key in group['rules']} != set(semgrep_catalog()):
        raise ValueError('Incomplete rule groups')
    return groups


def checked_rule_tests(data, fixture, known):
    positive, negative = set(), set()
    for line, text in enumerate(fixture.read_text(encoding='utf-8').splitlines(), 1):
        marker = re.fullmatch(r'\s*(?:#|//)\s*(ruleid|ok):\s*([A-Za-z0-9_.:-]+)\s*', text)
        if marker:
            if marker[2] not in known:
                raise ValueError('Unknown fixture rule')
            (positive if marker[1] == 'ruleid' else negative).add((marker[2],line+1))
    actual = {(item['check_id'],item['start']['line']) for item in data['results']}
    if ({key for key,_ in positive} != known or {key for key,_ in negative} != known
            or actual != positive or actual & negative or len(actual) != len(data['results'])):
        raise ValueError('Rule test failed or positive/negative cases are missing')
    return len(known)


def core_scan(executable, group, targets, directory, env):
    """semgrep-core accepts `-lang` with one target only; validate every file run."""
    if not targets:
        raise ValueError('Semgrep rule group has no targets')
    stdout = directory/'stdout.json'
    combined = {'results':[], 'paths':{'scanned':[]}, 'rules_by_engine':[], 'eos_core_exit_codes':[]}
    for target in sorted(targets):
        command = [executable, '-json_nodots', '-strict', '-j', '1', '-timeout', '10', '-timeout_threshold', '1',
                   '-rules', group['path'], '-lang', group['language'], target]
        with stdout.open('w',encoding='utf-8') as output, (directory/'stderr.log').open('w',encoding='utf-8') as errors:
            completed = subprocess.run(command,cwd=ROOT,env=env,stdout=output,stderr=errors,check=False,timeout=120)
        data = json.loads(stdout.read_text(encoding='utf-8'))
        data['eos_core_exit_codes'] = [completed.returncode]
        data['eos_scan_exit_code'] = int(bool(data.get('results')))
        semgrep(data,expected={target},expected_rules=group['rules'])
        combined['results'] += data['results']
        combined['paths']['scanned'] += data['paths']['scanned']
        combined['rules_by_engine'] += data['rules_by_engine']
        combined['eos_core_exit_codes'] += data['eos_core_exit_codes']
    return combined


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable')
    parser.add_argument('--test', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    if not args.test and args.output is None:
        parser.error('--output is required for a scan')
    if args.output:
        args.output.unlink(missing_ok=True)
    env = {**os.environ, 'SEMGREP_SEND_METRICS':'off', 'SEMGREP_ENABLE_VERSION_CHECK':'0'}
    env.pop('SEMGREP_APP_TOKEN', None)
    try:
        from_version = semgrep_version()
        executable = args.executable or str(ROOT/'.semgrep-native'/from_version/('semgrep-core.exe' if os.name == 'nt' else 'semgrep-core'))
        with TemporaryDirectory(prefix='eos-semgrep-') as directory:
            results, paths, rules, exits = [], [], [], []
            count = 0
            for group in rule_groups():
                fixture = ROOT/Path(group['path']).with_suffix(group['suffix'])
                targets = ({fixture.relative_to(ROOT).as_posix()} if args.test else
                           {value for value in semgrep_targets() if value.endswith(group['suffix'])})
                data = core_scan(executable,group,targets,Path(directory),env)
                if args.test:
                    count += checked_rule_tests(data,fixture,group['rules'])
                results += data['results']
                paths += data['paths']['scanned']
                rules += data['rules_by_engine']
                exits += data['eos_core_exit_codes']
            if args.test:
                print(f'Semgrep: all {count} rule tests passed')
                return 0
            data = {'version':from_version, 'results':results, 'errors':[], 'skipped_rules':[],
                    'paths':{'scanned':paths}, 'rules_by_engine':rules, 'eos_core_exit_codes':exits,
                    'eos_scan_exit_code':int(bool(results))}
            # Raw reports stay in RUNNER_TEMP; only the redacted converter output is uploaded.
            args.output.write_text(json.dumps(data), encoding='utf-8')
            semgrep(data)
            print(f"Semgrep: {len(data['paths']['scanned'])} source files, {len(semgrep_catalog())} rules, {len(data['results'])} findings")
            return data['eos_scan_exit_code']
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired, yaml.YAMLError):
        print('Semgrep: missing, incomplete or invalid scan/rule tests; no raw diagnostics published')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
