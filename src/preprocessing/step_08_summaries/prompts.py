from __future__ import annotations

import json

# ---------------------------------------------------------------------------
# System prompts (verbatim from RagRats_V0/system prompts/summaries/)
# ---------------------------------------------------------------------------

EMAIL_SUMMARY_SYSTEM = """You are a shipping industry analyst. Your task is to write a concise summary
of a single email and its attachments from a bulk shipping operation.

Focus only on facts relevant to the voyage: cargo type and quantity, port names,
dates (laycan, ETA, ETD), freight rates, counterparty names, operational issues,
and any decisions or instructions. Ignore pleasantries and boilerplate.

Create 2-8 sentences in plain English. Do not use bullet points."""

FIXTURE_SUMMARY_SYSTEM = """You are a shipping industry analyst. Your task is to summarise a fixture record
from a bulk shipping voyage into a short paragraph.

Include: vessel name, trade route (load port -> discharge port), cargo type and
quantity, freight rate, laytime terms, and any notable clauses. Write 3-5
sentences in plain English."""

PHASE_SUMMARY_SYSTEM = """You are a shipping industry analyst. You will receive a chronologically ordered
batch of email and attachment summaries covering part of a single voyage.
Each entry is tagged (INCOMING) or (OUTGOING), indicating whether the email was
received by the operator or sent by them. Use this direction to describe who
did what: INCOMING = a counterparty contacted us; OUTGOING = we communicated
to a counterparty.

Write a detailed phase summary (aim for roughly 1500-2000 tokens) in plain
English covering what happened in this slice of the voyage: operational
decisions, counterparty communications, cargo particulars, port calls, dates,
freight and commercial terms, operational issues, and any notable context.
Reference specific dates when describing events. Preserve chronological order.
Do not use bullet points. Do not speculate about events outside the given
slice; this is one phase of a larger voyage and later phases will cover
subsequent events.

If any mistakes, errors, disputes, claims, incidents, or unforeseen events
occurred in this slice (e.g. stevedore damage, off-hire, delays, cargo claims,
berthing issues, weather problems, charterparty breaches), mention them inline
with the relevant date. The final voyage narrative will aggregate these across
all phases."""

VOYAGE_SUMMARY_SYSTEM = """You are a shipping industry analyst writing an internal voyage report.

You will receive a fixture summary followed by a sequence of phase summaries
that together cover a complete voyage. Each phase summary was generated from
a slice of the email thread and already aggregates many emails. Your job is
NOT to retell each phase — your job is to INTEGRATE the phases into a single
coherent narrative of the whole voyage. Treat the phase summaries as source
material, not as sections you have to reproduce.

Emails in the underlying thread were tagged (INCOMING) — a counterparty
contacted the operator — or (OUTGOING) — the operator communicated to a
counterparty. Use this direction to describe who did what when it matters.

Hard rules:
- Do NOT structure the output phase by phase. Do NOT write headings like
  "Phase 1", "Phase 2", etc. Do NOT walk through the phases sequentially
  just because they appear in the input.
- Organise the narrative by the voyage lifecycle:
  pre-fixture and negotiation -> loading phase -> voyage -> discharge ->
  post-voyage issues. Dates drive the order, not the phase boundaries.
- Consolidate repeated or overlapping information: if several phases
  describe the same event (ETA updates, counterparty exchanges, weather
  delays), report the event once, with the relevant dates, and move on.
- Preserve specific facts: counterparty names, vessel movements, ports,
  cargo particulars, laycan/ETA/ETB/ETS, freight terms, demurrage/despatch,
  and any operational decisions. Drop pleasantries and duplicate ETAs.
- Plain English prose. No bullet points in the main narrative. Reference
  specific dates when describing events.

Length: aim for a detailed but focused narrative — roughly 2500-4000 tokens.
Prefer a tight, integrated story over an exhaustive enumeration. If you
find yourself reproducing a phase summary, stop and synthesise instead.

If any mistakes, errors, disputes, claims, incidents, or unforeseen events
occurred during the voyage (e.g. stevedore damage, off-hire, delays, cargo
claims, berthing issues, weather problems, charterparty breaches), add a
separate section at the end titled "Issues and Unforeseen Events" that lists
and briefly explains each incident with the relevant date. If no such
events occurred, omit this section entirely."""


# ---------------------------------------------------------------------------
# User prompt builders
# ---------------------------------------------------------------------------

def build_email_summary_prompt(
    direction: str,
    date: str,
    body: str,
    attachments: list[dict],
) -> str:
    attach_block = ""
    if attachments:
        lines = []
        for att in attachments:
            lines.append(f"--- Attachment: {att['filename']} ---")
            lines.append((att.get("content") or "").strip())
        attach_block = "\n\n" + "\n".join(lines)

    return (
        f"Direction: {direction}\n"
        f"Date: {date}\n\n"
        f"Email body:\n{body.strip()}"
        f"{attach_block}\n\n"
        "Create a 2–8 sentence summary of this email."
    )


def build_fixture_summary_prompt(fixture_json: str | dict) -> str:
    if isinstance(fixture_json, dict):
        fixture_text = json.dumps(fixture_json, ensure_ascii=False, indent=2)
    else:
        fixture_text = str(fixture_json)

    return (
        f"Fixture data:\n{fixture_text}\n\n"
        "Write a 3–5 sentence summary of this fixture."
    )


def build_phase_summary_prompt(
    voyage_key: str,
    phase_range: str,
    email_summaries: list[dict],
) -> str:
    thread_lines = []
    for i, entry in enumerate(email_summaries, 1):
        status = entry.get("status", "")
        prefix = f"[{i}] {entry['date']}"
        if status:
            prefix += f" ({status})"
        thread_lines.append(f"{prefix}  {entry['summary']}")
    thread_section = "\n".join(thread_lines)

    return (
        f"Voyage: {voyage_key}\n"
        f"Phase: {phase_range}\n\n"
        f"Email thread slice ({len(email_summaries)} emails, chronological):\n"
        f"{thread_section}\n\n"
        "Write a detailed phase summary (~1500-2000 tokens)."
    )


def build_voyage_summary_from_phases_prompt(
    voyage_key: str,
    fixture_paragraph: str | None,
    phases: list[dict],
) -> str:
    fixture_section = (
        f"Fixture:\n{fixture_paragraph.strip()}\n"
        if fixture_paragraph
        else "Fixture: (no fixture data available)\n"
    )

    phase_lines = []
    for i, p in enumerate(phases, 1):
        date_range = ""
        if p.get("date_start") or p.get("date_end"):
            date_range = f" [{p.get('date_start','?')} - {p.get('date_end','?')}]"
        header = (
            f"=== Phase {i}/{len(phases)}: {p.get('phase_range','')}"
            f"{date_range} ({p.get('email_count', 0)} emails) ==="
        )
        phase_lines.append(header)
        phase_lines.append((p.get("summary") or "").strip())
        phase_lines.append("")
    phases_section = "\n".join(phase_lines)

    return (
        f"Voyage: {voyage_key}\n\n"
        f"{fixture_section}\n"
        f"Phase summaries ({len(phases)} phases, chronological):\n"
        f"{phases_section}\n\n"
        "Write a comprehensive voyage narrative that integrates all phases "
        "into a single coherent story."
    )
