from __future__ import annotations

# Removes HTML tags and entities from a body. If the input has tag-like
# substrings, BeautifulSoup is used so block elements (<p>, <br>, <tr>, <li>)
# become real newlines instead of word-glued text. Then html.unescape catches
# any stray entities (&nbsp;, &amp;, &#39; …) that survived. Finally, runs of
# decorative separator characters on a line by themselves (---, ===, ***, ___)
# are dropped — they are noise that would otherwise confuse downstream cleaners.

import html
import re

from bs4 import BeautifulSoup

# Match real HTML-ish tags only. Requires the char after `<` to be a letter,
# `/`, or `!` so prose like "x < 3" or "<30 nautical miles" isn't mistaken for
# a tag and stripped.
_HTML_TAG_HINT = re.compile(r"<[A-Za-z/!][^>]{0,300}>")

# Whole-line separator runs (3+ of one decorative char). Spaces/tabs around
# them are tolerated. Newlines are NOT in the character class so this never
# eats real content lines.
_SEPARATOR_RUN = re.compile(r"^[ \t]*[-=*_]{3,}[ \t]*$", re.MULTILINE)

_BLOCK_TAGS = (
    "p", "div", "tr", "li", "ul", "ol",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "pre",
)


def strip_html(text: str) -> str:
    if not text:
        return text
    if _HTML_TAG_HINT.search(text):
        soup = BeautifulSoup(text, "html.parser")
        for br in soup.find_all("br"):
            br.replace_with("\n")
        # Block tags terminate a paragraph; emit a real blank line so
        # paragraph-level cleaners (strip_legal_notices) split correctly.
        for tag in soup.find_all(_BLOCK_TAGS):
            tag.insert_after("\n\n")
        text = soup.get_text()
    text = html.unescape(text)
    text = _SEPARATOR_RUN.sub("", text)
    return text


if __name__ == "__main__":
    sample = (
        "<p>Hello <b>Captain</b>,</p>"
        "<p>The vessel is <a href='x'>ready</a>.</p>"
        "&nbsp;&nbsp;&mdash; Emil"
        "\n----------\n"
        "Plain trailing text"
    )
    print(repr(strip_html(sample)))
