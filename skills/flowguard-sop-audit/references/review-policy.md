# Review policy

Create one review request per uncertain required step. The request should point
to the narrowest available video interval, ask one concrete question, and carry
the reason (`occluded`, low confidence, missing timestamp, or incomplete
evidence). A reviewer can mark it `CONFIRMED` or `REJECTED`; the decision is
stored with actor, time, and optional note.

Never convert an unresolved `INSUFFICIENT_EVIDENCE` result into a release solely
because a model confidence number is high. The existing exception/rework flow
remains the gate for confirmed violations.
