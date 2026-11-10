"""Convert scanner JSON to location-aware SARIF without source/secret snippets."""
import argparse
import json
from pathlib import Path
import re
from urllib.parse import quote

SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
SEVERITY = {"CRITICAL": "error", "HIGH": "error", "MEDIUM": "warning", "LOW": "note"}


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


def report(tool, category, findings):
    rules = {}
    results = []
    for rule, message, level, places in findings:
        rules.setdefault(rule, {"id": rule, "shortDescription": {"text": rule},
                                "properties": {"tags": ["security"]}})
        results.append({"ruleId": rule, "level": level, "message": {"text": message},
                        "locations": places})
    return {"$schema": SCHEMA, "version": "2.1.0", "runs": [{
        "tool": {"driver": {"name": tool, "rules": list(rules.values())}},
        "automationDetails": {"id": "source-security/" + category + "/"}, "results": results}]}


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
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    failed = False
    for name, source, convert in (("bandit", args.bandit, bandit),
                                  ("pip-audit", args.pip_audit,
                                   lambda data: pip_audit(data, ["requirements-dev.txt", "requirements-test.txt"])),
                                  ("trivy-secrets", args.trivy, trivy)):
        try:
            destination = args.output_dir / (name + ".sarif")
            destination.unlink(missing_ok=True)
            converted = convert(json.loads(source.read_text(encoding="utf-8")))
            destination.write_text(json.dumps(converted), encoding="utf-8")
            print(name + ": SARIF report ready")
        except (OSError, ValueError, KeyError, TypeError):
            # Never print parser errors or raw source; a secret may be contained there.
            print(name + ": missing, incomplete or invalid scanner report")
            failed = True
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
