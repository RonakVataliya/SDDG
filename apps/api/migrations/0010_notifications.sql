-- 0010 notifications (the bell): one row per notification for one user. Idempotent.
-- payload is JSON text holding IDs only (project_id, invitation_id, comment_id ...), never requirement text:
-- the bell looks names and wording up when it reads, so nothing user-written is stored here.
CREATE TABLE IF NOT EXISTS notifications (
  id text PRIMARY KEY,
  user_id text NOT NULL,
  type text NOT NULL,                          -- invitation | admin_invited | mention | ...
  payload text NOT NULL DEFAULT '{}',
  read_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  seq bigint GENERATED ALWAYS AS IDENTITY);
CREATE INDEX IF NOT EXISTS notifications_user_idx ON notifications (user_id, seq DESC);
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
