"""
Runs three real tickets through the graph, one down each of the three
paths, so the full routing decision, not just one branch, is visible
in a single run. classify and compose run on Gemini. The loops run on
Groq, chosen deliberately since Groq's speed matters most on the node
that might call the model multiple times in a row.
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
from src.shared.llm_client import LLMClient
from src.graph.ticket_graph import run_ticket_graph

load_dotenv()

TEST_TICKETS = [
    "I was charged for order ORD-4471 but never received it, can I get a refund?",
    "How do I export my data to a CSV file?",
    "I've contacted support three times this month and nothing has improved. I'm extremely frustrated.",
]


def main() -> None:
    classify_client = LLMClient(provider="gemini")
    loop_client = LLMClient(provider="groq")
    compose_client = LLMClient(provider="gemini")

    for i, ticket in enumerate(TEST_TICKETS):
        print(f"{'='*70}")
        print(f"Ticket: {ticket}")

        try:
            result = run_ticket_graph(classify_client, loop_client, compose_client, ticket)
        except Exception as e:
            # A rate limit exhausting all retries on one ticket should
            # not take down the other two. Print what happened and move
            # on, the same way a real production system would log one
            # failed request without crashing the whole service.
            print(f"This ticket failed after all retries: {e}")
            print("Skipping to the next ticket.\n")
            continue

        print(f"Category (routed by the graph): {result['category']}")
        if result["loop_result"] is not None:
            lr = result["loop_result"]
            print(f"Loop attempts: {lr['attempts']}, success: {lr['success']}")
            print(f"Final check result: {lr['reason']}")
        print(f"Final action: {result['final_action']}")
        if "reply" in result:
            print(f"Reply: {result['reply']}")
        if "reason" in result and result["loop_result"] is None:
            print(f"Reason: {result['reason']}")
        print()

        # A small gap between tickets, specifically to avoid stacking
        # enough calls in a few seconds to trip a per-minute rate limit
        # in the first place, rather than only reacting after it fires.
        if i < len(TEST_TICKETS) - 1:
            time.sleep(5)


if __name__ == "__main__":
    main()
