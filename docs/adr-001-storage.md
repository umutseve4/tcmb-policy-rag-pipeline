# ADR-001: Start with SQLite FTS5 before pgvector

- **Status:** accepted for v0.1
- **Date:** 2026-08-23

## Context

The first milestone must prove source versioning, idempotency, quarantine, transactions, evidence retrieval, and citation behavior without hiding correctness behind infrastructure.

## Decision

Use SQLite with FTS5/BM25 for the first vertical slice. Keep document and chunk identities independent of the retrieval backend. Add PostgreSQL + pgvector only after multi-document live ingestion is verified.

## Consequences

- CI remains fast, offline, and reproducible.
- Retrieval is lexical, not semantic; this is stated as a limitation.
- The schema and acceptance tests provide a migration contract for the PostgreSQL milestone.
