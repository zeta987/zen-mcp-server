# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- `CONTEXT.md` at the repo root.
- `docs/adr/` for architectural decisions that touch the area being changed.
- If `CONTEXT.md` or `docs/adr/` do not exist yet, proceed silently and use the existing project docs for orientation.

## File structure

This is a single-context repo:

```text
/
├── CONTEXT.md
├── docs/adr/
│   ├── 0001-example-decision.md
│   └── 0002-example-decision.md
└── docs/
```

## Use the project's vocabulary

When output names a domain concept in an issue title, refactor proposal, hypothesis, or test name, prefer the term as defined in `CONTEXT.md` when that file exists.

If the concept is not documented yet, treat that as missing context rather than inventing a durable project term.

## Flag ADR conflicts

If output contradicts an existing ADR, surface the conflict explicitly instead of silently overriding the recorded decision.
