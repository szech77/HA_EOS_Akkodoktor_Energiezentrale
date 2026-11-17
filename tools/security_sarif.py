"""Convert scanner JSON to location-aware SARIF without source/secret snippets."""
import argparse
import json
from pathlib import Path
import re
from urllib.parse import quote

import yaml

SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
SEVERITY = {"CRITICAL": "error", "HIGH": "error", "MEDIUM": "warning", "LOW": "note"}
ROOT = Path(__file__).resolve().parents[1]


def location(filename, line=1):
    path = Path(filename)
    if path.is_absolute():
        path = path.resolve().relative_to(Path.cwd().resolve())
    if ".." in path.parts or not path.parts or "\\" in path.as_posix():
        raise ValueError("Scanner location must stay within the checkout")
    if type(line) is not int or line < 1:
        raise ValueError("Scanner line must be a positive integer")
    return {"physicalLocation": {"artifactLocation": {"uri": quote(path.as_posix(), safe="/")},
                                 "region": {"startLine": line}}}


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:/+!-]{1,200}", value):
        raise ValueError("Invalid scanner rule identifier")
    return value


def report(tool, category, findings, *, rule_details=None, version=None):
    rules = dict(rule_details or {})
    results = []
    for rule, message, level, places in findings:
        rules.setdefault(rule, {"id": rule, "shortDescription": {"text": rule},
                                "properties": {"tags": ["security"]}})
        results.append({"ruleId": rule, "level": level, "message": {"text": message},
                        "locations": places})
    return {"$schema": SCHEMA, "version": "2.1.0", "runs": [{
        "tool": {"driver": {"name": tool, "rules": list(rules.values()), **({'version':version} if version else {})}},
        "automationDetails": {"id": "source-security/" + category + "/"}, "results": results}]}


def semgrep_catalog():
    """Only repository-owned rule descriptions may reach uploaded reports."""
    result = {}
    for path in sorted(path for path in (ROOT/'.semgrep/rules').iterdir() if path.suffix in ('.yml','.yaml')):
        for rule in yaml.safe_load(path.read_text(encoding='utf-8'))['rules']:
            key = identifier(rule['id'])
            meta = rule['metadata']
            score = str(meta['security-severity'])
            cwes = meta['cwe']
            if (key in result or rule['severity'] not in ('ERROR','WARNING','INFO')
                    or not re.fullmatch(r'(?:[0-9](?:\.[0-9]+)?|10(?:\.0+)?)', score)
                    or not cwes or any(not re.fullmatch(r'CWE-[0-9]+', item) for item in cwes)
                    or meta['confidence'] not in ('HIGH','MEDIUM','LOW')
                    or not rule['message'] or not meta['help']
                    or not all(isinstance(value,str) for value in (rule['message'],meta['help']))
                    or not meta['references'] or not meta['references'][0].startswith('https://')):
                raise ValueError('Invalid Semgrep rule catalog')
            result[key] = {'id':key, 'shortDescription':{'text':rule['message']},
                'fullDescription':{'text':meta['help']}, 'helpUri':meta['references'][0],
                'help':{'text':meta['help'], 'markdown':meta['help']+'\n\n[Reference]('+meta['references'][0]+')'},
                'defaultConfiguration':{'level':{'ERROR':'error','WARNING':'warning','INFO':'note'}[rule['severity']]},
                'properties':{'tags':['security']+['external/cwe/'+item.lower() for item in cwes],
                    'security-severity':score, 'precision':{'HIGH':'high','MEDIUM':'medium','LOW':'low'}[meta['confidence']]}}
    if not result:
        raise ValueError('Semgrep has no configured rules')
    return result


def semgrep_targets():
    return {path.relative_to(ROOT).as_posix() for directory in ('custom_components','tools')
            for path in (ROOT/directory).rglob('*') if path.suffix in ('.py','.js') and path.is_file()}


def semgrep_version():
    version = json.loads((ROOT/'.semgrep/tool.json').read_text(encoding='utf-8'))['version']
    if not isinstance(version,str) or not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',version):
        raise ValueError('Semgrep must have an exact version pin')
    return version


def semgrep_path(value):
    # Semgrep's native Windows engine uses backslashes in otherwise relative paths.
    if not isinstance(value, str):
        raise ValueError('Invalid Semgrep path')
    normalized = value.replace('\\','/')
    place = location(normalized)
    return place['physicalLocation']['artifactLocation']['uri']


def semgrep(data, *, expected=None, expected_rules=None):
    """Reject partial/empty scans; never copy matched text or expanded metadata."""
    version = semgrep_version()
    expected = semgrep_targets() if expected is None else expected
    if (not isinstance(data, dict) or data.get('version') != version
            or not isinstance(data.get('results'), list) or data.get('errors') != []
            or data.get('skipped_rules') != [] or not isinstance(data.get('paths'),dict)
            or not isinstance(data['paths'].get('scanned'),list)
            or data.get('eos_scan_exit_code') not in (0,1)
            or type(data.get('eos_scan_exit_code')) is not int
            or data['eos_scan_exit_code'] != int(bool(data['results']))
            or not isinstance(data.get('time',{}),dict)
            or data.get('time',{}).get('fixpoint_timeouts')):
        raise ValueError('Missing or incomplete Semgrep scan')
    scanned = {semgrep_path(path) for path in data['paths']['scanned']}
    if not expected or scanned != {semgrep_path(path) for path in expected}:
        raise ValueError('Semgrep did not scan every intended source file')
    catalog = semgrep_catalog()
    expected_rules = set(catalog) if expected_rules is None else expected_rules
    if (not isinstance(data.get('rules_by_engine'),list)
            or any(not isinstance(item,list) or len(item) != 2 for item in data['rules_by_engine'])
            or {item[0] for item in data['rules_by_engine']} != expected_rules
            or any(item[1] != 'OSS' for item in data['rules_by_engine'])
            or not isinstance(data.get('eos_core_exit_codes'),list) or not data['eos_core_exit_codes']
            or any(type(code) is not int or code != 0 for code in data['eos_core_exit_codes'])):
        raise ValueError('Semgrep did not successfully run all configured CE rules')
    findings = []
    for item in data['results']:
        if (not isinstance(item,dict) or not isinstance(item.get('path'),str)
                or not isinstance(item.get('extra',{}),dict) or not isinstance(item.get('start'),dict)):
            raise ValueError('Malformed Semgrep finding')
        key = identifier(item['check_id'])
        if key not in catalog or key not in expected_rules:
            raise ValueError('Unknown Semgrep rule')
        rule = catalog[key]
        path = item['path'].replace('\\','/')
        # semgrep-core marks `nosemgrep` comments as ignored; suppressions are not
        # accepted, so such findings stay ordinary, blocking results.
        if semgrep_path(path) not in scanned:
            raise ValueError('Invalid Semgrep result location')
        findings.append((key, rule['shortDescription']['text'], rule['defaultConfiguration']['level'],
                         [location(path,item['start']['line'])]))
    return report('Semgrep','semgrep',findings,rule_details=catalog,version=version)


def bandit(data):
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ValueError("Invalid Bandit report")
    if data.get("errors"):
        raise ValueError("Bandit did not scan all input files")
    findings = []
    for item in data["results"]:
        rule = identifier(item["test_id"])
        name = identifier(item["test_name"])
        # issue_text and code may contain hardcoded passwords. Do not publish them.
        findings.append((rule, f"Bandit {rule}: {name}. Review the indicated source location.",
                         SEVERITY.get(item["issue_severity"], "warning"),
                         [location(item["filename"], item["line_number"])]))
    return report("Bandit", "bandit", findings)


def requirement_locations(paths):
    result = {}
    for path in paths:
        for line, text in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
            match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9_.-]*)(?:\[[^]]+\])?\s*(?:[<>=!~;]|$)", text)
            if match:
                name = re.sub(r"[-_.]+", "-", match[1]).lower()
                result.setdefault(name, []).append(location(path, line))
    return result


def pip_audit(data, requirements):
    if not isinstance(data, dict) or not isinstance(data.get("dependencies"), list):
        raise ValueError("Invalid pip-audit report")
    direct = requirement_locations(requirements)
    findings = []
    for dependency in data["dependencies"]:
        if dependency.get("skip_reason"):
            raise ValueError("A dependency could not be audited")
        package = identifier(dependency["name"])
        name = re.sub(r"[-_.]+", "-", package).lower()
        places = direct.get(name) or [location(requirements[-1])]
        for vulnerability in dependency["vulns"]:
            rule = identifier(vulnerability["id"])
            fixes = ", ".join(identifier(version) for version in vulnerability.get("fix_versions", [])) or "not available"
            version = identifier(dependency["version"])
            origin = "Direct requirement" if name in direct else "Resolved transitive dependency of the audited requirements"
            message = f"{origin}: {package} {version}; advisory {rule}; fixed versions: {fixes}."
            # pip-audit does not provide CVSS severity: do not invent a security score.
            findings.append((rule, message, "warning", places))
    return report("pip-audit", "pip-audit", findings)


def trivy(data):
    if not isinstance(data, dict) or data.get("SchemaVersion") != 2:
        raise ValueError("Invalid Trivy report")
    results = data.get("Results", [])
    if not isinstance(results, list):
        raise ValueError("Invalid Trivy results")
    findings = []
    for item in results:
        for secret in item.get("Secrets", []):
            rule = identifier(secret["RuleID"])
            # Do not include Match, Title, Code, surrounding lines or the raw report.
            findings.append((rule, f"Potential secret detected by Trivy rule {rule}. Secret content omitted; review and rotate if confirmed.",
                             SEVERITY.get(secret["Severity"], "warning"),
                             [location(item["Target"], secret["StartLine"])]))
    return report("Trivy Secrets", "trivy-secrets", findings)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bandit", type=Path, required=True)
    parser.add_argument("--pip-audit", type=Path, required=True)
    parser.add_argument("--trivy", type=Path, required=True)
    parser.add_argument("--semgrep", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    failed = False
    for name, source, convert in (("bandit", args.bandit, bandit),
                                  ("pip-audit", args.pip_audit,
                                   lambda data: pip_audit(data, ["requirements-dev.txt", "requirements-test.txt"])),
                                  ("trivy-secrets", args.trivy, trivy),
                                  ("semgrep", args.semgrep, semgrep)):
        try:
            destination = args.output_dir / (name + ".sarif")
            destination.unlink(missing_ok=True)
            converted = convert(json.loads(source.read_text(encoding="utf-8")))
            destination.write_text(json.dumps(converted), encoding="utf-8")
            print(name + ": SARIF report ready")
        except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError):
            # Never print parser errors or raw source; a secret may be contained there.
            print(name + ": missing, incomplete or invalid scanner report")
            failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
