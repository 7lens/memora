"""Report partial STE checks. Do not certify compliance."""

from __future__ import annotations

import json
import re
from pathlib import Path

from markdown_it import MarkdownIt

from .codec import MemoraError, load

# These alternatives form a partial aid. They do not replace the STE dictionary.
ALTERNATIVES = {
    "utilize": "use",
    "commence": "start",
    "initiate": "start",
    "leverage": "use",
    "aforementioned": "specified",
    "prior": "before",
    "subsequent": "after",
    "endeavor": "try",
    "whilst": "while",
    "approximately": None,
}


def glossary(root: Path):
    path = root / "docs" / "glossary.md"
    if not path.exists():
        return {}
    data, _ = load(path.read_text(encoding="utf-8"))
    terms = data.get("brain", {}).get("terms", {})
    for term, entry in terms.items():
        if not isinstance(entry, dict) or not all(
            entry.get(k) for k in ("definition", "subject", "use")
        ):
            raise MemoraError(
                f"The technical term needs a definition, subject, and use: {term}"
            )
    return terms


def prose(text: str):
    # Code and source quotations retain their original text.
    quoted = False
    values = []
    for token in MarkdownIt("default").parse(text):
        if token.type == "blockquote_open":
            quoted = True
        elif token.type == "blockquote_close":
            quoted = False
        elif token.type == "inline" and not quoted:
            values.append(
                "".join(
                    c.content if c.type == "text" else " "
                    for c in token.children or []
                    if c.type in {"text", "softbreak", "hardbreak"}
                )
            )
    return "\n".join(values)


def check(
    text: str,
    root: Path,
    procedure: bool = False,
    dictionary: Path | None = None,
    standard: Path | None = None,
) -> dict:
    terms = glossary(root)
    approved = set()
    complete = False
    if dictionary:
        try:
            obj = json.loads(dictionary.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise MemoraError("The local dictionary cannot be read.") from exc
        if obj.get("issue") != 9 or not isinstance(obj.get("words"), dict):
            raise MemoraError("Use an Issue 9 dictionary with a words mapping.")
        approved = {word.lower() for word in obj["words"]}
        complete = bool(obj.get("complete", False))
    value = prose(text)
    issues = []
    limit = 20 if procedure else 25
    for number, sentence in enumerate(re.split(r"(?<=[.!?])\s+|\n+", value), 1):
        words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", sentence)
        if len(words) > limit:
            issues.append(
                {
                    "rule": "sentence_length",
                    "sentence": number,
                    "message": f"The sentence has {len(words)} words. Use at most {limit}.",
                }
            )
        for word in words:
            lower = word.lower()
            if ALTERNATIVES.get(lower):
                issues.append(
                    {
                        "rule": "vocabulary",
                        "sentence": number,
                        "word": word,
                        "message": f"Use {ALTERNATIVES[lower]} instead of {word}.",
                    }
                )
        if re.search(
            r"\b(am|is|are|was|were|be|been)\s+(?:\w+ly\s+)?\w+(?:ed|en)\b",
            sentence,
            re.IGNORECASE,
        ):
            issues.append(
                {
                    "rule": "possible_passive",
                    "sentence": number,
                    "message": "Review the verb. Use the active voice in a procedure.",
                }
            )
        if re.search(r"\b\w+(?:n't|'re|'ve|'ll)\b", sentence):
            issues.append(
                {
                    "rule": "contraction",
                    "sentence": number,
                    "message": "Write the full words.",
                }
            )
    remainder = value.lower()
    for term in sorted(terms, key=len, reverse=True):
        remainder = re.sub(
            r"(?<!\w)" + re.escape(term.lower()) + r"(?!\w)", "", remainder
        )
    if dictionary:
        for word in sorted(set(re.findall(r"[a-z]+", remainder)) - approved):
            issues.append(
                {
                    "rule": "unlisted_word",
                    "word": word,
                    "message": "Review the word and its permitted use.",
                }
            )
    return {
        "standard": "ASD-STE100 Issue 9",
        "result": "needs_review",
        "coverage": "dictionary_supplied" if complete else "partial",
        "reference_available": bool(standard and standard.is_file()),
        "notice": "These checks do not certify STE compliance. Review word meaning and part of speech.",
        "issues": issues,
    }
