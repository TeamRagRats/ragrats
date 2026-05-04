-- Add password_hash column to users table (if not already present from initial schema).
-- The developer user's password is set via seed_password.py after this migration runs.
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT;
