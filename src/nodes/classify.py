"""
The classify node. One call, no loop, since classifying a ticket's
category has no natural "retry until correct" shape, there's no
programmatic check for whether a category label is right the way there
is for a refund amount or a doc ID. This node's real job isn't just
labeling, it's producing the exact signal the graph's edges route on.
"""

import re


def classify_ticket(client, ticket_text: str) -> str:
    """Returns exactly one of: billing, technical, complaint."""
    prompt = (
        f"Classify this support ticket into exactly one category: "
        f"billing, technical, or complaint.\n\n"
        f"billing: refunds, charges, payment issues\n"
        f"technical: how something works, troubleshooting, how-to questions\n"
        f"complaint: dissatisfaction with no clear billing or technical fix needed\n\n"
        f"Ticket: {ticket_text}\n\n"
        f"Reply with exactly one word: billing, technical, or complaint."
    )
    # max_tokens is generous even though the answer is one word, since
    # a thinking-capable model's reasoning tokens share this same
    # budget, confirmed directly as the cause of a real failure during
    # this project's own testing. A tight budget here risks the model
    # spending it all thinking and returning nothing at all.
    response = client.chat(prompt=prompt, temperature=0.0, max_tokens=50)
    match = re.search(r"billing|technical|complaint", response.text.lower())
    return match.group(0) if match else "complaint"  # unclear tickets default to human review, never a loop
