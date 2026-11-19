-- 0006 System Design (Feature 4): one row per project and section kind (goals, decomposition, ...).
-- section_content holds {content, derived} as encrypted JSON (core/db.SECRET); derived is computed when written.
-- status: draft | confirmed (no row = empty). requirement_hash: HMAC of the cited requirements when last written.
CREATE TABLE IF NOT EXISTS design_sections (
  project_id text NOT NULL REFERENCES projects ON DELETE CASCADE,
  kind text NOT NULL,
  section_content text NOT NULL,
  status text NOT NULL,
  requirement_hash text NOT NULL,
  version integer NOT NULL,
  updated_at timestamptz NOT NULL,
  PRIMARY KEY (project_id, kind));

ALTER TABLE design_sections ENABLE ROW LEVEL SECURITY;
