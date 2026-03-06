-- PDF-Manager SQLite Schema
-- Compatible with SQLite 3.x (used by Flask-SQLAlchemy default configuration)
-- SQLAlchemy/Flask creates these tables automatically via db.create_all().
-- This file is provided as a reference and for manual inspection / migration.

-- ---------------------------------------------------------------------------
-- Users
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id           INTEGER  PRIMARY KEY AUTOINCREMENT,
    username     TEXT     NOT NULL UNIQUE,
    email        TEXT     NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    role         TEXT     NOT NULL DEFAULT 'Viewer'
                          CHECK (role IN ('Admin', 'Verifier', 'Viewer')),
    is_active    INTEGER  NOT NULL DEFAULT 1,   -- boolean: 1=true, 0=false
    created_at   DATETIME NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------------------
-- Documents (uploaded PDFs)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    id           INTEGER  PRIMARY KEY AUTOINCREMENT,
    filename     TEXT     NOT NULL,
    file_path    TEXT     NOT NULL,
    status       TEXT     NOT NULL DEFAULT 'uploaded'
                          CHECK (status IN ('uploaded', 'extracted', 'edited', 'approved', 'rejected')),
    uploaded_by  INTEGER  REFERENCES users(id) ON DELETE SET NULL,
    created_at   DATETIME NOT NULL DEFAULT (datetime('now')),
    page_count   INTEGER,
    file_size    INTEGER   -- bytes
);

CREATE INDEX IF NOT EXISTS idx_documents_status     ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_uploaded_by ON documents(uploaded_by);

-- ---------------------------------------------------------------------------
-- Extracted Fields
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS extracted_fields (
    id             INTEGER  PRIMARY KEY AUTOINCREMENT,
    document_id    INTEGER  NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    field_name     TEXT     NOT NULL,
    value          TEXT,
    confidence     REAL     NOT NULL DEFAULT 1.0,
    is_edited      INTEGER  NOT NULL DEFAULT 0,  -- boolean
    original_value TEXT
);

CREATE INDEX IF NOT EXISTS idx_extracted_fields_document_id ON extracted_fields(document_id);

-- ---------------------------------------------------------------------------
-- Audit Log
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_logs (
    id            INTEGER  PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER  REFERENCES users(id) ON DELETE SET NULL,
    action        TEXT     NOT NULL,
    resource_type TEXT,
    resource_id   TEXT,
    details       TEXT,
    timestamp     DATETIME NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id   ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp  ON audit_logs(timestamp);

