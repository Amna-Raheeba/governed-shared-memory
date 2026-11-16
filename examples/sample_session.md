
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
