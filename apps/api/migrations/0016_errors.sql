-- 0016 Errors (FR25d): what went wrong, for the admin Errors page.
-- Also in schema.sql; here so a database made from an older schema.sql gets it. Safe to run again.
-- Kinds, severities, class names and IDs only: never requirement or document text (core/db.py record_error).
-- No foreign keys: an error outlives the project it happened in.
CREATE TABLE IF NOT EXISTS errors (
  id text PRIMARY KEY,
  type text NOT NULL,       -- api (unhandled exception), job (failed job), ai (failed AI call), rate_limit
  severity text NOT NULL,   -- error or warning
  message text NOT NULL,    -- built by the server from kinds and class names, e.g. "ValueError in POST /projects/{project_id}/generate"
  project_id text,
  ref text,                 -- job id, when there is one
  created_at timestamptz NOT NULL);
CREATE INDEX IF NOT EXISTS errors_created_idx ON errors (created_at DESC);
ALTER TABLE errors ENABLE ROW LEVEL SECURITY;
