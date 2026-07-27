# Security Policy

## Supported Versions

We take security seriously. This section outlines our security policy and how to report security vulnerabilities.

## Reporting a Vulnerability

If you discover a security vulnerability in Astrocyte, please help us by reporting it responsibly.

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report security vulnerabilities by emailing:
- **astrocyte@mkzsys.com**

You should receive a response within 48 hours. If you don't, please follow up to ensure we received your report.

## Responsible Disclosure

We kindly ask that you:

- Give us reasonable time to fix the issue before making it public
- Avoid accessing or modifying user data
- Avoid disrupting our services
- Provide sufficient detail to reproduce the issue

## What We Promise

- We will acknowledge receipt of your report within 48 hours
- We will provide regular updates on our progress
- We will credit you (if desired) once the issue is resolved
- We will not pursue legal action against security researchers who follow this policy

## Automated Dependency Scanning

Dependencies and container images are scanned continuously:

- **Dependabot** opens weekly PRs for outdated Python (uv), npm, Docker, and
  GitHub Actions dependencies.
- **CI security scan** (on every PR) runs `pip-audit` (Python), `npm audit`
  (web), and a Trivy scan of the built container image; the build fails on
  fixable `HIGH`/`CRITICAL` advisories.

Reported vulnerabilities are triaged by severity: fixable HIGH/CRITICAL issues
block merges and are resolved by upgrading the affected dependency (usually via
the open Dependabot PR); lower-severity or unfixable advisories are tracked and
revisited as fixes become available.

## Scope

This security policy applies to the core Astrocyte codebase and officially supported components. Third-party applications deployed through Astrocyte are the responsibility of their respective maintainers.

## Security Updates

Security updates will be released as soon as possible after a fix is developed and tested. We will announce security updates through:

- GitHub Security Advisories
- Release notes
- Our website and documentation

## PGP Key (Optional)

For encrypted communications, you can use our PGP key:

```
-----BEGIN PGP PUBLIC KEY BLOCK-----

[PGP Key would be included here if available]

-----END PGP PUBLIC KEY BLOCK-----
```

## Contact

For security-related questions or concerns, please contact us at astrocyte@mkzsys.com.
