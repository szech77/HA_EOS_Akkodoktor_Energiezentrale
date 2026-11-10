"""External scanner contracts: preserve actionable locations, redact secret values."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from tools.security_sarif import bandit, main, pip_audit, trivy
from test_energy import temporary_project_directory


class SecurityReportingRequirements(TestCase):
    def test_bandit_keeps_rule_severity_and_location_without_copying_passwords(self):
        raw = {"test_id": "B105", "test_name": "hardcoded_password_string", "issue_severity": "MEDIUM",
               "filename": "tools/example.py", "line_number": 7,
               "issue_text": "secret-value", "code": "password = secret-value"}
        output = bandit({"results": [raw], "errors": []})
        finding = output["runs"][0]["results"][0]
        self.assertEqual(finding["ruleId"], "B105")
        self.assertEqual(finding["level"], "warning")
        self.assertEqual(finding["locations"][0]["physicalLocation"]["region"]["startLine"], 7)
        self.assertNotIn("secret-value", json.dumps(output))

    def test_trivy_does_not_publish_matched_tokens_or_surrounding_source(self):
        raw = {"SchemaVersion": 2, "Results": [{"Target": "example/settings.yaml", "Secrets": [{
            "RuleID": "github-token", "Severity": "HIGH", "StartLine": 3, "EndLine": 4,
            "Match": "sensitive-match", "Title": "sensitive-title", "Code": {"Lines": "sensitive-code"}}]}]}
        output = trivy(raw)
        finding = output["runs"][0]["results"][0]
        self.assertEqual(finding["level"], "error")
        self.assertEqual(finding["locations"][0]["physicalLocation"]["artifactLocation"]["uri"], "example/settings.yaml")
        self.assertNotIn("sensitive-", json.dumps(output))

    def test_direct_requirements_and_transitive_dependencies_remain_actionable(self):
        with temporary_project_directory() as root:
            requirements = root / "requirements.txt"
            requirements.write_text("# dependency\nExample_Pkg[sarif]==1.0\n", encoding="utf-8")
            vulnerabilities = [{"id": "GHSA-example", "fix_versions": ["2.0"]}]
            data = {"dependencies": [{"name": "example-pkg", "version": "1.0", "vulns": vulnerabilities},
                                      {"name": "indirect", "version": "0.1", "vulns": vulnerabilities}]}
            results = pip_audit(data, [str(requirements)])["runs"][0]["results"]
        self.assertEqual(results[0]["locations"][0]["physicalLocation"]["region"]["startLine"], 2)
        self.assertIn("fixed versions: 2.0", results[0]["message"]["text"])
        self.assertIn("transitive", results[1]["message"]["text"])
        self.assertEqual(results[1]["locations"][0]["physicalLocation"]["region"]["startLine"], 1)

    def test_clean_reports_publish_empty_results_to_close_fixed_findings(self):
        for output in (bandit({"results": [], "errors": []}), pip_audit({"dependencies": []}, []),
                       trivy({"SchemaVersion": 2})):
            self.assertEqual(output["version"], "2.1.0")
            self.assertEqual(output["runs"][0]["results"], [])
            self.assertTrue(output["runs"][0]["automationDetails"]["id"].endswith("/"))

    def test_incomplete_scans_do_not_become_clean_reports(self):
        for convert, data in ((bandit, {"results": [], "errors": ["cannot parse"]}),
                              (trivy, {}), (bandit, {})):
            with self.subTest(data=data), self.assertRaises(ValueError):
                convert(data)
        with self.assertRaises(ValueError):
            pip_audit({"dependencies": [{"name": "not-audited", "skip_reason": "offline"}]}, [])

    def test_invalid_locations_are_rejected_instead_of_uploading_outside_checkout(self):
        for filename, line in (("../private.txt", 1), ("file.py", 0)):
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                trivy({"SchemaVersion": 2, "Results": [{"Target": filename, "Secrets": [{
                    "RuleID": "token", "Severity": "HIGH", "StartLine": line}]}]})

    def test_one_broken_tool_does_not_hide_other_tools_and_raw_secrets_are_not_logged(self):
        with temporary_project_directory() as root:
            good = root / "bandit.json"
            bad = root / "broken.json"
            good.write_text(json.dumps({"results": [], "errors": []}), encoding="utf-8")
            bad.write_text("sensitive-raw-content", encoding="utf-8")
            output = root / "sarif"
            output.mkdir()
            (output / "trivy-secrets.sarif").write_text("stale analysis", encoding="utf-8")
            console = StringIO()
            with patch("sys.argv", ["security_sarif", "--bandit", str(good), "--pip-audit", str(bad),
                                    "--trivy", str(bad), "--output-dir", str(output)]), redirect_stdout(console):
                code = main()
            self.assertEqual(code, 1)
            self.assertTrue((output / "bandit.sarif").is_file())
            self.assertFalse((output / "trivy-secrets.sarif").exists())
            self.assertNotIn("sensitive-raw-content", console.getvalue())

    def test_locations_are_valid_repository_relative_uris_and_duplicate_rules_keep_all_findings(self):
        output = trivy({"SchemaVersion": 2, "Results": [{"Target": "config dir/file.yaml", "Secrets": [
            {"RuleID": "token", "Severity": "HIGH", "StartLine": line} for line in (2, 7)]}]})
        run = output["runs"][0]
        self.assertEqual(len(run["tool"]["driver"]["rules"]), 1)
        self.assertEqual(len(run["results"]), 2)
        self.assertEqual(run["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"],
                         "config%20dir/file.yaml")

    def test_dependency_versions_with_epoch_and_local_build_tags_are_preserved(self):
        with temporary_project_directory() as root:
            requirements = root / "requirements.txt"
            requirements.write_text("example==1!2.0+local\n", encoding="utf-8")
            output = pip_audit({"dependencies": [{"name": "example", "version": "1!2.0+local",
                "vulns": [{"id": "CVE-2026-1234", "fix_versions": []}]}]}, [str(requirements)])
        finding = output["runs"][0]["results"][0]
        self.assertIn("1!2.0+local", finding["message"]["text"])
        self.assertNotIn("security-severity", output["runs"][0]["tool"]["driver"]["rules"][0]["properties"])
