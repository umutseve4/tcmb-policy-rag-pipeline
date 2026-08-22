# TCMB Policy RAG Pipeline

A small, reproducible **ingestion-to-retrieval vertical slice** for Türkiye Cumhuriyet Merkez Bankası (TCMB) Monetary Policy Committee decisions.

> **Status:** v0.1 implements and tests immutable raw versioning, checksum-based idempotency, validation/quarantine, SQLite FTS5 retrieval, and citation-backed extractive answers. PostgreSQL/pgvector, dbt, scheduled discovery, generation, and the 30-question offline evaluation set are planned—not claimed as complete.

## Why this exists

A credible RAG system starts with reliable data engineering. This repository makes the hard parts visible: source provenance, version preservation, repeatable ingestion, deterministic validation, duplicate prevention, evidence retrieval, and explicit abstention when evidence is insufficient.

## Implemented v0.1

- SHA-256 content identity and immutable raw HTML paths
- idempotent re-ingestion: unchanged input adds `0` documents and `0` chunks
- changed content creates a new version while retaining the previous version
- deterministic metadata and minimum-length validation
- deduplicated quarantine records for malformed sources
- SQLite schema with foreign keys, uniqueness constraints, transactions, and FTS5/BM25 retrieval
- extractive answer contract with source URL, title, and publication date
- `insufficient_evidence` response when retrieval finds no support
- 8 offline unit/integration tests using deterministic fixtures
- dependency-light CLI and CI on Python 3.11, 3.12, and 3.13

## Architecture

```text
TCMB URL -> fetch -> immutable raw HTML -> parse/validate
                                      |-> quarantine
                                      `-> versioned documents -> chunks -> SQLite FTS5
                                                                  `-> cited answer / abstain
```

The raw layer is content-addressed by SHA-256. A database transaction writes the document and all chunks atomically, meaning either the version is complete or none of it is committed.

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e .
python -m unittest discover -s tests -v

tcmb-policy ingest "https://www.tcmb.gov.tr/..." --raw-dir data/raw
tcmb-policy ask "Politika faizi hakkında ne karar verildi?"
```

Live TCMB pages can change structure. The parser intentionally quarantines documents that do not meet its explicit contract instead of silently writing bad data.

## Data model

| Table | Purpose | Important guarantees |
|---|---|---|
| `documents` | one row per source version | unique SHA-256 checksum; URL + checksum uniqueness |
| `chunks` | retrievable evidence | document FK; deterministic ordinal and hash |
| `chunks_fts` | lexical retrieval index | Unicode tokenization; BM25 ranking |
| `quarantine` | rejected source versions | reason + checksum; repeat failures deduplicated |

## Verification

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src tests
```

CI runs those gates on Python 3.11, 3.12, and 3.13. No production claim is made until live-source, scale, security, recovery, and deployment evidence exists.

## Roadmap and measurable gates

### M1 — multi-document ingestion
- discover and ingest the latest 24 months of PPK decisions
- second full run: `0` new documents and `0` duplicate chunks
- `100%` of intentionally malformed fixtures quarantined

### M2 — production-shaped retrieval
- PostgreSQL + pgvector and dbt staging/core models
- Turkish full-text + vector hybrid retrieval
- at least 30 manually verified Turkish questions
- `Recall@5 >= 0.80`; citation precision `>= 0.90`

### M3 — grounded API and operations
- FastAPI `/ask` with schema validation and structured errors
- grounded-answer score `>= 0.85`
- retrieval p95 `< 300 ms`; model network latency measured separately
- maximum 3 retries, then structured `503`
- parser, idempotency, and retrieval branch coverage `>= 85%`

## Known limitations

1. v0.1 uses lexical retrieval, not embeddings or an LLM.
2. The parser supports an explicit fixture-backed contract; current TCMB HTML variants still require live verification.
3. No scheduler, backfill discovery, PostgreSQL, dbt, API, load test, deployment, or monitoring exists yet.
4. The example live URL is intentionally not pinned in tests; tests are offline and reproducible.

## Security and privacy

- No credentials are required or stored.
- CI scans tracked text for common secret patterns.
- Network access is explicit and limited to user-supplied URLs.
- Raw source provenance is retained; responses expose citations rather than hiding the source.

See [SECURITY.md](SECURITY.md) for responsible disclosure.

## License

MIT. See [LICENSE](LICENSE).
