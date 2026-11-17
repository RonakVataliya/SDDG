-- 0004 LLM usage (plan 1.3): the provider chosen for a job, the model behind each item and diagram, and one row
-- per LLM call (metadata only, never content) for NFR1 statistics, the admin page and the eval.
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS provider text;
ALTER TABLE items ADD COLUMN IF NOT EXISTS model_used text;
ALTER TABLE diagrams ADD COLUMN IF NOT EXISTS model_used text;
CREATE TABLE IF NOT EXISTS llm_calls (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  job_id text REFERENCES jobs ON DELETE CASCADE,       -- null for calls made inside a request (revisions)
  project_id text NOT NULL REFERENCES projects ON DELETE CASCADE,
  node text, provider text, model text,
  input_tokens int, output_tokens int, wait_ms int, duration_ms int, attempts int, rate_limited int,
  status text NOT NULL, mixed_models boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS llm_calls_created_idx ON llm_calls (created_at);
CREATE INDEX IF NOT EXISTS llm_calls_job_idx ON llm_calls (job_id);
ALTER TABLE llm_calls ENABLE ROW LEVEL SECURITY;
