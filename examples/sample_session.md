
# Sample session

Output of `python -m governed_shared_memory demo` (2026-11-16):

```
planner wrote mem-fc4d0c4975c9 (0 conflicts)
researcher wrote mem-d78fa04386a1 (1 conflicts)
  CONFLICT [slot]: conflicting date values over shared terms (project, deadline, january): ['20 january'] vs ['12 january']
  leak blocked: agent 'researcher' may not read namespace 'planner'
planner superseded mem-fc4d0c4975c9 with mem-d9d2c047b738
{
  "namespace": "shared",
  "active": 2,
  "superseded": 1,
  "open_conflicts": 0,
  "conflicted_records": 0,
  "unconflicted_active": 2
}
```

## Tombstone — the superseded record, 24 hours later

`mem.tombstones("admin", "shared")`, evaluated at
`2026-11-18T10:00:00+00:00` (24 hours after supersession, confidence
0.8 decayed to 0.4 on the 24-hour half-life):

```json
{
  "record_id": "mem-02bc088e46fb",
  "text": "project deadline is 12 January",
  "writer": "planner",
  "namespace": "shared",
  "source": "user",
  "original_confidence": 0.8,
  "decayed_confidence": 0.4,
  "age_seconds": 86400.0,
  "superseded_by": "mem-979417c1852a",
  "superseded_at": "2026-11-17T10:00:00+00:00",
  "supersession_reason": "user confirmed the later date",
  "created_at": "2026-11-17T10:42:55.965192+00:00"
}
```

The old deadline is still readable as history — with what replaced
it, when, and why — but a live search for "project deadline" returns
only the 20 January record.
