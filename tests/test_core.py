from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from tcmb_policy_rag.core import Store, ValidationError, grounded_answer, parse_document


FIXTURES = Path(__file__).parent / "fixtures"
URL = "https://www.tcmb.gov.tr/ppk/2026-08-20"


class PipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / "policy.db")
        self.html = (FIXTURES / "valid.html").read_bytes()

    def tearDown(self) -> None:
        self.store.close()
        self.temp.cleanup()

    def test_parser_extracts_required_metadata(self) -> None:
        parsed = parse_document(URL, self.html)
        self.assertEqual(parsed.published_date, "2026-08-20")
        self.assertIn("Para Politikası Kurulu", parsed.title)
        self.assertEqual(len(parsed.checksum), 64)

    def test_invalid_document_fails_validation(self) -> None:
        with self.assertRaises(ValidationError):
            parse_document(URL, (FIXTURES / "invalid.html").read_bytes())

    def test_second_ingestion_is_idempotent(self) -> None:
        parsed = parse_document(URL, self.html)
        first = self.store.ingest(parsed, self.root / "raw.html")
        second = self.store.ingest(parsed, self.root / "raw.html")
        self.assertEqual(first["documents_added"], 1)
        self.assertGreater(first["chunks_added"], 0)
        self.assertEqual(second, {"status": "unchanged", "documents_added": 0, "chunks_added": 0})

    def test_changed_checksum_preserves_old_version(self) -> None:
        first = parse_document(URL, self.html)
        revised_html = self.html.replace("sabit tutulmasına".encode(), "artırılmasına".encode())
        self.assertNotEqual(revised_html, self.html)
        second = parse_document(URL, revised_html)
        self.store.ingest(first, self.root / "v1.html")
        self.store.ingest(second, self.root / "v2.html")
        count = self.store.connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        self.assertEqual(count, 2)

    def test_quarantine_deduplicates_same_failure(self) -> None:
        bad = (FIXTURES / "invalid.html").read_bytes()
        for _ in range(2):
            try:
                parse_document(URL, bad)
            except ValidationError as exc:
                self.store.quarantine(URL, bad, str(exc))
        count = self.store.connection.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0]
        self.assertEqual(count, 1)

    def test_retrieval_returns_citation(self) -> None:
        parsed = parse_document(URL, self.html)
        self.store.ingest(parsed, self.root / "raw.html")
        result = grounded_answer(self.store, "politika faizi kararı nedir")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["citations"][0]["source_url"], URL)

    def test_no_overlap_returns_insufficient_evidence(self) -> None:
        parsed = parse_document(URL, self.html)
        self.store.ingest(parsed, self.root / "raw.html")
        result = grounded_answer(self.store, "mars yörünge uzay aracı")
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertIsNone(result["answer"])

    def test_foreign_keys_enabled(self) -> None:
        value = self.store.connection.execute("PRAGMA foreign_keys").fetchone()[0]
        self.assertEqual(value, 1)
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.connection.execute(
                "INSERT INTO chunks(document_id, ordinal, text, chunk_hash) VALUES (999, 0, 'x', 'h')"
            )


if __name__ == "__main__":
    unittest.main()
