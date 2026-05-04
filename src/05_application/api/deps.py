from __future__ import annotations

# FastAPI dependency providers: DB connection + JWT auth via httpOnly cookie.

import logging
import os
import secrets
import sys
from pathlib import Path
from typing import Generator

import psycopg
from dotenv import load_dotenv
from fastapi import Cookie, HTTPException, Request, status
from jose import JWTError, jwt

# ---------------------------------------------------------------------------
# Bootstrap: ensure repo root (and thus core/, clients/, src/) are importable
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[3]  # src/05_application/api/ → repo root
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

load_dotenv(_REPO_ROOT / ".env")

# ---------------------------------------------------------------------------
# JWT configuration
# ---------------------------------------------------------------------------
_JWT_SECRET = os.environ.get("JWT_SECRET")
if not _JWT_SECRET:
    _JWT_SECRET = secrets.token_hex(32)
    logging.warning(
        "JWT_SECRET not set in .env — using a random secret. "
        "All sessions will be invalidated on server restart. "
        "Set JWT_SECRET in .env for persistent sessions."
    )

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 8

# ---------------------------------------------------------------------------
# Database dependency
# ---------------------------------------------------------------------------

def get_db() -> Generator[psycopg.Connection, None, None]:
    """Yield a psycopg3 connection from DATABASE_URL in .env."""
    database_url = os.environ["DATABASE_URL"]
    with psycopg.connect(database_url) as conn:
        yield conn


# ---------------------------------------------------------------------------
# Auth dependency
# ---------------------------------------------------------------------------

def verify_token(request: Request) -> str:
    """
    Reads the JWT from the httpOnly cookie 'ragrats_token'.
    Returns the username (sub claim) if valid, raises 401 otherwise.
    """
    token: str | None = request.cookies.get("ragrats_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    try:
        payload = jwt.decode(token, _JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username: str | None = payload.get("sub")
        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )
        return username
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
