# Contributing to Memlog

Contributions are welcome — bug fixes, improvements, and new features.

## Getting started

```bash
just install   # install all deps and set up git hooks
just backend   # backend dev server on :8000
just frontend  # frontend dev server on :8080
just test      # run backend tests
just fmt       # auto-fix formatting
```

Pre-commit hooks run automatically on every commit (ruff, prettier, bandit).

## Submitting a PR

- Keep changes focused — one thing per PR
- For significant changes, open an issue first to align on direction
- Make sure `just test` and `just fmt` pass before pushing

## Reporting bugs

Open a GitHub issue with steps to reproduce and what you expected to happen.
