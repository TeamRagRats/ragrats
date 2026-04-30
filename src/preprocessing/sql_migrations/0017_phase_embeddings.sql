CREATE TABLE IF NOT EXISTS phase_embeddings (
    voyage_key   TEXT    NOT NULL,
    phase_index  INTEGER NOT NULL,
    embedding    vector(2560) NOT NULL,
    model        TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (voyage_key, phase_index),
    FOREIGN KEY (voyage_key, phase_index)
        REFERENCES phase_summaries (voyage_key, phase_index) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS phase_embeddings_voyage_idx ON phase_embeddings (voyage_key);
