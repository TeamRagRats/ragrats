CREATE TABLE IF NOT EXISTS ground_truth_v2 (
    question_id         TEXT         PRIMARY KEY,
    question            TEXT         NOT NULL,
    ground_truth_answer TEXT         NOT NULL,
    category            TEXT         NOT NULL
                                     CHECK (category IN ('logistics_cargo', 'commercial_terms', 'incident_decision')),
    difficulty          TEXT         NOT NULL DEFAULT 'medium'
                                     CHECK (difficulty IN ('easy', 'medium', 'hard')),
    source_type         TEXT         NOT NULL,
    source_id           TEXT,
    source_chunk_id     UUID         NOT NULL REFERENCES chunks(chunk_id),
    voyage_key          TEXT         NOT NULL,
    vessel_name         TEXT         NOT NULL,
    generated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS gt2_voyage_key_idx ON ground_truth_v2(voyage_key);
CREATE INDEX IF NOT EXISTS gt2_category_idx   ON ground_truth_v2(category);
