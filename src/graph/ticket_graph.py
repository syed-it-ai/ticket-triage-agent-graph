"""
The graph itself. This is the piece that actually makes the decision
the rest of the system depends on: given what classify produced, which
node runs next. Billing and technical tickets each get a loop with its
own real check. A complaint gets no loop at all, by design, since
there's no programmatic check a loop could run against a feeling.

This is deliberately not a straight line. The branching here is the
entire point: a graph's job is picking which path runs, not just
passing data forward through a fixed sequence.
"""

from src.nodes.classify import classify_ticket
from src.nodes.billing_loop import run_billing_loop
from src.nodes.technical_loop import run_technical_loop
from src.nodes.escalate import escalate_to_human
from src.nodes.compose_reply import compose_reply


def run_ticket_graph(classify_client, loop_client, compose_client, ticket_text: str) -> dict:
    """
    Three different clients are accepted deliberately, not one. In the
    real build this lets classify and compose run on Gemini while the
    loop runs on Groq, proving a graph's nodes are genuinely swappable
    independent of each other, the same point this project's main
    roadmap makes about orchestrator-workers generally.
    """
    category = classify_ticket(classify_client, ticket_text)
    trace = {"ticket": ticket_text, "category": category}

    if category == "billing":
        loop_result = run_billing_loop(loop_client, ticket_text)
        trace["loop_result"] = loop_result
        if loop_result["success"]:
            trace["reply"] = compose_reply(compose_client, category, loop_result)
            trace["final_action"] = "resolved_by_loop"
        else:
            trace["final_action"] = "escalated_after_loop_exhausted"
        return trace

    if category == "technical":
        loop_result = run_technical_loop(loop_client, ticket_text)
        trace["loop_result"] = loop_result
        if loop_result["success"]:
            trace["reply"] = compose_reply(compose_client, category, loop_result)
            trace["final_action"] = "resolved_by_loop"
        else:
            trace["final_action"] = "escalated_after_loop_exhausted"
        return trace

    # category == "complaint", or classify's own fail-safe default
    escalation = escalate_to_human(ticket_text)
    trace["loop_result"] = None
    trace["final_action"] = escalation["action"]
    trace["reason"] = escalation["reason"]
    return trace
