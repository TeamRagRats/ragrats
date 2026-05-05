"""
System prompt template and per-category instruction blocks.

build_system_prompt(category, vessel_name, voyage_key) assembles the full
system prompt for one LLM call. build_user_message(...) builds the user turn.
"""
from __future__ import annotations

_BASE_INTRO = """\
You are a shipping operations expert helping build a question-answer evaluation set.

You will be given a text chunk from a shipping operations system along with context \
about the voyage it belongs to. Decide if the chunk contains a specific, verifiable \
fact that matches the requested CATEGORY.

If yes, generate exactly ONE Q&A pair.\
"""

CATEGORY_BLOCKS: dict[str, str] = {
    "logistics_cargo": """\
CATEGORY: logistics_cargo
Focus on operational logistics and cargo facts:
- Port arrival/departure times (ATA, ATD, ETA, ETD)
- NOR tender, laytime commencement/completion
- Cargo type, quantity, stowage, loading/discharge rates
- Draft, deadweight, hold inspections, pre-loading surveys

GOOD examples:
- "When did African Juniper tender NOR at Itaqui?"
- "What was the drafted depth of Aphrodite M on arrival at Eramet terminal?"
- "How many metric tons of soya were loaded on Emil Selmer at Santos?"
- "At what time did Corio Bay complete discharge at Buenos Aires on 25 October 2024?"

BAD examples:
- "When did the vessel arrive?" — no vessel name
- "What cargo was loaded on the ship?" — "the ship" is generic
- "What time was NOR tendered?" — which vessel and port?\
""",

    "commercial_terms": """\
CATEGORY: commercial_terms
Focus on commercial and contractual facts:
- Freight rates, lump sum, per-tonne rates
- Demurrage and despatch rates and amounts
- Daily hire rates, survey fees, port costs
- Charter party terms, B/L details, CP dates
- Cost disputes or agreed settlements

GOOD examples:
- "What demurrage rate applies on the African Juniper v1 fixture?"
- "What daily rate did Weco Bulk agree to pay for Corio Bay's simultaneous vessel attendance?"
- "What is the freight rate per metric ton on the Emil Selmer HMT#3 charter party?"
- "What was the agreed lump sum for the Berge Yotei voyage to Cargill Ocean Transportation?"

BAD examples:
- "What is the freight rate?" — no vessel or voyage context
- "What did the charterer agree to pay?" — "the charterer" is ambiguous\
""",

    "incident_decision": """\
CATEGORY: incident_decision
Focus on problems, decisions, and instructions:
- Engine faults, mechanical issues, off-hire events
- Delays, weather holds, port congestion
- Damage to cargo, vessel, or terminal
- Voyage orders, owner/charterer instructions
- Confirmed decisions, approvals, resolutions of disputes

GOOD examples:
- "What engine fault prevented African Juniper from departing anchorage on 1 November 2025?"
- "What decision did Weco Bulk make regarding the cargo shortage claim on Grace voyage 1?"
- "Why was the loading at Santos suspended on the Appaloosa v2 voyage?"
- "What instruction did the operations team give regarding the NABSA authorization for African Teal?"

BAD examples:
- "What problem occurred?" — which vessel?
- "What did the owner decide?" — "the owner" is generic\
""",
}

_CRITICAL_RULES = """\
CRITICAL RULES:
1. The question MUST mention the vessel name or voyage key so it is unambiguous. \
Use the exact name/key provided in the header below.
2. NEVER use "the vessel", "the ship", "the cargo", "the port", "the charterer", \
"the owner", "according to", "the email", "the document", "the chunk", "the text", \
"mentioned in", "currently".
3. The answer must be directly extractable from the CHUNK — not from the voyage context.
4. The voyage context is provided only so you can write an unambiguous question.
5. If the chunk contains no fact matching the category, return {"has_qa": false}.

Respond with valid JSON only, no markdown fences:
{"has_qa": true, "question": "...", "answer": "...", "difficulty": "easy|medium|hard"}
or
{"has_qa": false}\
"""


def build_system_prompt(category: str) -> str:
    block = CATEGORY_BLOCKS[category]
    return f"{_BASE_INTRO}\n\n{block}\n\n{_CRITICAL_RULES}"


def build_user_message(
    voyage_key: str,
    vessel_name: str,
    source_type: str,
    voyage_summary: str,
    fixture_summary: str,
    chunk_text: str,
) -> str:
    ctx_parts: list[str] = []
    if voyage_summary:
        ctx_parts.append(f"VOYAGE CONTEXT (background only — do not quote):\n{voyage_summary[:1500]}")
    if fixture_summary:
        ctx_parts.append(f"FIXTURE CONTEXT:\n{fixture_summary[:800]}")
    ctx_block = "\n\n".join(ctx_parts)

    snippet = chunk_text.strip()[:3000]

    return (
        f"Voyage: {voyage_key}\n"
        f"Vessel: {vessel_name}\n"
        f"Source type: {source_type}\n"
        + (f"\n{ctx_block}\n" if ctx_block else "")
        + f"\nCHUNK (the answer must come from THIS):\n{snippet}"
    )
