# Security Policy

## Supported Versions

Security updates are provided for the latest published release.

Older releases do not receive guaranteed security fixes.

| Version | Supported |
|---|---|
| Latest release | ✅ |
| Older releases | ❌ |

## Reporting a Vulnerability

Please do **not** report security vulnerabilities through public GitHub issues.

Report vulnerabilities privately using:

**GitHub → Security → Private vulnerability reporting**

Alternatively, create a private GitHub Security Advisory:

https://github.com/szech77/HA_EOS_Akkodoktor_Energiezentrale/security/advisories/new

Please include, when available:

- A clear description of the vulnerability and its impact
- The affected integration version or commit
- Steps to reproduce or a minimal proof of concept
- Affected configuration, devices, or components
- Any known workarounds
- Your preferred contact information for follow-up

Do not include passwords, access tokens, private sensor values, or other
sensitive information from your Home Assistant installation.

## Response Targets

We aim to:

- Acknowledge reports within 7 days
- Assess the impact within 14 days
- Coordinate testing and publication timelines with the reporter

These timelines may vary depending on severity, complexity, and maintainer
availability.

## Disclosure Process

After receiving a report, we will assess the impact and, where appropriate,
create a private GitHub Security Advisory. We will coordinate on a remediation
plan before publishing an update and disclosing the issue.

Please keep vulnerability details private until disclosure is coordinated.

## Security Considerations

This integration can control energy storage, charging equipment, and other
connected devices. Please consider the following:

- Do not execute device commands outside controlled test environments
- Do not publish real credentials or private device configurations
- Protect EOS and other local services with appropriate network segmentation
  and firewall rules
- Test configuration changes in read mode before enabling energy control
- Grant only the permissions and control capabilities that are actually needed

## Automated Security Checks

The repository uses:

- Bandit for Python static analysis
- pip-audit for Python dependency vulnerabilities
- Trivy for secret detection
- Dependabot for dependency updates
- GitHub Code Scanning for published findings
