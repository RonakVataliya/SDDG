-- 0008 Input methods and validation (FR1, FR2, FR3): uploaded PDF/DOCX documents, the original FR/NFR ID and
-- user-story fields of each statement, and the document an extraction job came from.
-- Also in schema.sql; here so a database made from an older schema.sql gets it. Safe to run again.
ALTER TABLE statements ADD COLUMN IF NOT EXISTS source_label text;  -- original ID from the input, e.g. FR-001
ALTER TABLE statements ADD COLUMN IF NOT EXISTS metadata text;      -- encrypted JSON: {structured, role, goal, reason}

-- Stored in Supabase Storage, tracked here. filename is encrypted (core/db.py SECRET).
CREATE TABLE IF NOT EXISTS documents (
  id text PRIMARY KEY,
  project_id text NOT NULL REFERENCES projects ON DELETE CASCADE,
  filename text NOT NULL,
  storage_path text NOT NULL,
  content_type text NOT NULL,
  size_bytes bigint NOT NULL,
  page_count int NOT NULL,
  status text NOT NULL,
  warning text,
  skipped_pages text,
  job_id text,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL);
CREATE INDEX IF NOT EXISTS documents_project_idx ON documents (project_id);
CREATE INDEX IF NOT EXISTS documents_job_idx ON documents (job_id);
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS document_id text;
CREATE INDEX IF NOT EXISTS jobs_document_idx ON jobs (document_id);
