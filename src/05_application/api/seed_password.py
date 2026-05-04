#!/usr/bin/env python3
"""
One-time script to set a bcrypt password for the 'developer' user.

Run from the repo root:
    python src/05_application/api/seed_password.py

Or with a custom username / password:
    python src/05_application/api/seed_password.py --username alice --password s3cr3t
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure repo root is importable
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))

from passlib.context import CryptContext
from core.db import connect

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def main() -> None:
    p = argparse.ArgumentParser(description="Set bcrypt password for a RagRats user")
    p.add_argument("--username", default="developer", help="Username to update (default: developer)")
    p.add_argument("--password", default="developer", help="Plain-text password to hash and store")
    args = p.parse_args()

    hashed = _pwd_context.hash(args.password)

    with connect() as conn:
        result = conn.execute(
            "UPDATE users SET password_hash = %s WHERE username = %s",
            (hashed, args.username),
        )
        conn.commit()
        if result.rowcount == 0:
            # Insert user if they don't exist
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (%s, %s) ON CONFLICT (username) DO UPDATE SET password_hash = EXCLUDED.password_hash",
                (args.username, hashed),
            )
            conn.commit()
            print(f"Created user '{args.username}' with hashed password.")
        else:
            print(f"Updated password for user '{args.username}'.")


if __name__ == "__main__":
    main()
