-- 0005 Stories backlog (3.4): user stories ("As a <role> I want to <goal> so I can <reason>") linked to requirements.
-- role_text, goal_text, reason_text and confirmations (a JSON list) hold user content and are encrypted (core/db.SECRET).
-- priority: must | should | could | wont; status: todo | in_progress | done; estimate in story points (0-100).
CREATE TABLE IF NOT EXISTS stories (
  id text PRIMARY KEY,
  project_id text NOT NULL REFERENCES projects ON DELETE CASCADE,
  ref text NOT NULL,
  role_text text NOT NULL, goal_text text NOT NULL, reason_text text NOT NULL, confirmations text NOT NULL,
  priority text NOT NULL, estimate integer, status text NOT NULL, assignee_id text,
  created_at timestamptz NOT NULL, updated_at timestamptz NOT NULL,
  UNIQUE (project_id, ref));

-- A deleted requirement drops its links only; a story left with none is shown as needing a requirement.
CREATE TABLE IF NOT EXISTS story_statements (
  story_id text NOT NULL REFERENCES stories ON DELETE CASCADE,
  statement_id text NOT NULL REFERENCES statements ON DELETE CASCADE,
  PRIMARY KEY (story_id, statement_id));
CREATE INDEX IF NOT EXISTS story_statements_statement_idx ON story_statements (statement_id);

-- Last S-number handed out per project, as test_counters does for TC numbers: a deleted story's number is never reused.
CREATE TABLE IF NOT EXISTS story_counters (
  project_id text PRIMARY KEY REFERENCES projects ON DELETE CASCADE,
  last_story integer NOT NULL);

ALTER TABLE stories ENABLE ROW LEVEL SECURITY;
ALTER TABLE story_statements ENABLE ROW LEVEL SECURITY;
ALTER TABLE story_counters ENABLE ROW LEVEL SECURITY;
