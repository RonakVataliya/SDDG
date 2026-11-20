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
-- Projects from before project_members existed get their creator as a member. Only projects with no members at
-- all, so running this file again never brings back a creator who left or was removed (Members page).
INSERT INTO project_members (project_id, user_id)
  SELECT p.id, p.owner_id FROM projects p
  WHERE NOT EXISTS (SELECT 1 FROM project_members m WHERE m.project_id = p.id)
ON CONFLICT DO NOTHING;
ALTER TABLE project_members ENABLE ROW LEVEL SECURITY;
CREATE TABLE IF NOT EXISTS statements (
  id text PRIMARY KEY, project_id text NOT NULL REFERENCES projects ON DELETE CASCADE,
  ref text NOT NULL, text text NOT NULL, label text, source_document text NOT NULL,
  source_page int, source_paragraph int, source_line_start int, source_line_end int, source_excerpt text);
ALTER TABLE statements
ADD COLUMN IF NOT EXISTS source_label text;

ALTER TABLE statements
ADD COLUMN IF NOT EXISTS metadata text;
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

-- Project documents (FR1b, FR1c, FR2). Stored in Supabase Storage, tracked here.
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
  updated_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS documents_project_idx ON documents (project_id);
ALTER TABLE documents ADD COLUMN IF NOT EXISTS job_id text;
CREATE INDEX IF NOT EXISTS documents_job_idx ON documents (job_id);
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS document_id text;
CREATE INDEX IF NOT EXISTS jobs_document_idx ON jobs (document_id);

-- Diagram look chosen by the user (#38): JSON, see core/styling.py. NULL = inherit from parent_id, else default.
ALTER TABLE diagrams ADD COLUMN IF NOT EXISTS style text;

-- Stream 5: PM reporting and client management (FR3b, FR3e, FR20, FR21, FR32).
-- The client is stored on the project (no client directory). archived_at marks an archived project: the web app
-- shows it read-only and Home lists it under Archived; the API does not block writes to it.
ALTER TABLE projects ADD COLUMN IF NOT EXISTS client_name text;     -- encrypted; Home groups projects by it
ALTER TABLE projects ADD COLUMN IF NOT EXISTS contact_email text;   -- lowercased
ALTER TABLE projects ADD COLUMN IF NOT EXISTS archived_at timestamptz;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS archived_by text;

-- Requirements-first workflow: which extraction nodes (actors, entities, …) have run on the confirmed
-- requirements, as a JSON list. Reset whenever a requirement changes, so the next generation re-extracts.
ALTER TABLE projects ADD COLUMN IF NOT EXISTS extracted_nodes text NOT NULL DEFAULT '[]';

-- Design packs and reviews were dropped from Stream 5. Removes them where an earlier PM build created them.
DROP TABLE IF EXISTS reviews, design_packs;

-- Tests feature (Sprint 3, stream 6): test design per requirement, test cases and manual runs.
-- Every table has project_id, so access checks and tests_access.py's encryption sweep can find its rows.
-- Text and JSON columns that hold requirement content are encrypted (core/db.py SECRET).

-- One row per requirement that AI request 1 has designed. requirement_hash (an HMAC of the requirement text at the
-- time) tells later reads whether the text has changed since.
CREATE TABLE IF NOT EXISTS test_designs (
  statement_id text PRIMARY KEY REFERENCES statements ON DELETE CASCADE,
  project_id text NOT NULL REFERENCES projects ON DELETE CASCADE,
  requirement_hash text NOT NULL,
  performance_targets text NOT NULL,          -- JSON list: [{measure, limit, unit, load}]
  generated_at timestamptz NOT NULL);
CREATE INDEX IF NOT EXISTS test_designs_project_idx ON test_designs (project_id);

-- Acceptance criteria in Given / When / Then form.
CREATE TABLE IF NOT EXISTS test_criteria (
  id text PRIMARY KEY,
  project_id text NOT NULL REFERENCES projects ON DELETE CASCADE,
  statement_id text NOT NULL REFERENCES statements ON DELETE CASCADE,
  given_text text NOT NULL, when_text text NOT NULL, then_text text NOT NULL,
  seq bigint GENERATED ALWAYS AS IDENTITY);
CREATE INDEX IF NOT EXISTS test_criteria_project_idx ON test_criteria (project_id, statement_id, seq);

-- The inputs a requirement talks about. kind: range | count | set.
CREATE TABLE IF NOT EXISTS test_conditions (
  id text PRIMARY KEY,
  project_id text NOT NULL REFERENCES projects ON DELETE CASCADE,
  statement_id text NOT NULL REFERENCES statements ON DELETE CASCADE,
  name text NOT NULL, kind text NOT NULL, description text, unit text,
  limits text NOT NULL,                        -- JSON {"min": n|null, "max": n|null}
  set_values text NOT NULL,                    -- JSON list of valid values (sets)
  invalid_values text NOT NULL,                -- JSON list of values a set must reject
  classes text,                                -- JSON [{label, valid}], from the AI service's /tests/derive
  boundaries text,                             -- JSON [{value, valid}], from the AI service's /tests/derive
  seq bigint GENERATED ALWAYS AS IDENTITY);
CREATE INDEX IF NOT EXISTS test_conditions_project_idx ON test_conditions (project_id, statement_id, seq);
-- For a database that ran an earlier draft of this table: add the columns if they are missing (no-op otherwise).
ALTER TABLE test_conditions ADD COLUMN IF NOT EXISTS classes text;
ALTER TABLE test_conditions ADD COLUMN IF NOT EXISTS boundaries text;

-- Basic and alternate flows. kind: basic | alternate.
CREATE TABLE IF NOT EXISTS test_flows (
  id text PRIMARY KEY,
  project_id text NOT NULL REFERENCES projects ON DELETE CASCADE,
  statement_id text NOT NULL REFERENCES statements ON DELETE CASCADE,
  kind text NOT NULL, flow_text text NOT NULL,
  seq bigint GENERATED ALWAYS AS IDENTITY);
CREATE INDEX IF NOT EXISTS test_flows_project_idx ON test_flows (project_id, statement_id, seq);

-- Test cases. number (TC-001...) is never reused within a project.
-- status: draft (no steps yet) | ready. origin: generated | manual. kept=false: a draft the user unticked.
CREATE TABLE IF NOT EXISTS test_cases (
  id text PRIMARY KEY,
  project_id text NOT NULL REFERENCES projects ON DELETE CASCADE,
  statement_id text NOT NULL REFERENCES statements ON DELETE CASCADE,
  number text NOT NULL, title text NOT NULL,
  technique text NOT NULL, kind text NOT NULL, priority text NOT NULL,
  status text NOT NULL, kept boolean NOT NULL, origin text NOT NULL, outcome text,
  test_data text NOT NULL, covers text NOT NULL, preconditions text NOT NULL, steps text NOT NULL, expected text,
  requirement_hash text NOT NULL,              -- HMAC of the requirement text the case was written for
  created_at timestamptz NOT NULL,
  seq bigint GENERATED ALWAYS AS IDENTITY,
  UNIQUE (project_id, number));
CREATE INDEX IF NOT EXISTS test_cases_project_idx ON test_cases (project_id, seq);

-- Last TC number handed out per project. Drafts are replaced when a design changes, so numbering cannot come from
-- max(number) the way R-numbers do: that would hand a deleted draft's number to a new case.
CREATE TABLE IF NOT EXISTS test_counters (
  project_id text PRIMARY KEY REFERENCES projects ON DELETE CASCADE,
  last_case integer NOT NULL);

-- Manual runs. mode: all | failed | regression | minimal | pick. A run is open until finished_at is set.
CREATE TABLE IF NOT EXISTS test_runs (
  id text PRIMARY KEY,
  project_id text NOT NULL REFERENCES projects ON DELETE CASCADE,
  name text NOT NULL, mode text NOT NULL,
  case_ids text NOT NULL,                      -- JSON list, in the order the run shows them
  created_by text NOT NULL, created_at timestamptz NOT NULL, finished_at timestamptz);
CREATE INDEX IF NOT EXISTS test_runs_project_idx ON test_runs (project_id, created_at);

-- One result per case per run. status: pass | fail | blocked | skipped. Who marked it and when are kept.
CREATE TABLE IF NOT EXISTS test_results (
  run_id text NOT NULL REFERENCES test_runs ON DELETE CASCADE,
  case_id text NOT NULL REFERENCES test_cases ON DELETE CASCADE,
  project_id text NOT NULL REFERENCES projects ON DELETE CASCADE,
  status text NOT NULL, note text, marked_by text NOT NULL, marked_at timestamptz NOT NULL,
  PRIMARY KEY (run_id, case_id));
CREATE INDEX IF NOT EXISTS test_results_case_idx ON test_results (case_id);

ALTER TABLE test_designs ENABLE ROW LEVEL SECURITY;
ALTER TABLE test_criteria ENABLE ROW LEVEL SECURITY;
ALTER TABLE test_conditions ENABLE ROW LEVEL SECURITY;
ALTER TABLE test_flows ENABLE ROW LEVEL SECURITY;
ALTER TABLE test_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE test_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE test_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE test_counters ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------------------------------------------
-- Raj: roles, revisions and comments (Sprint 3 shared contracts). Same statements as migrations/0009.
-- ---------------------------------------------------------------------------------------------------------------

-- Roles (shared contract, FR24): every project member has exactly one role, read from here on every request.
-- viewer < editor < owner. Existing members (each project's creator) become owners. Safe to run twice.
ALTER TABLE project_members ADD COLUMN IF NOT EXISTS role text NOT NULL DEFAULT 'owner';
ALTER TABLE project_members DROP CONSTRAINT IF EXISTS project_members_role_check;
ALTER TABLE project_members ADD CONSTRAINT project_members_role_check CHECK (role IN ('viewer', 'editor', 'owner'));

-- When the person joined, for the Members page ("Created the project" or a date). Existing members joined when their
-- project was created; only rows still without a date are filled, so a second run changes nothing.
ALTER TABLE project_members ADD COLUMN IF NOT EXISTS joined_at timestamptz;
UPDATE project_members m SET joined_at = p.created_at FROM projects p WHERE p.id = m.project_id AND m.joined_at IS NULL;
ALTER TABLE project_members ALTER COLUMN joined_at SET DEFAULT now();

-- A System Administrator counts as Owner on every project (require_role). The users columns belong to the admin
-- console (Nitin, 0015-0019); is_admin is added here too, with IF NOT EXISTS, so roles work whichever runs first.
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin boolean NOT NULL DEFAULT false;

-- Revisions (shared contract, FR24f edit conflict check): every save of a requirement, item or diagram version
-- counts up its revision, starting at 1. A save sends the revision it was based on; a newer stored one means someone
-- else saved in between (409). revised_by / revised_at say who saved the current revision and when (user id only,
-- never content). A diagram edit is a new row, so its revision is its parent's plus one. Safe to run twice.
ALTER TABLE statements ADD COLUMN IF NOT EXISTS revision int NOT NULL DEFAULT 1;
ALTER TABLE statements ADD COLUMN IF NOT EXISTS revised_by text;
ALTER TABLE statements ADD COLUMN IF NOT EXISTS revised_at timestamptz;
ALTER TABLE items ADD COLUMN IF NOT EXISTS revision int NOT NULL DEFAULT 1;
ALTER TABLE items ADD COLUMN IF NOT EXISTS revised_by text;
ALTER TABLE items ADD COLUMN IF NOT EXISTS revised_at timestamptz;
ALTER TABLE diagrams ADD COLUMN IF NOT EXISTS revision int NOT NULL DEFAULT 1;
ALTER TABLE diagrams ADD COLUMN IF NOT EXISTS revised_by text;

-- Comments and issue reports (shared contract, FR32, FR27a-c). Any member, even a Viewer, can comment on a
-- requirement or a diagram version; is_issue_report turns a comment into a feedback report that Owners (their
-- projects) and admins (all projects) see on the Feedback page. 'project' is for reports about the project as a
-- whole, e.g. its export. body is encrypted (core/db.py SECRET); author_id and resolved_by are user ids.
CREATE TABLE IF NOT EXISTS comments (
  id text PRIMARY KEY,
  project_id text NOT NULL REFERENCES projects ON DELETE CASCADE,
  target_type text NOT NULL CHECK (target_type IN ('statement', 'diagram', 'project')),
  target_id text NOT NULL,
  author_id text NOT NULL,
  body text NOT NULL,
  is_issue_report boolean NOT NULL DEFAULT false,
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
  resolved_by text,
  resolved_at timestamptz,
  created_at timestamptz NOT NULL);
CREATE INDEX IF NOT EXISTS comments_target_idx ON comments (project_id, target_type, target_id, created_at);
CREATE INDEX IF NOT EXISTS comments_reports_idx ON comments (created_at) WHERE is_issue_report;
ALTER TABLE comments ENABLE ROW LEVEL SECURITY;
