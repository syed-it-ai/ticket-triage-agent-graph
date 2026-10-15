"""
The compose reply node. Runs only after a loop has already succeeded,
meaning the facts it's writing from (a verified order and refund
amount, or a verified real doc ID) are already checked. This node's
only job is tone and phrasing, never verification, that already happened.
"""


def compose_reply(client, category: str, loop_result: dict) -> str:
    proposal = loop_result["proposal"]
    if category == "billing":
        fact_summary = f"Refund of ${proposal['refund_amount']} approved for order {proposal['order_id']}."
    else:
        fact_summary = f"Pointing the customer to {proposal['doc_id']}: {proposal.get('answer', '')}"

    prompt = (
        f"Write a customer support reply based on these already-verified facts, "
        f"do not add any new facts: {fact_summary}\n\n"
        f"Hard limit: no more than 30 words total. Stop there even if the thought "
        f"feels incomplete, a short reply is required, not a thorough one."
    )
    # Raised again after a second real run still truncated mid-sentence
    # at 250 tokens ("please feel free to check"). The model was simply
    # writing a longer answer than the old prompt's "two sentences" was
    # actually constraining, so this also tightens the prompt itself
    # with a hard word limit, not just a bigger budget to write into.
    response = client.chat(prompt=prompt, temperature=0.4, max_tokens=400)
    return response.text.strip()
