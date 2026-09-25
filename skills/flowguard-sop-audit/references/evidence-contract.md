# Evidence contract

Every finding should preserve:

- the SOP `step_code` and `sequence`;
- `detected`, model confidence, and a separate `evidence_score`;
- video `start_seconds`, `end_seconds`, and keyframe timestamps;
- a plain-language evidence explanation;
- `occluded` plus provider `chunk_idx` and `cv_boundary_score` when available.

For Step 5 frame analysis, persist each extracted JPEG in RustFS first. Send a
time-limited presigned object URL as the `image_url`; never inline frame bytes
as base64 in the model request. Keep object keys in the audit raw response so
the evidence can be traced after the URL expires.

The model's `overall_pass` field is advisory. The execution graph recomputes
the business decision so a malformed or overconfident provider response cannot
release a work order.
