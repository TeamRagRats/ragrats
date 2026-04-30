CREATE TABLE IF NOT EXISTS ground_truth (
    question_id        TEXT        PRIMARY KEY,
    question           TEXT        NOT NULL,
    ground_truth_answer TEXT       NOT NULL,
    difficulty         TEXT        NOT NULL DEFAULT 'medium'
                                   CHECK (difficulty IN ('easy', 'medium', 'hard')),
    source_email_id    UUID        REFERENCES emails(email_id) ON DELETE SET NULL,
    thread_id          UUID,
    voyage_key         TEXT        NOT NULL,
    voyage_path        TEXT,
    email_time         DATE,
    status             TEXT        NOT NULL DEFAULT 'pending'
                                   CHECK (status IN ('pending', 'approved', 'rejected')),
    generated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ground_truth_voyage_key_idx ON ground_truth(voyage_key);
CREATE INDEX IF NOT EXISTS ground_truth_status_idx     ON ground_truth(status);
