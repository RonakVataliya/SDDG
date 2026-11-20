-- 0007 Diagram look (#38): the style chosen by the user, JSON (see core/styling.py). NULL = inherit from parent_id, else default.
-- Also in schema.sql; here so a database made from an older schema.sql gets it. Safe to run again.
ALTER TABLE diagrams ADD COLUMN IF NOT EXISTS style text;
