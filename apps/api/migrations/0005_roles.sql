-- 0005 Roles (shared contract, FR24): every project member has exactly one role, read from here on every request.
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
