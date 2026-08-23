# Security Policy

Terento is an active beta project. This policy covers the repository, the native macOS application, the catalog service, and the public web surfaces.

## Supported versions

| Version or branch | Support |
| --- | --- |
| Latest beta release | Security reports accepted; fixes are best effort |
| Current default branch (experimental at the time of writing) | Security reports accepted; fixes are best effort |
| Older beta releases | Not guaranteed |

Terento is not a stable production release. Device and map behaviour may change between beta releases.

## Reporting a vulnerability

Please do not open a public issue for a suspected vulnerability. Do not include secrets, personal data, device serial numbers, complete map files, or private logs in a report.

Use GitHub's private vulnerability reporting or Security Advisories for this repository when the reporting form is available:

https://github.com/VooZ2/terento/security/advisories/new

If private reporting is not available, contact the repository owner privately through GitHub and include the words 'Terento security report' in the subject.

Include:

- the affected version, commit, or component;
- a concise description of the security impact;
- reproducible steps or a minimal proof of concept;
- the affected operating system, device model, and configuration, when relevant; and
- any suggested mitigation.

Please give maintainers a reasonable opportunity to investigate before public disclosure. Do not test against devices, accounts, or data that you do not own or have explicit permission to use.

## Response process

Maintainers will try to:

1. acknowledge a report within seven calendar days;
2. confirm the affected component and severity;
3. prepare a fix or mitigation when practical;
4. coordinate disclosure and credit with the reporter, if requested; and
5. document affected versions and the available upgrade or workaround.

These are project goals, not a guaranteed service level.

## Scope notes

- Report vulnerabilities in Terento code, build configuration, release automation, or the catalog service here.
- Report vulnerabilities in Garmin devices or firmware to Garmin through its own security process.
- Report vulnerabilities in libmtp, libusb, Swift, macOS, map providers, or other third-party dependencies to their upstream maintainers as well; mention the dependency and version in the Terento report.
- Do not upload proprietary map data or credentials as part of a report.

## Safe testing

Only test with devices and accounts you own or are explicitly authorised to use. Avoid destructive transfers, deletion of unrelated files, denial-of-service activity, privacy-invasive testing, and automated traffic against services that are not part of the local test environment.
