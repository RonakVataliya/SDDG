-- Idempotent. Run it by hand (psql or the Supabase SQL editor); the API does not apply it at startup.
CREATE TABLE IF NOT EXISTS users (id text PRIMARY KEY, email text UNIQUE NOT NULL);
CREATE TABLE IF NOT EXISTS consents (user_id text PRIMARY KEY, policy_version text NOT NULL, consented_at timestamptz NOT NULL);
CREATE TABLE IF NOT EXISTS projects (
  id text PRIMARY KEY, owner_id text NOT NULL, name text NOT NULL,
  created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL, confirmed_at timestamptz);
CREATE INDEX IF NOT EXISTS projects_owner_idx ON projects (owner_id);
-- Who may open a project. Every project route checks this table, not owner_id.
CREATE TABLE IF NOT EXISTS project_members (
  project_id text NOT NULL REFERENCES projects ON DELETE CASCADE, user_id text NOT NULL,
  PRIMARY KEY (project_id, user_id));
CREATE INDEX IF NOT EXISTS project_members_user_idx ON project_members (user_id);
INSERT INTO project_members (project_id, user_id) SELECT id, owner_id FROM projects ON CONFLICT DO NOTHING;
ALTER TABLE project_members ENABLE ROW LEVEL SECURITY;
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
ALTER TABLE diagrams ADD COLUMN IF NOT EXISTS layout text;  -- element positions {id: [x, y]} (issue #37)
-- Validation warnings the user accepted as-is (per diagram version, copied to edited versions).
CREATE TABLE IF NOT EXISTS accepted_warnings (
  diagram_id text NOT NULL REFERENCES diagrams ON DELETE CASCADE,
  warning_id text NOT NULL,
  accepted_by text NOT NULL, accepted_at timestamptz NOT NULL,
  PRIMARY KEY (diagram_id, warning_id));
ALTER TABLE accepted_warnings ENABLE ROW LEVEL SECURITY;

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

-- Requirement flags from the quality checker; explained and resolved by the user.
CREATE TABLE IF NOT EXISTS flags (
  id text PRIMARY KEY,
  project_id text NOT NULL REFERENCES projects ON DELETE CASCADE,
  statement_id text NOT NULL REFERENCES statements ON DELETE CASCADE,
  type text NOT NULL,                 -- ambiguous | incomplete | conflict
  reason text NOT NULL,
  trigger_text text,
  related_statement_id text,          -- the other requirement of a conflict
  question text, answer text, suggested_fix text,
  status text NOT NULL DEFAULT 'open', -- open | resolved
  resolved_by text, resolved_at timestamptz,
  created_at timestamptz NOT NULL,
  seq bigint GENERATED ALWAYS AS IDENTITY);
ALTER TABLE flags ENABLE ROW LEVEL SECURITY;

-- ===================== Sprint 3 =====================
-- Safe to re-run, and safe on a database that already holds Sprint 2 data.
-- Convention: "who did it" columns hold an email (as accepted_warnings.accepted_by does); *_ids columns hold a JSON list.

-- C1. Stable IDs: matched and kept, never wiped. updated_at is NULL until the row is first edited,
-- so existing diagrams are not all marked out of date by this migration.
ALTER TABLE statements ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'active';  -- active | removed
ALTER TABLE statements ADD COLUMN IF NOT EXISTS revision int NOT NULL DEFAULT 1;
ALTER TABLE statements ADD COLUMN IF NOT EXISTS updated_at timestamptz;
ALTER TABLE items ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'active';       -- active | stale
ALTER TABLE items ADD COLUMN IF NOT EXISTS updated_at timestamptz;

-- C2. Members and roles. Upgrades the table above: one row per invite, user_id filled once the invite is accepted.
-- The role default keeps the current create_project insert working (it only ever adds the owner).
ALTER TABLE project_members ADD COLUMN IF NOT EXISTS email text;
ALTER TABLE project_members ADD COLUMN IF NOT EXISTS role text NOT NULL DEFAULT 'owner';    -- owner | editor | viewer | client
ALTER TABLE project_members ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'active'; -- invited | active | removed
ALTER TABLE project_members ADD COLUMN IF NOT EXISTS invited_by text;
ALTER TABLE project_members ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE project_members DROP CONSTRAINT IF EXISTS project_members_pkey;
ALTER TABLE project_members ALTER COLUMN user_id DROP NOT NULL;
-- Cleanup below may touch the last owner row of a project; pause row triggers (e.g. keep-an-owner) for these two statements only.
ALTER TABLE project_members DISABLE TRIGGER USER;
-- A half-applied earlier run (primary key gone, index not yet made) lets line 13 insert owners twice; keep one copy.
DELETE FROM project_members a USING project_members b
  WHERE a.ctid > b.ctid AND a.project_id = b.project_id AND a.user_id = b.user_id;
CREATE UNIQUE INDEX IF NOT EXISTS project_members_user_uq ON project_members (project_id, user_id);
CREATE UNIQUE INDEX IF NOT EXISTS project_members_email_uq ON project_members (project_id, email);
UPDATE project_members m SET email = u.email FROM users u WHERE u.id = m.user_id AND m.email IS NULL;
ALTER TABLE project_members ENABLE TRIGGER USER;
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin boolean NOT NULL DEFAULT false;
ALTER TABLE users ADD COLUMN IF NOT EXISTS deactivated_at timestamptz;

-- Client management (A): a thin client directory; a project may belong to one client. Archived = read-only after handover.
CREATE TABLE IF NOT EXISTS clients (
  id text PRIMARY KEY, owner_id text NOT NULL, name text NOT NULL, created_at timestamptz NOT NULL);
ALTER TABLE clients ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS client_id text REFERENCES clients ON DELETE SET NULL;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS archived_at timestamptz;

-- Design pack (C): the diagrams and requirements the client is allowed to see. Sent to the client once shared_at is set.
CREATE TABLE IF NOT EXISTS design_packs (
  id text PRIMARY KEY, project_id text NOT NULL REFERENCES projects ON DELETE CASCADE,
  name text NOT NULL, diagram_ids text NOT NULL, statement_ids text NOT NULL,
  shared_at timestamptz, created_at timestamptz NOT NULL);
ALTER TABLE design_packs ENABLE ROW LEVEL SECURITY;

-- C3. Comments and sign-off. An approve on a design pack records the exact diagram versions it covered.
CREATE TABLE IF NOT EXISTS reviews (
  id text PRIMARY KEY, project_id text NOT NULL REFERENCES projects ON DELETE CASCADE,
  target_type text NOT NULL,          -- statement | diagram | pack
  target_id text NOT NULL,
  author text NOT NULL,
  kind text NOT NULL,                 -- comment | approve | request_changes
  body text, diagram_ids text,        -- diagram_ids: only on a pack approval
  created_at timestamptz NOT NULL, resolved_at timestamptz);
ALTER TABLE reviews ENABLE ROW LEVEL SECURITY;

-- Change requests (D): proposed requirement edits, previewed for impact, then accepted or rejected.
CREATE TABLE IF NOT EXISTS change_requests (
  id text PRIMARY KEY, project_id text NOT NULL REFERENCES projects ON DELETE CASCADE,
  description text NOT NULL,
  edits text NOT NULL,                -- JSON {statement_id: new text}
  status text NOT NULL DEFAULT 'open', -- open | accepted | rejected
  created_by text NOT NULL, created_at timestamptz NOT NULL,
  decided_by text, decided_at timestamptz);
ALTER TABLE change_requests ENABLE ROW LEVEL SECURITY;

-- Meeting audio. Chunks hold audio only until transcribed, then audio is set to NULL ("keep text only").
CREATE TABLE IF NOT EXISTS meetings (
  id text PRIMARY KEY, project_id text NOT NULL REFERENCES projects ON DELETE CASCADE,
  started_by text NOT NULL,
  consent_at timestamptz NOT NULL,    -- recording cannot start without consent
  status text NOT NULL DEFAULT 'recording', -- recording | transcribing | ready | failed
  started_at timestamptz NOT NULL, ended_at timestamptz,
  transcript text);                   -- merged, editable text with speaker labels and timestamps
ALTER TABLE meetings ENABLE ROW LEVEL SECURITY;
CREATE TABLE IF NOT EXISTS meeting_chunks (
  meeting_id text NOT NULL REFERENCES meetings ON DELETE CASCADE,
  track text NOT NULL,                -- tab | mic
  seq int NOT NULL,
  audio bytea, segments text, transcribed_at timestamptz,
  PRIMARY KEY (meeting_id, track, seq));
ALTER TABLE meeting_chunks ENABLE ROW LEVEL SECURITY;

-- Test design. A criterion or case is out of date when a statement it links to changed (see C1).
CREATE TABLE IF NOT EXISTS acceptance_criteria (
  id text PRIMARY KEY, project_id text NOT NULL REFERENCES projects ON DELETE CASCADE,
  statement_id text NOT NULL REFERENCES statements ON DELETE CASCADE,
  text text NOT NULL,                 -- Given / When / Then
  question text, answer text,         -- missing detail the AI asked about, and the user's reply
  created_at timestamptz NOT NULL);
ALTER TABLE acceptance_criteria ENABLE ROW LEVEL SECURITY;
CREATE TABLE IF NOT EXISTS test_cases (
  id text PRIMARY KEY, project_id text NOT NULL REFERENCES projects ON DELETE CASCADE,
  title text NOT NULL, kind text NOT NULL, -- positive | negative | edge
  preconditions text, steps text, expected text, -- steps stay NULL until the title is approved
  statement_ids text NOT NULL, created_at timestamptz NOT NULL);
ALTER TABLE test_cases ENABLE ROW LEVEL SECURITY;
CREATE TABLE IF NOT EXISTS test_runs (
  id text PRIMARY KEY, project_id text NOT NULL REFERENCES projects ON DELETE CASCADE,
  name text NOT NULL, started_by text NOT NULL, created_at timestamptz NOT NULL);
ALTER TABLE test_runs ENABLE ROW LEVEL SECURITY;
CREATE TABLE IF NOT EXISTS test_results (
  run_id text NOT NULL REFERENCES test_runs ON DELETE CASCADE,
  case_id text NOT NULL REFERENCES test_cases ON DELETE CASCADE,
  status text NOT NULL,               -- pass | fail | blocked | skipped
  note text, marked_by text NOT NULL, marked_at timestamptz NOT NULL,
  PRIMARY KEY (run_id, case_id));
ALTER TABLE test_results ENABLE ROW LEVEL SECURITY;
