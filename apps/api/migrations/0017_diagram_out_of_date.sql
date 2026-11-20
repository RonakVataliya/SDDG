-- 0017 Out-of-date diagrams (FR17c): when a requirement a diagram draws was last edited. NULL = not out of date.
-- Also in schema.sql; here so a database made from an older schema.sql gets it. Safe to run again.
ALTER TABLE diagrams ADD COLUMN IF NOT EXISTS out_of_date_at timestamptz;
