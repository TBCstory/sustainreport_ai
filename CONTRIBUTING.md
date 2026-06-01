# Contributing to sustainreport-ai

Thanks for considering a contribution.

`sustainreport-ai` is an alpha-stage orchestrator for generating evidence-grounded ESG sustainability report drafts. The goal is not to auto-publish a final report. The system is designed to help consultants and reviewers build a traceable draft that can be checked, revised, and handed off safely.

한국어 문서는 유지되어야 합니다. English documentation improvements are welcome, but please do not remove useful Korean explanations already in the repository.

## What kinds of contributions are welcome?

We especially welcome contributions in these areas:

- Bug reports and reproducible defect fixes
- Documentation improvements and contributor onboarding
- Test additions and CI reliability improvements
- ESG framework mapping improvements (for example GRI, TCFD, KSSB, ESRS)
- CLI usability improvements and clearer status output
- Issue triage, labeling, and reproduction notes

If you are unsure whether something fits the project, open an issue first.

## Project boundaries

Please keep changes aligned with the current project scope:

- Keep the project focused on ESG sustainability report draft generation
- Do not rewrite the architecture just to make it "cleaner"
- Do not introduce fictional features, fictional ESG facts, or made-up outputs
- Do not change derived workflow state files by hand when a script or CLI command already exists
- If you are unsure, leave a `TODO` note or open a discussion instead of guessing

## Development setup

This repository uses `uv` for environment and dependency management.

```bash
uv sync --extra dev
uv run sustainreport --help
```

If you need optional OCR-related dependencies, install them separately and keep those changes out of unrelated pull requests.

## Basic checks

Run the basic local checks before opening a pull request:

```bash
uv run ruff check .
uv run pytest
```

If you changed CLI behavior, also run a quick manual smoke check:

```bash
uv run sustainreport --help
```

## Coding and documentation style

- Prefer small, reviewable pull requests
- Preserve existing Korean documentation; add English clarifications where helpful
- Keep comments concise and factual
- Avoid broad refactors unless they are necessary to fix the targeted issue
- Add or update tests when behavior changes
- Keep examples and fixtures synthetic, scrubbed, or clearly non-confidential

## Data handling and confidentiality

Do not commit:

- API keys, tokens, or secrets
- `.env` files with real values
- Customer ESG reports or internal sustainability documents
- Private project workspaces under `workspaces/`
- Any generated artifact that may contain sensitive client information

Use `.env.example` only for placeholders and documentation-safe sample variable names.

## Pull request expectations

Please make it easy to review your change.

- Explain what changed and why
- Link the related issue when available
- Include tests or smoke-check notes when relevant
- Update README or supporting docs if user-visible behavior changed
- Keep unrelated cleanup out of the same pull request

For sensitive issues, do not open a public issue with details. Follow [SECURITY.md](SECURITY.md) instead.
