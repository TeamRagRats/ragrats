from __future__ import annotations

import sys
from pathlib import Path

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

_REPO_ROOT = Path(__file__).resolve().parents[3]
_RETRIEVAL = _REPO_ROOT / "src" / "02_retrieval"
_GENERATION = _REPO_ROOT / "src" / "03_generation"
for _p in [str(_REPO_ROOT), str(_RETRIEVAL), str(_GENERATION)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from run_generation import run_query
from deps import get_db, verify_token

router = APIRouter(prefix="/chat", tags=["chat"])


class CreateSessionResponse(BaseModel):
    session_id: str


class MessageRequest(BaseModel):
    message: str
    session_id: str
    multi_query: bool = False


class MessageResponse(BaseModel):
    answer: str
    query_id: str


class ReviewRequest(BaseModel):
    query_id: str
    is_correct: bool
    feedback: str | None


@router.post("/sessions", response_model=CreateSessionResponse)
def create_session(
    conn: psycopg.Connection = Depends(get_db),
    username: str = Depends(verify_token),
):
    row = conn.execute(
        "INSERT INTO query_sessions (username) VALUES (%s) RETURNING session_id",
        (username,),
    ).fetchone()
    conn.commit()
    return {"session_id": str(row[0])}


@router.post("/message", response_model=MessageResponse)
def send_message(
    body: MessageRequest,
    conn: psycopg.Connection = Depends(get_db),
    username: str = Depends(verify_token),
):
    session_row = conn.execute(
        "SELECT username FROM query_sessions WHERE session_id = %s",
        (body.session_id,),
    ).fetchone()
    if session_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session_row[0] != username:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    answer, query_id = run_query(
        body.message,
        username=username,
        source="application",
        session_id=body.session_id,
        multi_query=body.multi_query,
    )
    return {"answer": answer, "query_id": query_id}


@router.post("/review", status_code=201)
def submit_review(
    body: ReviewRequest,
    conn: psycopg.Connection = Depends(get_db),
    username: str = Depends(verify_token),
):
    row = conn.execute(
        "SELECT q.query_text, gl.answer "
        "FROM queries q LEFT JOIN generation_logging gl ON gl.query_id = q.query_id "
        "WHERE q.query_id = %s::uuid",
        (body.query_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Query not found")
    query_text, answer = row[0], row[1] or ""
    conn.execute(
        "INSERT INTO reviews (query_id, query_text, answer, username, is_correct, feedback) "
        "VALUES (%s::uuid, %s, %s, %s, %s, %s) "
        "ON CONFLICT (query_id) DO UPDATE SET "
        "query_text = EXCLUDED.query_text, "
        "answer = EXCLUDED.answer, "
        "is_correct = EXCLUDED.is_correct, "
        "feedback = EXCLUDED.feedback",
        (body.query_id, query_text, answer, username, body.is_correct, body.feedback),
    )
    conn.commit()
    return {"ok": True}
