<h1 align="center">TCMB Policy RAG Pipeline</h1>

<p align="center">
  Ask a question about a Turkish central bank rate decision and get an answer<br>
  that carries its source URL, title and publication date —<br>
  or the word <b><code>insufficient_evidence</code></b>, because a confident guess is worse than nothing.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/offline%20tests-8-FF4D4F?style=flat-square" alt="8 offline tests">
  <img src="https://img.shields.io/badge/python%20versions-3.11%20%C2%B7%203.12%20%C2%B7%203.13-FF4D4F?style=flat-square" alt="Python 3.11, 3.12, 3.13">
  <img src="https://img.shields.io/badge/re--ingest%20duplicates-0-FF4D4F?style=flat-square" alt="0 duplicates on re-ingest">
</p>

---

## Run it in 60 seconds

```bash
python -m venv .venv
. .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e .
python -m unittest discover -s tests -v

tcmb-policy ingest "https://www.tcmb.gov.tr/..." --raw-dir data/raw
tcmb-policy ask "Politika faizi hakkında ne karar verildi?"
```

No API key, no vector database, no model download. The tests run entirely offline
from deterministic fixtures.

## What happens to a document

```text
TCMB URL -> fetch -> immutable raw HTML -> parse/validate
                                      |-> quarantine
                                      `-> versioned documents -> chunks -> SQLite FTS5
                                                                  `-> cited answer / abstain
```

The raw layer is content-addressed by SHA-256. A database transaction writes the
document and all of its chunks atomically: either the version is complete, or
nothing is committed. Live TCMB pages change structure, so the parser
**quarantines** anything that fails its explicit contract rather than silently
writing bad data.

## What is actually implemented in v0.1

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

| Table | Purpose | Important guarantees |
|---|---|---|
| `documents` | one row per source version | unique SHA-256 checksum; URL + checksum uniqueness |
| `chunks` | retrievable evidence | document FK; deterministic ordinal and hash |
| `chunks_fts` | lexical retrieval index | Unicode tokenization; BM25 ranking |
| `quarantine` | rejected source versions | reason + checksum; repeat failures deduplicated |

## Limits

1. v0.1 uses **lexical** retrieval — no embeddings, no LLM.
2. The parser supports an explicit fixture-backed contract; current TCMB HTML variants still require live verification.
3. No scheduler, backfill discovery, PostgreSQL, dbt, API, load test, deployment, or monitoring exists yet.
4. The example live URL is intentionally not pinned in tests; tests are offline and reproducible.
5. PostgreSQL/pgvector, dbt, scheduled discovery, generation, and the 30-question offline evaluation set are **planned — not claimed as complete**.

Verification gates, run on Python 3.11, 3.12 and 3.13 in CI:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python -m compileall -q src tests
```

No production claim is made until live-source, scale, security, recovery, and
deployment evidence exists.

<details>
<summary><b>Roadmap with measurable gates</b></summary>

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

</details>

<details>
<summary><b>Security and privacy</b></summary>

- No credentials are required or stored.
- CI scans tracked text for common secret patterns.
- Network access is explicit and limited to user-supplied URLs.
- Raw source provenance is retained; responses expose citations rather than hiding the source.

See [SECURITY.md](SECURITY.md) for responsible disclosure.

</details>

---

A credible RAG system starts with reliable data engineering — provenance, versioning, idempotency, quarantine, and abstention. That is the part this repository refuses to skip.

MIT — see [LICENSE](LICENSE).
