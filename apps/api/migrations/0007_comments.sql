-- 0007 Comments and issue reports (shared contract, FR32, FR27a-c). Any member, even a Viewer, can comment on a
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
