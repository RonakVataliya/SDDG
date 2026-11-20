-- 0011 invitations (FR24a): invite someone to a project by email; the invitee accepts in the app (the bell), or
-- through the invitation's link. There is no email service. Idempotent.
--
-- Two shared-contract columns are repeated here with IF NOT EXISTS so this file works whether or not the roles
-- (project_members.role) and admin (users.is_admin) migrations have run: whoever runs first adds the column.
ALTER TABLE project_members ADD COLUMN IF NOT EXISTS role text NOT NULL DEFAULT 'owner';  -- viewer | editor | owner
ALTER TABLE users ADD COLUMN IF NOT EXISTS is_admin boolean DEFAULT false;

CREATE TABLE IF NOT EXISTS invitations (
  id text PRIMARY KEY,
  project_id text NOT NULL REFERENCES projects ON DELETE CASCADE,
  email text NOT NULL,                         -- lowercased
  role text NOT NULL,                          -- viewer | editor | owner
  token text NOT NULL UNIQUE,                  -- secret in the invitation link
  invited_by text NOT NULL,
  expires_at timestamptz NOT NULL,             -- 7 days after it was sent
  accepted_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS invitations_project_idx ON invitations (project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS invitations_email_idx ON invitations (email);
-- One open invitation per person per project.
CREATE UNIQUE INDEX IF NOT EXISTS invitations_open_uq ON invitations (project_id, email)
  WHERE accepted_at IS NULL AND revoked_at IS NULL;
ALTER TABLE invitations ENABLE ROW LEVEL SECURITY;

-- The bell shows an invitation once: the unique index stops two requests from adding it twice.
CREATE UNIQUE INDEX IF NOT EXISTS notifications_invitation_uq ON notifications (user_id, ((payload::jsonb)->>'invitation_id'))
  WHERE type = 'invitation';
