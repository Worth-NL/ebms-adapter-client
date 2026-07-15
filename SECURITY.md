# Security Policy

## Supported Versions

Only the latest published release on PyPI receives security fixes.

## Reporting a Vulnerability

This library transports HTTP Basic Auth credentials (`EbmsAdapterClientConfig.username`/`password`)
and, via the `berichtenbox` sub-package, Dutch citizen BSN data as part of message payloads. If you
find a security issue — including but not limited to credential handling, TLS verification bypass,
or XML parsing vulnerabilities — please report it privately rather than opening a public issue:

1. Open a [GitHub Security Advisory](https://github.com/Worth-NL/ebms-adapter-client/security/advisories/new)
   for this repository, or
2. Email the maintainers at Worth Systems.

Please do not report security issues through public GitHub issues.

We aim to acknowledge reports within 5 business days.
