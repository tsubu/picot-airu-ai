"""SQLite schema and connection helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    filename TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    total_messages INTEGER NOT NULL DEFAULT 0,
    new_messages INTEGER NOT NULL DEFAULT 0,
    duplicate_messages INTEGER NOT NULL DEFAULT 0,
    qa_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS raw_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type TEXT NOT NULL,
    source_id TEXT,
    message_id TEXT,
    payload_json TEXT NOT NULL,
    body_hash TEXT,
    imported_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source_type, source_id),
    UNIQUE(message_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    raw_message_id INTEGER REFERENCES raw_messages(id),
    message_id TEXT,
    subject TEXT,
    from_address TEXT,
    to_addresses TEXT,
    cc_addresses TEXT,
    date TEXT,
    body_text TEXT,
    body_html TEXT,
    in_reply_to TEXT,
    references_header TEXT,
    source_type TEXT,
    source_id TEXT,
    role TEXT,
    body_hash TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    summary TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS conversation_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL UNIQUE REFERENCES conversations(id) ON DELETE CASCADE,
    summary TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS qa_pairs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    category TEXT,
    product TEXT,
    confidence REAL,
    verified INTEGER NOT NULL DEFAULT 0,
    source_message_ids TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ai_responses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    message_id INTEGER REFERENCES conversation_messages(id),
    model TEXT,
    prompt_version TEXT,
    confidence REAL,
    status TEXT NOT NULL DEFAULT 'ok',
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS rag_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ai_response_id INTEGER NOT NULL REFERENCES ai_responses(id) ON DELETE CASCADE,
    qa_id INTEGER,
    score REAL,
    rank INTEGER
);

CREATE TABLE IF NOT EXISTS app_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    level TEXT NOT NULL,
    event TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS qa_embedding_status (
    qa_id INTEGER PRIMARY KEY REFERENCES qa_pairs(id) ON DELETE CASCADE,
    embedded_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS graph_entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    description TEXT,
    source_qa_ids TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(entity_type, normalized_name)
);

CREATE TABLE IF NOT EXISTS graph_relations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_entity_id INTEGER NOT NULL REFERENCES graph_entities(id) ON DELETE CASCADE,
    to_entity_id INTEGER NOT NULL REFERENCES graph_entities(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 1.0,
    source_qa_id INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(from_entity_id, to_entity_id, relation_type, source_qa_id)
);

CREATE TABLE IF NOT EXISTS graph_builds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    entity_count INTEGER NOT NULL DEFAULT 0,
    relation_count INTEGER NOT NULL DEFAULT 0,
    qa_processed INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running',
    detail TEXT
);

CREATE INDEX IF NOT EXISTS idx_messages_message_id ON messages(message_id);
CREATE INDEX IF NOT EXISTS idx_messages_body_hash ON messages(body_hash);
CREATE INDEX IF NOT EXISTS idx_qa_pairs_created_at ON qa_pairs(created_at);
CREATE INDEX IF NOT EXISTS idx_conversations_updated_at ON conversations(updated_at);
CREATE INDEX IF NOT EXISTS idx_graph_entities_type_name ON graph_entities(entity_type, normalized_name);
CREATE INDEX IF NOT EXISTS idx_graph_relations_from ON graph_relations(from_entity_id);
CREATE INDEX IF NOT EXISTS idx_graph_relations_to ON graph_relations(to_entity_id);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate(db_path: Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        from security.credentials import ensure_default_settings

        ensure_default_settings(conn)
        conn.commit()
