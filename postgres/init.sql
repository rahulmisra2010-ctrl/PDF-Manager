-- =============================================================================
-- PDF-Manager — PostgreSQL Production Initialization
-- Executed automatically by the postgres container on first startup.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Role / user
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'pdfmanager') THEN
        CREATE ROLE pdfmanager WITH LOGIN PASSWORD 'CHANGE_ME_AT_RUNTIME';
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- Database (created by POSTGRES_DB env var; just set permissions here)
-- ---------------------------------------------------------------------------
GRANT CONNECT ON DATABASE pdfmanager TO pdfmanager;
GRANT USAGE   ON SCHEMA public TO pdfmanager;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES    TO pdfmanager;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT, UPDATE           ON SEQUENCES TO pdfmanager;

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";  -- query performance

-- ---------------------------------------------------------------------------
-- Users table
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL        PRIMARY KEY,
    username      VARCHAR(80)   NOT NULL UNIQUE,
    email         VARCHAR(120)  NOT NULL UNIQUE,
    password_hash TEXT          NOT NULL,
    role          VARCHAR(20)   NOT NULL DEFAULT 'Viewer'
                                CHECK (role IN ('Admin', 'Verifier', 'Viewer')),
    is_active     BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Documents table
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    id           SERIAL       PRIMARY KEY,
    filename     TEXT         NOT NULL,
    file_path    TEXT         NOT NULL,
    status       VARCHAR(20)  NOT NULL DEFAULT 'uploaded'
                              CHECK (status IN ('uploaded','extracted','edited','approved','rejected')),
    uploaded_by  INTEGER      REFERENCES users(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    page_count   INTEGER,
    file_size    BIGINT
);

CREATE INDEX IF NOT EXISTS idx_documents_status      ON documents(status);
CREATE INDEX IF NOT EXISTS idx_documents_uploaded_by ON documents(uploaded_by);
CREATE INDEX IF NOT EXISTS idx_documents_created_at  ON documents(created_at DESC);

-- ---------------------------------------------------------------------------
-- Extracted fields table
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS extracted_fields (
    id             SERIAL      PRIMARY KEY,
    document_id    INTEGER     NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    field_name     TEXT        NOT NULL,
    value          TEXT,
    confidence     REAL        NOT NULL DEFAULT 1.0,
    is_edited      BOOLEAN     NOT NULL DEFAULT FALSE,
    original_value TEXT
);

CREATE INDEX IF NOT EXISTS idx_extracted_fields_document_id ON extracted_fields(document_id);

-- ---------------------------------------------------------------------------
-- Audit log table
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_logs (
    id            SERIAL       PRIMARY KEY,
    user_id       INTEGER      REFERENCES users(id) ON DELETE SET NULL,
    action        TEXT         NOT NULL,
    resource_type TEXT,
    resource_id   TEXT,
    details       TEXT,
    timestamp     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id   ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp DESC);

-- ---------------------------------------------------------------------------
-- Grant permissions on all newly created tables
-- ---------------------------------------------------------------------------
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES    IN SCHEMA public TO pdfmanager;
GRANT USAGE, SELECT, UPDATE           ON ALL SEQUENCES IN SCHEMA public TO pdfmanager;
