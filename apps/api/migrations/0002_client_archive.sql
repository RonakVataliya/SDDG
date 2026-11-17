-- 0002 Stream 5 (FR3b, FR3e, FR20, FR21): the project's client and archive state. The client is stored on the
-- project (no client directory). archived_at marks an archived project, shown read-only and listed under Archived.
ALTER TABLE projects ADD COLUMN IF NOT EXISTS client_name text;     -- encrypted; Home groups projects by it
ALTER TABLE projects ADD COLUMN IF NOT EXISTS contact_email text;   -- lowercased
ALTER TABLE projects ADD COLUMN IF NOT EXISTS archived_at timestamptz;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS archived_by text;

-- Design packs and reviews were dropped from Stream 5. Removes them where an earlier PM build created them.
DROP TABLE IF EXISTS reviews, design_packs;
