from __future__ import annotations

# Authentication router: login sets an httpOnly JWT cookie, logout clears it.

from datetime import datetime, timedelta, timezone

import psycopg
from fastapi import APIRouter, Depends, HTTPException, Response, status
from passlib.context import CryptContext
from jose import jwt
from pydantic import BaseModel

from deps import JWT_ALGORITHM, JWT_EXPIRE_HOURS, _JWT_SECRET, get_db, verify_token

router = APIRouter(prefix="/auth", tags=["auth"])

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

COOKIE_NAME = "ragrats_token"


class LoginRequest(BaseModel):
    username: str
    password: str


def _create_jwt(username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    return jwt.encode(
        {"sub": username, "exp": expire},
        _JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


@router.post("/login")
def login(body: LoginRequest, response: Response, conn: psycopg.Connection = Depends(get_db)):
    row = conn.execute(
        "SELECT password_hash FROM users WHERE username = %s",
        (body.username,),
    ).fetchone()

    if row is None or row[0] is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    password_hash: str = row[0]
    if not _pwd_context.verify(body.password, password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    token = _create_jwt(body.username)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        max_age=JWT_EXPIRE_HOURS * 3600,
        path="/",
    )
    return {"username": body.username}


@router.post("/logout")
def logout(response: Response, _username: str = Depends(verify_token)):
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"ok": True}
