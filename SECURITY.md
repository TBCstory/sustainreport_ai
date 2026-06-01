# Security Policy

## Scope and current status

`sustainreport-ai` is currently alpha-stage software. Security handling is best-effort, but we still want responsible disclosure and careful data handling.

## Do not commit sensitive material

Please do not commit any of the following to this repository:

- API keys, access tokens, or credentials
- `.env`, `.env.local`, or other environment files with real secrets
- Customer ESG documents
- Internal reports or consulting deliverables
- Private project workspaces or generated draft packages

Use `.env.example` only for placeholders and documentation-safe variable names.

## Generated workspaces may be confidential

Generated workspace directories under `workspaces/` may contain confidential source material, draft text, or client-specific metadata. They are intentionally ignored by Git and should stay out of commits, pull requests, and issue attachments unless the contents are fully synthetic and scrubbed.

## How to report a security issue

If GitHub Security Advisories are available for this repository, please use a private security advisory report.

If private reporting is not available, open a minimal public issue without sensitive details. Share only enough information to let maintainers acknowledge the problem and move the discussion to a safer channel if needed.

Please do not include:

- Secret values
- Full exploit instructions with live credentials
- Customer documents
- Private workspace archives

## Examples of reportable issues

- Secret leakage in the repository or CI
- Unsafe handling of `.env` files or generated workspaces
- Dependency vulnerabilities with practical impact
- Unexpected exposure of client data through logs, fixtures, or examples

## If you accidentally commit sensitive data

Act quickly:

1. Revoke or rotate the secret if applicable.
2. Remove the sensitive material from the branch and future commits.
3. Notify maintainers through the private disclosure route when possible.

Do not paste the sensitive content into an issue while reporting it.
