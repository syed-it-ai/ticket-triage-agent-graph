"""
The escalate node. Deliberately the simplest node in the whole graph,
no loop, no model call at all. A complaint has no programmatic check
for "is this response correct," there's no real database to verify a
feeling against, which is exactly why it doesn't get a loop. Forcing a
loop onto a node with no real check would just be theater, a retry
that can't actually tell success from failure.
"""


def escalate_to_human(ticket_text: str) -> dict:
    return {
        "success": True,
        "attempts": 0,
        "action": "escalated_to_human_review",
        "reason": "Complaints have no programmatic correctness check, routed directly to a person instead of a loop.",
    }
