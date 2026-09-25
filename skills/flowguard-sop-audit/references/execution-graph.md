# Execution graph

The graph is compiled from the published SOP, sorted by `sequence`. Each
adjacent pair creates a `required_before` edge. Provider events are sorted by
their video start time; unknown step codes are ignored by the alignment layer
and must be rejected before persistence.

The serialized trace contains one or more items per expected step with:

```json
{"expectedCode":"install_seal","observedCode":"install_seal","status":"MATCHED","reason":"按 SOP 顺序观察到"}
```

Status values are `MATCHED`, `MISSING`, `MISORDERED`, and `DUPLICATE`. The trace
is evidence for the final decision, not a replacement for the original video
hash or provider response.
