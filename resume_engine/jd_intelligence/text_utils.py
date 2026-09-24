"""Small text helpers for deterministic JD parsers."""

from __future__ import annotations

import re


def compact(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def lines(text: str) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def sentence_window(text: str, pattern: str, *, flags: int = re.IGNORECASE) -> str | None:
    match = re.search(pattern, text or "", flags)
    if not match:
        return None
    start = max(0, match.start() - 100)
    end = min(len(text), match.end() + 140)
    chunk = (text or "")[start:end]
    pieces = re.split(r"(?<=[.!?])\s+", chunk)
    for piece in pieces:
        if re.search(pattern, piece, flags):
            return compact(piece)
    return compact(chunk)


def has_any(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        evidence = sentence_window(text, pattern)
        if evidence:
            return evidence
    return None


NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
}


def int_from_word_or_digits(value: str | None) -> int | None:
    if not value:
        return None
    raw = value.strip().lower()
    if raw.isdigit():
        return int(raw)
    return NUMBER_WORDS.get(raw)
