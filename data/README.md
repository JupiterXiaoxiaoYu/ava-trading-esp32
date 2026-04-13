# Data Directory

This directory is the repo-level placeholder for local runtime data that should not be treated as source code.

Right now it is intentionally minimal. Keep it for local state, experiments, or runtime material that should exist near the repo but should not be mixed with implementation files.

## Intended use

- Local runtime data that is safe to regenerate
- Scratch datasets or exports used during debugging
- Non-code artifacts that support local development

## Avoid putting here

- Production secrets
- Source files that belong in `server/`, `firmware/`, `shared/`, or `docs/`
- Large generated build outputs
- Anything that should become part of the committed product contract

## Related directories

- [`../tmp/README.md`](../tmp/README.md) - short-lived logs and scratch artifacts
- [`../docs/README.md`](../docs/README.md) - committed notes and investigations
- [`../server/README_en.md`](../server/README_en.md) - backend runtime surfaces
