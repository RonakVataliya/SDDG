-- 0006 Revisions (shared contract, FR24f edit conflict check): every save of a requirement, item or diagram version
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
