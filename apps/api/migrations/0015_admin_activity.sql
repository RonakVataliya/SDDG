-- 0015 Admin and activity log (FR22, FR23): admin flag, deactivation and last-seen on users; the activity log.
-- Also in schema.sql; here so a database made from an older schema.sql gets it. Safe to run again.
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin boolean NOT NULL DEFAULT false;
ALTER TABLE users ADD COLUMN IF NOT EXISTS deactivated_at timestamptz;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_seen_at timestamptz;

-- Who did what, IDs only: never requirement text (core/db.py log_event). project_id is NULL for system-wide
-- events (an admin deactivating a user). actor_id has no foreign key: DEV_AUTH_BYPASS users are not in users.
CREATE TABLE IF NOT EXISTS activity_log (
  id text PRIMARY KEY,
  project_id text REFERENCES projects ON DELETE CASCADE,
  actor_id text NOT NULL,
  action text NOT NULL,   -- member.invited, role.changed, statement.edited, comment.created, ...
  target text,            -- e.g. R-004 - rev 3, or a user id
  detail text,            -- JSON of IDs and small values
  created_at timestamptz NOT NULL);
CREATE INDEX IF NOT EXISTS activity_log_project_idx ON activity_log (project_id, created_at DESC);
ALTER TABLE activity_log ENABLE ROW LEVEL SECURITY;
