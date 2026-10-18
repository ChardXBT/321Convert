# Security

## Reporting a vulnerability

Please report security issues privately through
[GitHub's private vulnerability reporting](https://github.com/ChardXBT/321Convert/security/advisories/new)
rather than in a public issue. Include the steps to reproduce and, if possible, a sample file.
You should hear back within a week.

## Scope

321Convert processes untrusted files. The controls that matter most:

- Every conversion runs in a child process with a hard timeout; the web worker never parses
  uploads itself.
- Uploads are validated by extension and content, bounded in size, and Office archives are
  checked for ZIP bombs and path traversal before parsing.
- Image decoding is limited to an allow-list of formats and a pixel ceiling.
- HTML/Markdown input is sanitised with an allow-list before rendering, and the PDF renderer is
  restricted to a read-only font directory with no network access.
- Responses use a strict Content-Security-Policy and same-origin checks on POST requests.

Reports about those controls, about information leaking through error messages or logs, or
about denial of service that gets past the limits are especially welcome.

## Supported versions

Only the `master` branch and the deployed instance are supported. Dependencies are kept
current through Dependabot and `pip-audit` runs in CI.
