"""Core ingestion and retrieval primitives.

The module intentionally uses only Python's standard library so the critical
idempotency, versioning, quarantine and citation paths stay easy to audit.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.request import Request, urlopen


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._ignored = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "nav", "footer"}:
            self._ignored += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "nav", "footer"} and self._ignored:
            self._ignored -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored:
            text = " ".join(data.split())
            if text:
                self.parts.append(text)


@dataclass(frozen=True)
class ParsedDocument:
    source_url: str
    title: str
    published_date: str
    text: str
    checksum: str


class ValidationError(ValueError):
    """Raised when a source cannot pass deterministic quality rules."""


def parse_document(source_url: str, html: bytes) -> ParsedDocument:
    checksum = hashlib.sha256(html).hexdigest()
    parser = _TextExtractor()
    parser.feed(html.decode("utf-8", errors="replace"))
    text = "\n".join(parser.parts)
    title_match = re.search(r"Para Politikası Kurulu[^\n]{0,160}", text, re.I)
    date_match = re.search(r"\b(20\d{2})[-./](0[1-9]|1[0-2])[-./]([0-2]\d|3[01])\b", text)
    if not title_match:
        raise ValidationError("missing PPK title")
    if not date_match:
        raise ValidationError("missing ISO-compatible publication date")
    if len(text) < 120:
        raise ValidationError("document text shorter than 120 characters")
    year, month, day = date_match.groups()
    return ParsedDocument(
        source_url=source_url,
        title=title_match.group(0).strip(),
        published_date=f"{year}-{month}-{day}",
        text=text,
        checksum=checksum,
    )


def chunk_text(text: str, *, max_chars: int = 900) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS documents (
  id INTEGER PRIMARY KEY,
  source_url TEXT NOT NULL,
  checksum TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  published_date TEXT NOT NULL,
  raw_path TEXT NOT NULL,
  ingested_at TEXT NOT NULL,
  UNIQUE(source_url, checksum)
);
CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES documents(id),
  ordinal INTEGER NOT NULL,
  text TEXT NOT NULL,
  chunk_hash TEXT NOT NULL UNIQUE,
  UNIQUE(document_id, ordinal)
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
  text, content='chunks', content_rowid='id', tokenize='unicode61'
);
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TABLE IF NOT EXISTS quarantine (
  id INTEGER PRIMARY KEY,
  source_url TEXT NOT NULL,
  checksum TEXT NOT NULL,
  reason TEXT NOT NULL,
  quarantined_at TEXT NOT NULL,
  UNIQUE(source_url, checksum)
);
"""


class Store:
    def __init__(self, database: Path) -> None:
        database.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(database)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)

    def close(self) -> None:
        self.connection.close()

    def quarantine(self, source_url: str, html: bytes, reason: str) -> None:
        checksum = hashlib.sha256(html).hexdigest()
        self.connection.execute(
            "INSERT OR IGNORE INTO quarantine(source_url, checksum, reason, quarantined_at) VALUES (?, ?, ?, ?)",
            (source_url, checksum, reason, datetime.now(UTC).isoformat()),
        )
        self.connection.commit()

    def ingest(self, document: ParsedDocument, raw_path: Path) -> dict[str, int | str]:
        existing = self.connection.execute(
            "SELECT id FROM documents WHERE checksum = ?", (document.checksum,)
        ).fetchone()
        if existing:
            return {"status": "unchanged", "documents_added": 0, "chunks_added": 0}
        with self.connection:
            cursor = self.connection.execute(
                "INSERT INTO documents(source_url, checksum, title, published_date, raw_path, ingested_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    document.source_url,
                    document.checksum,
                    document.title,
                    document.published_date,
                    str(raw_path),
                    datetime.now(UTC).isoformat(),
                ),
            )
            document_id = int(cursor.lastrowid)
            added = 0
            for ordinal, text in enumerate(chunk_text(document.text)):
                chunk_hash = hashlib.sha256(
                    f"{document.checksum}:{ordinal}:{text}".encode()
                ).hexdigest()
                result = self.connection.execute(
                    "INSERT OR IGNORE INTO chunks(document_id, ordinal, text, chunk_hash) VALUES (?, ?, ?, ?)",
                    (document_id, ordinal, text, chunk_hash),
                )
                added += result.rowcount
        return {"status": "ingested", "documents_added": 1, "chunks_added": added}

    def search(self, question: str, *, limit: int = 5) -> list[dict[str, str | float]]:
        tokens = [token for token in re.findall(r"\w+", question.lower()) if len(token) > 2]
        if not tokens:
            return []
        query = " OR ".join(f'"{token}"' for token in tokens)
        rows = self.connection.execute(
            """
            SELECT c.text, d.source_url, d.title, d.published_date,
                   bm25(chunks_fts) AS rank
            FROM chunks_fts
            JOIN chunks c ON c.id = chunks_fts.rowid
            JOIN documents d ON d.id = c.document_id
            WHERE chunks_fts MATCH ?
            ORDER BY rank ASC, d.published_date DESC
            LIMIT ?
            """,
            (query, limit),
        ).fetchall()
        return [
            {
                "text": row["text"],
                "source_url": row["source_url"],
                "title": row["title"],
                "published_date": row["published_date"],
                "score": round(float(-row["rank"]), 6),
            }
            for row in rows
        ]


def fetch(url: str, *, timeout: int = 20) -> bytes:
    request = Request(url, headers={"User-Agent": "tcmb-policy-rag-pipeline/0.1"})
    with urlopen(request, timeout=timeout) as response:
        return response.read()


def ingest_url(store: Store, url: str, raw_dir: Path) -> dict[str, int | str]:
    html = fetch(url)
    checksum = hashlib.sha256(html).hexdigest()
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{checksum}.html"
    raw_path.write_bytes(html)
    try:
        document = parse_document(url, html)
    except ValidationError as exc:
        store.quarantine(url, html, str(exc))
        return {"status": "quarantined", "documents_added": 0, "chunks_added": 0}
    return store.ingest(document, raw_path)


def grounded_answer(store: Store, question: str) -> dict[str, object]:
    evidence = store.search(question)
    if not evidence:
        return {"status": "insufficient_evidence", "answer": None, "citations": []}
    top = evidence[0]
    return {
        "status": "ok",
        "answer": top["text"],
        "citations": [
            {
                "source_url": item["source_url"],
                "title": item["title"],
                "published_date": item["published_date"],
            }
            for item in evidence
        ],
    }


def format_result(result: object) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)
