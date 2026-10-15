"""
The technical loop node. A model answering a how-to question will
confidently reference a help-doc ID whether or not that ID actually
exists, the same plausible-but-wrong failure this project's Stage 3
schema-vs-semantic work demonstrated directly. The loop's check here
queries the real doc index, not the model's own claim that the ID is
valid.
"""

import re
from src.shared.mock_data_stores import HELP_DOC_INDEX


def propose_answer(client, ticket_text: str, feedback: str = "") -> dict:
    doc_list = "\n".join(f"{doc_id}: {title}" for doc_id, title in HELP_DOC_INDEX.items())
    feedback_block = f"\n\nYour previous attempt failed this check: {feedback}\nFix it." if feedback else ""
    prompt = (
        f"A customer asked this technical question: {ticket_text}\n\n"
        f"Available help docs:\n{doc_list}\n\n"
        f"Reply with exactly this format:\n"
        f"doc_id: <the ID of the single most relevant doc above>\n"
        f"answer: <one sentence answering the question>"
        f"{feedback_block}"
    )
    response = client.chat(prompt=prompt, temperature=0.2, max_tokens=300)
    doc_match = re.search(r"doc_id:\s*(\S+)", response.text)
    answer_match = re.search(r"answer:\s*(.+)", response.text)
    return {
        "doc_id": doc_match.group(1).strip() if doc_match else None,
        "answer": answer_match.group(1).strip() if answer_match else None,
    }


def check_answer(proposal: dict) -> tuple:
    """The real check: does the referenced doc ID actually exist in the
    real index, queried directly, never assumed from the model's claim."""
    doc_id = proposal.get("doc_id")
    if doc_id not in HELP_DOC_INDEX:
        return False, f"doc_id '{doc_id}' does not exist in the help-doc index, this ID was invented"
    if not proposal.get("answer"):
        return False, "no answer text was provided"
    return True, f"doc_id '{doc_id}' is real: '{HELP_DOC_INDEX[doc_id]}'"


def run_technical_loop(client, ticket_text: str, max_attempts: int = 3) -> dict:
    feedback = ""
    for attempt in range(1, max_attempts + 1):
        proposal = propose_answer(client, ticket_text, feedback)
        passed, reason = check_answer(proposal)
        if passed:
            return {"success": True, "attempts": attempt, "proposal": proposal, "reason": reason}
        feedback = reason
    return {"success": False, "attempts": max_attempts, "proposal": proposal, "reason": reason}
