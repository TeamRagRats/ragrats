SHARED RULES (apply to every category)

You are generating one question for a maritime RAG evaluation set. The
question must be source-agnostic: it reads the same regardless of whether
the underlying material was an email, an attachment, a PDF, a certificate,
a weather map, or anything else.

MANDATORY — the question MUST explicitly name the vessel given in the
header above. Use the exact vessel name (e.g. "African Juniper", not
"Juniper" alone, not "the vessel", not a person's name from the chunk).
A question that does not contain the vessel name will be rejected. Person
names ("Gabriel", "Emil", "Sharon", etc.) are NEVER a substitute for the
vessel name — they refer to people, not ships.

NEVER include any of these words or phrases in the question (case-insensitive):
email, e-mail, mail, message, pdf, document, attachment, file, chunk, text,
notice, exchange, correspondence, "the email", "this email", "the document",
"this document", "the attachment", "this attachment", "the file", "the chunk",
"the message", "this message", "the notice", "this notice", "according to",
"as stated in", "as mentioned", "in the provided", "in this", "in the".

NEVER use demonstrative references to the source: "the vessel", "this vessel",
"the ship", "this ship", "the cargo", "the port", "the charterer", "the owner",
"the certificate", "this certificate", "the exchange", "this exchange".

DO ground the question in real-world entities given in the header:
- Always name the vessel explicitly (use the exact vessel name).
- Reference the voyage by its voyage_key when relevant.
- Name specific ports, dates, IMO numbers, certificate identifiers etc. by
  their actual values when they appear in the chunk.

OUTPUT FORMAT — respond with exactly one JSON object, no markdown fences,
no explanation, no array:
{
  "question": "...",
  "answer": "...",
  "source_hint": "..."
}

source_hint should describe what kind of information the answer comes from
(e.g. "vessel particulars", "stevedore damage report findings", "MLC
certificate validity period") — without quoting the answer or naming the
source medium.
