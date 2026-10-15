"""
The billing loop node. This is where the actual loop lives: propose a
refund decision, check it against real policy and a real order
database, and if the check fails, feed the specific failure back in
and retry. Exits only when the check genuinely passes, never on a
"looks reasonable" judgment call.

This is the same excessive-agency scoping principle from this
project's safety stage, applied here as the loop's own exit condition
instead of a separate permission gate: a refund outside policy never
gets approved, no matter how many times the model retries.
"""

import json
import re
from src.shared.mock_data_stores import ORDER_DATABASE, REFUND_POLICY_MAX_AMOUNT


def propose_refund(client, ticket_text: str, feedback: str = "") -> dict:
    """
    Asks the model only to identify the order ID, a genuine extraction
    task the ticket text actually supports. The refund amount is never
    guessed by the model, it's looked up directly from the real order
    record once the ID is confirmed.

    This fixes a real issue found during testing: the earlier version
    asked the model to also guess a dollar amount with zero information
    in the ticket to base it on, since the ticket never states a price.
    Worse, check_refund's own rejection messages named the correct
    amount directly ("exceeds the actual order amount of 49.99"), which
    meant a "retry" was often just the model copying a number out of
    its own error message, not genuinely reasoning to the right answer.
    """
    feedback_block = f"\n\nYour previous attempt failed this check: {feedback}\nFix it." if feedback else ""
    prompt = (
        f"A customer sent this billing ticket: {ticket_text}\n\n"
        f"Reply with exactly this JSON shape, nothing else:\n"
        f'{{"order_id": "<the order ID mentioned, exactly as written>"}}'
        f"{feedback_block}"
    )
    response = client.chat(prompt=prompt, temperature=0.2, max_tokens=300)
    match = re.search(r"\{.*\}", response.text, re.DOTALL)
    if not match:
        return {"order_id": None, "refund_amount": None}
    try:
        extracted = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {"order_id": None, "refund_amount": None}

    order_id = extracted.get("order_id")
    # A real lookup, never a guess. If the order doesn't exist,
    # refund_amount stays None and check_refund's existing order_id
    # check catches it exactly the same way it always did.
    real_amount = ORDER_DATABASE.get(order_id, {}).get("amount")
    return {"order_id": order_id, "refund_amount": real_amount}


def check_refund(proposal: dict) -> tuple:
    """
    The real, programmatic check. Both conditions query the actual
    mock database and policy constant, never the model's own claim
    about whether its answer is correct.
    """
    order_id = proposal.get("order_id")
    amount = proposal.get("refund_amount")

    if order_id not in ORDER_DATABASE:
        return False, f"order_id '{order_id}' does not exist in the order database"
    if amount is None or amount <= 0:
        return False, f"refund_amount '{amount}' is not a valid positive number"
    if amount > REFUND_POLICY_MAX_AMOUNT:
        return False, f"refund_amount {amount} exceeds the policy maximum of {REFUND_POLICY_MAX_AMOUNT}"
    actual_order_amount = ORDER_DATABASE[order_id]["amount"]
    if amount > actual_order_amount:
        return False, f"refund_amount {amount} exceeds the actual order amount of {actual_order_amount}"
    # Caught in a real run: a $0.01 refund against a $49.99 order passed
    # every check above, schema-valid, policy-valid, not exceeding the
    # order amount, while being a practically nonsensical resolution.
    # The check wasn't actually checking the thing that mattered.
    if amount < actual_order_amount * 0.9:
        return False, (
            f"refund_amount {amount} is suspiciously small compared to the actual "
            f"order amount of {actual_order_amount}, this ticket implies a full refund"
        )
    return True, "within policy and matches the order record"


def run_billing_loop(client, ticket_text: str, max_attempts: int = 3) -> dict:
    feedback = ""
    for attempt in range(1, max_attempts + 1):
        proposal = propose_refund(client, ticket_text, feedback)
        passed, reason = check_refund(proposal)
        if passed:
            return {"success": True, "attempts": attempt, "proposal": proposal, "reason": reason}
        feedback = reason
    return {"success": False, "attempts": max_attempts, "proposal": proposal, "reason": reason}
