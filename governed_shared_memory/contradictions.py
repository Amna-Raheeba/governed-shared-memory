"""Contradiction detection on write.

Two detectors, both lexical heuristics — read this before trusting them:

1. **Polarity conflict** (adapted from the evidence-graph detector in
   ``multi-agent-research-assistant``): two active memories in the same
   namespace with opposing polarity (explicit negation vs positive
   outcome marker) over at least ``MIN_SHARED_TERMS`` shared content
   terms. Catches the blunt case — "saliency maps did not increase
   trust" vs "saliency maps increased trust" — and misses paraphrases.

2. **Slot conflict**: the same subject + attribute with a different
   value, e.g. "project deadline is 12 January" vs "project deadline
   is 20 January", or "the budget is $500" vs "the budget is $800".
   Detected by matching a small set of value patterns (dates,
   money, plain numbers) inside otherwise near-identical texts.
   This is the case that matters most for a *shared* memory: agents
   overwriting each other's facts. Slot conflicts are the strongest
   signal this module produces.

A conflict is a *flag*, never a block: the new memory is still stored,
the old one stays active, and both are listed under
:func:`consolidation.open_conflicts` until a human or a governed
supersession resolves them. Silently overwriting is exactly the
failure mode this library exists to prevent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .bm25 import tokenize
from .records import MemoryRecord

MIN_SHARED_TERMS = 3

NEGATION_PHRASES = {
    "did not", "does not", "do not", "didn't", "doesn't",
    "not measurably", "no measurable", "failed to", "turned off",
    "is not", "are not", "was not", "were not", "never",
}
NEGATION_TOKENS = {
    "never", "cannot", "ignored", "disagree", "disagreement",
    "failed", "fails", "without", "no", "not",
}
POSITIVE_MARKERS = {
    "improved", "improve", "improves", "increased", "increase", "increases",
    "helped", "helps", "valued", "rated", "useful", "effective", "better",
    "raised", "works", "working", "successful", "succeeded",
}
POLARITY_WORDS = NEGATION_TOKENS | POSITIVE_MARKERS | {
    "did", "does", "do", "alone",
}

# Value patterns for slot conflicts: dates, money, plain numbers.
DATE_RE = re.compile(
    r"\b\d{1,2}\s+(january|february|march|april|may|june|july|august|"
    r"september|october|november|december)\b|\b\d{4}-\d{2}-\d{2}\b",
    re.IGNORECASE,
)
MONEY_RE = re.compile(r"\$\s?\d[\d,]*(\.\d{2})?")
NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?\b")


@dataclass
class Conflict:
    """One flagged contradiction between two active memories."""

    kind: str  # "polarity" | "slot"
    record_a: str  # record_id
    record_b: str
    writer_a: str
    writer_b: str
    shared_terms: list[str]
    reason: str

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "record_a": self.record_a,
            "record_b": self.record_b,
            "writer_a": self.writer_a,
            "writer_b": self.writer_b,
            "shared_terms": self.shared_terms,
            "reason": self.reason,
        }


def _content_terms(text: str) -> list[str]:
    seen: list[str] = []
    for tok in tokenize(text):
        if tok in POLARITY_WORDS or len(tok) <= 2:
            continue
        if tok not in seen:
            seen.append(tok)
    return seen


def _raw_tokens(text: str) -> list[str]:
    """Tokens with nothing removed: polarity needs 'did not' / 'not',
    which the BM25 tokenizer drops as stopwords."""
    return re.findall(r"[a-z0-9']+", text.lower())


def _polarity(text: str) -> str:
    toks = _raw_tokens(text)
    joined = " " + " ".join(toks) + " "
    if any(f" {p} " in joined for p in NEGATION_PHRASES):
        return "negative"
    tok_set = set(toks)
    neg = bool(tok_set & NEGATION_TOKENS)
    pos = bool(tok_set & POSITIVE_MARKERS)
    if neg and not pos:
        return "negative"
    if pos and not neg:
        return "positive"
    return "neutral"


def _values(text: str) -> dict[str, set[str]]:
    """Extracted slot values by pattern kind."""
    return {
        "date": {m.group(0).lower() for m in DATE_RE.finditer(text)},
        "money": {m.group(0).lower() for m in MONEY_RE.finditer(text)},
        "number": {m.group(0) for m in NUMBER_RE.finditer(text)},
    }


def detect_pair(a: MemoryRecord, b: MemoryRecord) -> Conflict | None:
    """Detect a contradiction between two records, or None.

    Same-writer pairs are never flagged: one agent revising its own
    note is a correction, and it should use explicit supersession
    instead. Cross-writer pairs in the same namespace are checked.
    """
    if a.writer == b.writer:
        return None
    terms_a = _content_terms(a.text)
    terms_b = _content_terms(b.text)
    shared = [t for t in terms_a if t in set(terms_b)]
    # The differing value itself can never count as a shared term
    # ("$800" vs "$1200" share nothing), so slot conflicts need only
    # 2 shared non-numeric terms; polarity conflicts keep the bar at 3.
    shared_non_numeric = [t for t in shared if not t.isdigit()]
    if len(shared_non_numeric) < 2:
        return None

    # Slot conflict first: same subject, different concrete value.
    vals_a, vals_b = _values(a.text), _values(b.text)
    for kind in ("date", "money", "number"):
        if vals_a[kind] and vals_b[kind] and vals_a[kind] != vals_b[kind]:
            return Conflict(
                kind="slot",
                record_a=a.record_id, record_b=b.record_id,
                writer_a=a.writer, writer_b=b.writer,
                shared_terms=shared,
                reason=(
                    f"conflicting {kind} values over shared terms "
                    f"({', '.join(shared)}): {sorted(vals_a[kind])} vs "
                    f"{sorted(vals_b[kind])}"
                ),
            )

    # Polarity conflict: opposing direction over the same terms.
    if len(shared) < MIN_SHARED_TERMS:
        return None
    pol_a, pol_b = _polarity(a.text), _polarity(b.text)
    if {pol_a, pol_b} == {"positive", "negative"}:
        return Conflict(
            kind="polarity",
            record_a=a.record_id, record_b=b.record_id,
            writer_a=a.writer, writer_b=b.writer,
            shared_terms=shared,
            reason=(
                f"opposing polarity over shared terms ({', '.join(shared)}): "
                f"[{a.writer}] is {pol_a}, [{b.writer}] is {pol_b}"
            ),
        )
    return None


def detect_for_new(new: MemoryRecord,
                   existing: list[MemoryRecord]) -> list[Conflict]:
    """Conflicts between a new record and active records in its namespace."""
    return [
        c for rec in existing
        if rec.status == "active" and rec.record_id != new.record_id
        and (c := detect_pair(new, rec)) is not None
    ]


def detect_all(records: list[MemoryRecord]) -> list[Conflict]:
    """All pairwise conflicts among active records in one namespace."""
    active = [r for r in records if r.status == "active"]
    found: list[Conflict] = []
    for i in range(len(active)):
        for j in range(i + 1, len(active)):
            if (c := detect_pair(active[i], active[j])) is not None:
                found.append(c)
    return found
