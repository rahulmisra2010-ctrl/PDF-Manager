-- PDF-Manager PostgreSQL Schema
-- Run this file to create the database tables

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ---------------------------------------------------------------------------
-- Users
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT        NOT NULL UNIQUE,
    name        TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ---------------------------------------------------------------------------
-- Documents (uploaded PDFs)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID        REFERENCES users(id) ON DELETE SET NULL,
    filename        TEXT        NOT NULL,
    file_path       TEXT        NOT NULL,
    file_size_bytes BIGINT,
    page_count      INT,
    status          TEXT        NOT NULL DEFAULT 'uploaded'
                                CHECK (status IN ('uploaded', 'extracted', 'edited', 'exported')),
    uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_status  ON documents(status);

-- ---------------------------------------------------------------------------
-- Extracted Data Fields
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS extracted_fields (
    id            UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   UUID    NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    field_name    TEXT    NOT NULL,
    field_value   TEXT,
    confidence    NUMERIC(5, 4) CHECK (confidence BETWEEN 0 AND 1),
    page_number   INT     NOT NULL DEFAULT 1 CHECK (page_number >= 1),
    bbox_x0       NUMERIC,
    bbox_y0       NUMERIC,
    bbox_x1       NUMERIC,
    bbox_y1       NUMERIC,
    is_edited     BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_extracted_fields_document_id ON extracted_fields(document_id);

-- ---------------------------------------------------------------------------
-- Detected Tables (structured tabular data from PDFs)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS detected_tables (
    id            UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   UUID    NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    table_index   INT     NOT NULL,
    page_number   INT     NOT NULL DEFAULT 1,
    data          JSONB   NOT NULL DEFAULT '[]',   -- list of rows; each row is a list of cell strings
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_detected_tables_document_id ON detected_tables(document_id);

-- ---------------------------------------------------------------------------
-- Exports
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS exports (
    id            UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id   UUID    NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    format        TEXT    NOT NULL CHECK (format IN ('pdf', 'json', 'csv')),
    file_path     TEXT    NOT NULL,
    download_url  TEXT,
    expires_at    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_exports_document_id ON exports(document_id);

-- ---------------------------------------------------------------------------
-- Auto-update updated_at timestamps
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE OR REPLACE TRIGGER trg_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE OR REPLACE TRIGGER trg_extracted_fields_updated_at
    BEFORE UPDATE ON extracted_fields
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
