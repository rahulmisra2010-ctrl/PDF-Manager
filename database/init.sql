-- PDF-Manager Database Initialization Script
-- Creates the database, role, and applies the schema.
-- Run as a PostgreSQL superuser (e.g. postgres).

-- Create application role (skip if it already exists)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'pdfmanager') THEN
        CREATE ROLE pdfmanager WITH LOGIN PASSWORD 'pdfmanager';
    END IF;
END
$$;

-- Create database (must be run outside a transaction block)
-- Run manually if needed:
--   CREATE DATABASE pdfmanager OWNER pdfmanager;

-- Connect to the target database before running the schema:
--   \c pdfmanager

GRANT USAGE ON SCHEMA public TO pdfmanager;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO pdfmanager;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO pdfmanager;

-- Apply the schema
\i schema.sql

-- Seed a default admin user for local development
INSERT INTO users (email, name)
VALUES ('admin@pdfmanager.local', 'Admin User')
ON CONFLICT (email) DO NOTHING;
