-- 0003 Requirements-first workflow: which extraction nodes (actors, entities, ...) have run on the confirmed
-- requirements, as a JSON list. Reset whenever a requirement changes, so the next generation re-extracts.
ALTER TABLE projects ADD COLUMN IF NOT EXISTS extracted_nodes text NOT NULL DEFAULT '[]';
