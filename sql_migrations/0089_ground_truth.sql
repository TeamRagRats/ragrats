-- Ground truth: synthetic operator-style Q&A grounded in a single email
-- (body_cleaned) plus up to 3 of that email's attachments' structured_md.
-- Two emails per voyage_key, one question per category per email.
-- Categories follow the Know Your RAG (COLING 2025) taxonomy.

CREATE TABLE IF NOT EXISTS ground_truth (
    question_id    UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    question       TEXT         NOT NULL,
    category       TEXT         NOT NULL
                                CHECK (category IN (
                                    'fact_single', 'reasoning', 'summary', 'unanswerable'
                                )),
    answer         TEXT         NOT NULL,
    body_cleaned   TEXT,
    structured_md  TEXT,
    thread_id      UUID         NOT NULL,
    source_id      UUID         NOT NULL,
    voyage_key     TEXT         NOT NULL,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (source_id, category)
);

CREATE INDEX IF NOT EXISTS gt_voyage_idx   ON ground_truth (voyage_key);
CREATE INDEX IF NOT EXISTS gt_thread_idx   ON ground_truth (thread_id);
CREATE INDEX IF NOT EXISTS gt_category_idx ON ground_truth (category);
