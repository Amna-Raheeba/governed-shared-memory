"""Provenance-preserving tombstones with confidence decay.

When a record is superseded it is not deleted: it becomes a
*tombstone* — still queryable as history, carrying the id of the
record that replaced it, the reason it was replaced, and the time it
was replaced. An agent can therefore ask "what did we used to
believe, when did it change, and why?" — the question a plain
supersession link cannot answer, because it records neither the
reason nor the time.

A tombstone's confidence *decays* with age, because an old belief
should weigh less the longer it has been dead — but decay models
salience, not truth: a tombstone never becomes a current fact again,
and live queries (``list_active`` / ``search``) never return one.
Decay is a deterministic exponential with a 24-hour half-life by
default, so the same record evaluated at the same reference time
always gives the same number, and the decay curve is exactly
checkable at fixed time points.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .records import MemoryRecord

#: Default half-life for tombstone confidence decay: 24 hours.
DEFAULT_HALF_LIFE_SECONDS = 86400.0


def parse_iso(value: str) -> datetime:
    """Parse an ISO 8601 timestamp; naive values are read as UTC."""
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def now_iso() -> str:
    """Current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def decay_confidence(original: float, age_seconds: float,
                     half_life_seconds: float = DEFAULT_HALF_LIFE_SECONDS,
                     ) -> float:
    """Exponential half-life decay of a confidence value.

    ``original * 0.5 ** (age / half_life)`` — deterministic for fixed
    inputs. An age at or below zero means "just superseded": no decay
    yet, the original confidence is returned unchanged.
    """
    if not 0.0 <= original <= 1.0:
        raise ValueError("confidence must be in [0, 1]")
    if half_life_seconds <= 0:
        raise ValueError("half-life must be positive")
    if age_seconds <= 0:
        return original
    return original * 0.5 ** (age_seconds / half_life_seconds)


@dataclass
class Tombstone:
    """The preserved view of one superseded record.

    Built from a ``MemoryRecord`` whose status is ``"superseded"``.
    The record's text, writer and source are kept verbatim — a
    tombstone is history, not a summary — plus the three facts that
    make it answerable: what replaced it (``superseded_by``), when
    (``superseded_at``), and why (``supersession_reason``).
    """

    record_id: str
    text: str
    writer: str
    namespace: str
    source: str
    original_confidence: float
    superseded_by: str | None
    superseded_at: str | None  # ISO 8601 UTC; None for pre-0.2.0 rows
    supersession_reason: str | None  # None when no reason was recorded
    created_at: str

    def age_seconds(self, at: str | datetime | None = None) -> float | None:
        """Seconds since supersession at the reference time.

        ``None`` when the record has no recorded supersession time
        (rows written before v0.2.0): the age is unknown, so no decay
        is applied rather than a guessed one.
        """
        if self.superseded_at is None:
            return None
        ref = _as_datetime(at)
        return max(0.0, (ref - parse_iso(self.superseded_at)).total_seconds())

    def decayed_confidence(
        self, at: str | datetime | None = None,
        half_life_seconds: float = DEFAULT_HALF_LIFE_SECONDS,
    ) -> float:
        """Confidence at the reference time, decayed by age.

        Unknown supersession time (pre-0.2.0 rows) returns the
        original confidence unchanged — an honest "we do not know how
        old this is" rather than a decay from a guessed date.
        """
        age = self.age_seconds(at)
        if age is None:
            return self.original_confidence
        return decay_confidence(self.original_confidence, age,
                                half_life_seconds)

    def to_dict(self, at: str | datetime | None = None,
                half_life_seconds: float = DEFAULT_HALF_LIFE_SECONDS,
                ) -> dict:
        age = self.age_seconds(at)
        return {
            "record_id": self.record_id,
            "text": self.text,
            "writer": self.writer,
            "namespace": self.namespace,
            "source": self.source,
            "original_confidence": self.original_confidence,
            "decayed_confidence": round(
                self.decayed_confidence(at, half_life_seconds), 4),
            "age_seconds": age,
            "superseded_by": self.superseded_by,
            "superseded_at": self.superseded_at,
            "supersession_reason": self.supersession_reason,
            "created_at": self.created_at,
        }


def from_record(record: MemoryRecord) -> Tombstone:
    """Build the tombstone view of a superseded record."""
    if record.status != "superseded":
        raise ValueError(
            f"record {record.record_id} is {record.status!r}, not superseded")
    return Tombstone(
        record_id=record.record_id,
        text=record.text,
        writer=record.writer,
        namespace=record.namespace,
        source=record.source,
        original_confidence=record.confidence,
        superseded_by=record.superseded_by,
        superseded_at=record.superseded_at,
        supersession_reason=record.supersession_reason,
        created_at=record.created_at,
    )


def _as_datetime(at: str | datetime | None) -> datetime:
    if at is None:
        return datetime.now(timezone.utc)
    if isinstance(at, datetime):
        if at.tzinfo is None:
            return at.replace(tzinfo=timezone.utc)
        return at
    return parse_iso(at)
