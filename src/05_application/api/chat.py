from __future__ import annotations

# Chat router: session management and streaming RAG responses.

import asyncio
import sys
from pathlib import Path
from typing import AsyncGenerator

import psycopg
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Path bootstrap — repo root must be on sys.path for pipeline imports.
# deps.py already does this, but we do it here too for safety.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[3]
_RETRIEVAL = _REPO_ROOT / "src" / "02_retrieval"
_GENERATION = _REPO_ROOT / "src" / "03_generation"
for _p in [str(_REPO_ROOT), str(_RETRIEVAL), str(_GENERATION)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from clients.embed_client import EmbedClient
from clients.llm_client import LLMClient
from core.db import connect as _core_connect

from step_01_voyage_key import find_winning_voyage_keys
from step_02_chunk_retrieval import retrieve_chunks, expand_chunks
from step_01_context_builder import build_context

from deps import get_db, verify_token

router = APIRouter(prefix="/chat", tags=["chat"])

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = (
    _REPO_ROOT / "system_prompts" / "generation" / "generation.md"
).read_text(encoding="utf-8").strip()

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class CreateSessionResponse(BaseModel):
    session_id: str


class MessageOut(BaseModel):
    message_id: str
    session_id: str
    role: str
    content: str
    created_at: str


class StreamRequest(BaseModel):
    message: str
    session_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_retrieval(query: str) -> str:
    """Run the full retrieval pipeline and return the built context string."""
    embed_client = EmbedClient()
    embedding = embed_client.embed([query])[0]

    with _core_connect() as conn:
        winning_keys, _ = find_winning_voyage_keys(conn, embedding, top_k=500)
        if not winning_keys:
            return ""
        chunks = retrieve_chunks(conn, embedding, voyage_keys=winning_keys, top_k=20)
        expanded = expand_chunks(conn, chunks, window=2)

    context = build_context([
        {
            "chunk_id": c.chunk_id,
            "voyage_key": c.voyage_key,
            "source_type": c.source_type,
            "source_id": c.source_id,
            "chunk_index": c.chunk_index,
            "similarity": c.similarity,
            "text": c.text,
        }
        for c in expanded
    ])
    return context


def _stream_llm(query: str, context: str) -> AsyncGenerator[str, None]:
    """
    Calls the LLM with stream=True using the openai client directly.
    Returns an async generator yielding SSE-formatted strings.
    """
    import queue
    import threading

    llm = LLMClient()

    user_prompt = (
        "Use the following retrieved context to answer the question.\n\n"
        f"CONTEXT:\n{context}\n\n"
        f"QUESTION:\n{query}"
    )

    token_queue: queue.Queue[str | None] = queue.Queue()

    def _stream_worker() -> None:
        try:
            stream = llm.client.chat.completions.create(
                model=llm.model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=2500,
                stream=True,
                extra_body={
                    "chat_template_kwargs": {"enable_thinking": False},
                    "repetition_penalty": 1.15,
                },
                timeout=120,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    token_queue.put(delta.content)
        except Exception as exc:
            token_queue.put(f"\n\n[Error: {exc}]")
        finally:
            token_queue.put(None)  # sentinel

    thread = threading.Thread(target=_stream_worker, daemon=True)
    thread.start()

    async def _gen() -> AsyncGenerator[str, None]:
        loop = asyncio.get_event_loop()
        while True:
            token = await loop.run_in_executor(None, token_queue.get)
            if token is None:
                break
            yield token
        thread.join(timeout=5)

    return _gen()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

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


@router.get("/sessions/{session_id}/messages", response_model=list[MessageOut])
def get_messages(
    session_id: str,
    conn: psycopg.Connection = Depends(get_db),
    username: str = Depends(verify_token),
):
    # Verify the session belongs to this user
    session_row = conn.execute(
        "SELECT username FROM query_sessions WHERE session_id = %s",
        (session_id,),
    ).fetchone()
    if session_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session_row[0] != username:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    rows = conn.execute(
        """
        SELECT message_id, session_id, role, content, created_at
        FROM session_messages
        WHERE session_id = %s
        ORDER BY created_at ASC
        """,
        (session_id,),
    ).fetchall()

    return [
        {
            "message_id": str(row[0]),
            "session_id": str(row[1]),
            "role": row[2],
            "content": row[3],
            "created_at": row[4].isoformat(),
        }
        for row in rows
    ]


@router.post("/stream")
async def stream_chat(
    body: StreamRequest,
    username: str = Depends(verify_token),
):
    # Validate session belongs to user (use a fresh connection)
    with _core_connect() as validation_conn:
        session_row = validation_conn.execute(
            "SELECT username FROM query_sessions WHERE session_id = %s",
            (body.session_id,),
        ).fetchone()
    if session_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if session_row[0] != username:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    async def event_generator() -> AsyncGenerator[str, None]:
        full_answer_parts: list[str] = []

        # Run retrieval in a thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        try:
            context = await loop.run_in_executor(None, _run_retrieval, body.message)
        except Exception as exc:
            yield f"data: [Retrieval error: {exc}]\n\n"
            yield "data: [DONE]\n\n"
            return

        # Stream LLM tokens
        try:
            async for token in _stream_llm(body.message, context):
                full_answer_parts.append(token)
                # Escape newlines in SSE data field
                escaped = token.replace("\n", "\\n")
                yield f"data: {escaped}\n\n"
        except Exception as exc:
            yield f"data: [Generation error: {exc}]\n\n"
            yield "data: [DONE]\n\n"
            return

        full_answer = "".join(full_answer_parts)

        # Persist messages to the DB
        try:
            with _core_connect() as persist_conn:
                persist_conn.execute(
                    "INSERT INTO session_messages (session_id, role, content) VALUES (%s, %s, %s)",
                    (body.session_id, "user", body.message),
                )
                persist_conn.execute(
                    "INSERT INTO session_messages (session_id, role, content) VALUES (%s, %s, %s)",
                    (body.session_id, "assistant", full_answer),
                )
                persist_conn.commit()
        except Exception as exc:
            # Log but don't break the stream — answer was already sent
            import logging
            logging.getLogger("chat").error("Failed to persist messages: %s", exc)

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
