-- T4: one row per checker-agent run (LangChain tool-calling agent), with its
-- full tool trace; the verdict is copied onto the contradiction it checked.
CREATE TABLE IF NOT EXISTS agent_runs (
    id SERIAL PRIMARY KEY,
    contradiction_id INT NOT NULL REFERENCES contradictions(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    trace JSONB NOT NULL DEFAULT '[]',   -- [{tool, args, result_preview}]
    verdict JSONB,                       -- the submitted Verdict
    tool_calls INT,
    tokens_in INT,
    tokens_out INT,
    latency_ms INT,
    stop_reason TEXT NOT NULL,           -- verdict | forced | error
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- A pair is checked once per (model, prompt version); failed runs may be retried.
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_run_pair_model_prompt
    ON agent_runs (contradiction_id, model, prompt_version)
    WHERE stop_reason <> 'error';

ALTER TABLE contradictions
    ADD COLUMN IF NOT EXISTS verdict VARCHAR(20),
    ADD COLUMN IF NOT EXISTS agent_confidence FLOAT,
    ADD COLUMN IF NOT EXISTS agent_run_id INT REFERENCES agent_runs(id) ON DELETE SET NULL;
