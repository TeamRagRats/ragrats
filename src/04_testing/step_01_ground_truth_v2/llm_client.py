"""
vLLM client wrapper for ground truth generation.

make_client()   : returns (OpenAI, model_name)
generate_qa()   : one chunk -> dict | None (3-retry, JSON parsing, validation)
"""
from __future__ import annotations

import json
import sys
import time

from openai import OpenAI

from chunk_sampler import ChunkRow
from prompts import build_system_prompt, build_user_message
from validators import is_valid
from voyage_metadata import VoyageMeta


def make_client(base_url: str, model_override: str = "") -> tuple[OpenAI, str]:
    client = OpenAI(base_url=base_url, api_key="none")
    model = model_override or client.models.list().data[0].id
    print(f"Using model: {model} at {base_url}")
    return client, model


def generate_qa(
    client: OpenAI,
    model: str,
    meta: VoyageMeta,
    chunk: ChunkRow,
    category: str,
) -> dict | None:
    system_prompt = build_system_prompt(category)
    user_message = build_user_message(
        voyage_key=meta.voyage_key,
        vessel_name=meta.vessel_name,
        source_type=chunk.source_type,
        voyage_summary=meta.voyage_summary,
        fixture_summary=meta.fixture_summary,
        chunk_text=chunk.text,
    )

    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.2,
                max_tokens=400,
                extra_body={
                    "chat_template_kwargs": {"enable_thinking": False},
                    "repetition_penalty": 1.15,
                },
                timeout=60,
            )
            raw = (response.choices[0].message.content or "").strip()

            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.rsplit("```", 1)[0]

            result = json.loads(raw)

            if not result.get("has_qa"):
                return None

            question = (result.get("question") or "").strip()
            answer = (result.get("answer") or "").strip()
            difficulty = result.get("difficulty", "medium")

            if not is_valid(question, answer, meta.vessel_name, meta.voyage_key):
                return None

            return {
                "chunk_id": chunk.chunk_id,
                "source_type": chunk.source_type,
                "source_id": chunk.source_id,
                "voyage_key": chunk.voyage_key,
                "vessel_name": meta.vessel_name,
                "category": category,
                "question": question,
                "answer": answer,
                "difficulty": difficulty,
            }

        except json.JSONDecodeError:
            pass
        except Exception as exc:
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
            else:
                print(f"  [warn] chunk {chunk.chunk_id}: {exc}", file=sys.stderr)

    return None
