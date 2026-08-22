# Contributing

1. Create a focused branch from `main`.
2. Keep the critical ingestion path dependency-light and deterministic.
3. Add or update offline fixtures and tests for behavior changes.
4. Run `PYTHONPATH=src python -m unittest discover -s tests -v` and `python -m compileall -q src tests`.
5. Open a pull request that separates implemented evidence from planned work.

Never commit credentials, real personal data, generated databases, or downloaded raw documents.
