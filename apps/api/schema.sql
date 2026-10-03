-- Idempotent. Applied automatically at API startup; safe to paste into the Supabase SQL editor too.
CREATE TABLE IF NOT EXISTS users (id text PRIMARY KEY, email text UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS consents (user_id text PRIMARY KEY, policy_version text NOT NULL, consented_at timestamptz NOT NULL);
CREATE TABLE IF NOT EXISTS projects (
  id text PRIMARY KEY, owner_id text NOT NULL, name text NOT NULL,
  created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL, confirmed_at timestamptz);
CREATE INDEX IF NOT EXISTS projects_owner_idx ON projects (owner_id);
CREATE TABLE IF NOT EXISTS statements (
  id text PRIMARY KEY, project_id text NOT NULL REFERENCES projects ON DELETE CASCADE,
  ref text NOT NULL, text text NOT NULL, label text, source_document text NOT NULL,
  source_page int, source_paragraph int, source_line_start int, source_line_end int, source_excerpt text);
CREATE TABLE IF NOT EXISTS items (
  id text PRIMARY KEY, project_id text NOT NULL REFERENCES projects ON DELETE CASCADE,
  category text NOT NULL, name text NOT NULL, description text, origin text NOT NULL,
  qualifiers text NOT NULL, statement_ids text NOT NULL,
  source_item_id text, target_item_id text, relation_type text);
CREATE TABLE IF NOT EXISTS jobs (
  id text PRIMARY KEY, project_id text NOT NULL REFERENCES projects ON DELETE CASCADE,
  kind text NOT NULL, status text NOT NULL, queue_position int,
  progress_step int NOT NULL, progress_total int NOT NULL, progress_label text NOT NULL,
  diagram_types text NOT NULL, diagram_ids text NOT NULL, error text,
  created_at timestamptz NOT NULL, started_at timestamptz, finished_at timestamptz);
CREATE INDEX IF NOT EXISTS jobs_project_idx ON jobs (project_id);
CREATE TABLE IF NOT EXISTS diagrams (
  id text PRIMARY KEY, project_id text NOT NULL REFERENCES projects ON DELETE CASCADE,
  type text NOT NULL, title text NOT NULL, created_at timestamptz NOT NULL,
  svg text NOT NULL, elements text NOT NULL, statement_ids text NOT NULL,
  plantuml_source text, parent_id text, instruction text, spec text);
CREATE INDEX IF NOT EXISTS diagrams_project_idx ON diagrams (project_id);

-- Insertion order for statements/items (Postgres has no rowid; ids are random).
ALTER TABLE statements ADD COLUMN IF NOT EXISTS seq bigint GENERATED ALWAYS AS IDENTITY;
ALTER TABLE items ADD COLUMN IF NOT EXISTS seq bigint GENERATED ALWAYS AS IDENTITY;
CREATE INDEX IF NOT EXISTS statements_project_idx ON statements (project_id, seq);
CREATE INDEX IF NOT EXISTS items_project_idx ON items (project_id, seq);

-- Supabase exposes public tables through its REST API to anyone with the publishable key.
-- RLS on + no policies = closed to the REST API; this backend connects as the postgres role, which bypasses RLS.
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE consents ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE statements ENABLE ROW LEVEL SECURITY;
ALTER TABLE items ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE diagrams ENABLE ROW LEVEL SECURITY;
