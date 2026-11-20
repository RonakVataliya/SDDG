-- 0009 Roles, revisions and comments (Sprint 3 shared contracts, Raj). One file because 0005-0008 were taken on main.
-- Three independent parts; every statement is safe to run twice.

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
