#!/usr/bin/env python3
"""Validate a FlowGuard audit JSON fixture without importing the API app."""

from __future__ import annotations

import json
import sys
from pathlib import Path


DECISIONS = {"PASS", "VIOLATION", "INSUFFICIENT_EVIDENCE"}
STATUSES = {"CONFIRMED", "MISSING", "MISORDERED", "UNCERTAIN", "SKIPPED"}


def validate(payload: dict) -> list[str]:
    errors: list[str] = []
    if payload.get("decision") not in DECISIONS:
        errors.append("decision must be PASS, VIOLATION, or INSUFFICIENT_EVIDENCE")
    findings = payload.get("findings")
    if not isinstance(findings, list) or not findings:
        errors.append("findings must be a non-empty list")
        return errors
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            errors.append(f"findings[{index}] must be an object")
            continue
        if not finding.get("stepCode") and not finding.get("step_code"):
            errors.append(f"findings[{index}] is missing stepCode")
        status = finding.get("evidenceStatus", finding.get("evidence_status"))
        if status not in STATUSES:
            errors.append(f"findings[{index}] has invalid evidenceStatus")
    return errors


def main() -> int:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    raw = source.read_text(encoding="utf-8") if source else sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        print(f"invalid JSON: {error}", file=sys.stderr)
        return 2
    errors = validate(payload)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("valid FlowGuard audit result")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
