from __future__ import annotations

# Strips reply/forward prefixes (Re:, Fwd:, SV:, etc.) and lowercases a subject string
# so emails with the same topic can be matched regardless of prefix depth.
# Used by build_threads.py and assign_thread_ids.py.

import re

_PREFIX_RE = re.compile(r"^\s*(re|fw|fwd|sv|vs|tr|aw)\s*:\s*", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")


def normalize_subject(subject: str | None) -> str:
    if not subject:
        return ""
    s = subject
    while True:
        new = _PREFIX_RE.sub("", s)
        if new == s:
            break
        s = new
    s = _WS_RE.sub(" ", s).strip().lower()
    return s


if __name__ == "__main__":
    for s in ["Re: Fwd: Hello", "RE:RE: Foo", "Plain", "SV: Test"]:
        print(repr(s), "->", repr(normalize_subject(s)))
