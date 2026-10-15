"""
Covers every piece of this system that doesn't need a live model call:
the two real checks (billing, technical) and the graph's routing logic
itself, using scripted fake clients so the retry mechanism is verified
directly, not assumed.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.nodes.billing_loop import check_refund, propose_refund
from src.nodes.technical_loop import check_answer
from src.graph.ticket_graph import run_ticket_graph


class FakeResponse:
    def __init__(self, text):
        self.text = text


# --- billing check ---

def test_valid_refund_within_policy_and_order_amount_passes():
    passed, _ = check_refund({"order_id": "ORD-4471", "refund_amount": 49.99})
    assert passed is True


def test_nonexistent_order_id_fails():
    passed, reason = check_refund({"order_id": "ORD-0000", "refund_amount": 49.99})
    assert passed is False
    assert "does not exist" in reason


def test_amount_exceeding_policy_max_fails():
    passed, reason = check_refund({"order_id": "ORD-4471", "refund_amount": 9999.0})
    assert passed is False
    assert "exceeds the policy maximum" in reason


def test_amount_exceeding_actual_order_amount_fails():
    passed, reason = check_refund({"order_id": "ORD-1203", "refund_amount": 400.0})
    assert passed is False
    assert "exceeds the actual order amount" in reason


def test_propose_refund_looks_up_the_real_amount_never_guesses_it():
    # A second real issue found during testing: the model was being
    # asked to guess a dollar amount the ticket text never stated, and
    # this function's own rejection messages ended up naming the
    # correct amount, so a "retry" often just copied a leaked answer.
    # The fix: the model only extracts the order ID, the amount is a
    # real lookup, never something the model proposes at all.
    fake_client = type("C", (), {"chat": lambda self, prompt, **kw: FakeResponse('{"order_id": "ORD-4471"}')})()
    proposal = propose_refund(fake_client, "charged for ORD-4471, never received it")
    assert proposal["refund_amount"] == 49.99


def test_degenerate_tiny_refund_against_a_real_order_fails():
    # A real run proposed a $0.01 refund against a $49.99 order. It
    # passed every check that existed at the time: positive amount,
    # within the $500 policy, not exceeding the order's value. This
    # test locks in the fix so that regression can't happen silently.
    passed, reason = check_refund({"order_id": "ORD-4471", "refund_amount": 0.01})
    assert passed is False
    assert "suspiciously small" in reason


# --- technical check ---

def test_real_doc_id_passes():
    passed, _ = check_answer({"doc_id": "DOC-101", "answer": "Reset it from settings."})
    assert passed is True


def test_invented_doc_id_fails():
    passed, reason = check_answer({"doc_id": "DOC-999", "answer": "Made up answer."})
    assert passed is False
    assert "invented" in reason


# --- graph routing ---

def test_billing_ticket_routes_through_billing_loop():
    classify_client = type("C", (), {"chat": lambda self, prompt, **kw: FakeResponse("billing")})()
    loop_client = type("L", (), {"chat": lambda self, prompt, **kw: FakeResponse('{"order_id": "ORD-4471", "refund_amount": 49.99}')})()
    compose_client = type("P", (), {"chat": lambda self, prompt, **kw: FakeResponse("Refund processed.")})()
    result = run_ticket_graph(classify_client, loop_client, compose_client, "refund please")
    assert result["category"] == "billing"
    assert result["final_action"] == "resolved_by_loop"


def test_complaint_routes_to_escalation_with_no_loop_at_all():
    classify_client = type("C", (), {"chat": lambda self, prompt, **kw: FakeResponse("complaint")})()
    result = run_ticket_graph(classify_client, None, None, "I am unhappy")
    assert result["category"] == "complaint"
    assert result["final_action"] == "escalated_to_human_review"
    assert result["loop_result"] is None


def test_loop_genuinely_retries_and_feeds_the_real_failure_back():
    classify_client = type("C", (), {"chat": lambda self, prompt, **kw: FakeResponse("billing")})()

    class FlakyLoopClient:
        def __init__(self):
            self.calls = 0

        def chat(self, prompt, **kw):
            self.calls += 1
            if self.calls == 1:
                return FakeResponse('{"order_id": "ORD-0000", "refund_amount": 49.99}')
            assert "does not exist" in prompt  # the real failure reason must appear in the retry prompt
            return FakeResponse('{"order_id": "ORD-4471", "refund_amount": 49.99}')

    loop_client = FlakyLoopClient()
    compose_client = type("P", (), {"chat": lambda self, prompt, **kw: FakeResponse("Refund processed.")})()
    result = run_ticket_graph(classify_client, loop_client, compose_client, "refund please")
    assert result["loop_result"]["attempts"] == 2
    assert result["loop_result"]["success"] is True
    assert loop_client.calls == 2


def test_loop_gives_up_after_max_attempts_and_escalates():
    classify_client = type("C", (), {"chat": lambda self, prompt, **kw: FakeResponse("billing")})()
    always_invalid_client = type("L", (), {"chat": lambda self, prompt, **kw: FakeResponse('{"order_id": "ORD-0000", "refund_amount": 49.99}')})()
    compose_client = type("P", (), {"chat": lambda self, prompt, **kw: FakeResponse("should not be called")})()
    result = run_ticket_graph(classify_client, always_invalid_client, compose_client, "refund please")
    assert result["loop_result"]["success"] is False
    assert result["final_action"] == "escalated_after_loop_exhausted"
    assert "reply" not in result  # compose must never run on a failed loop
