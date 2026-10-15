# Ticket triage: a graph that decides, with loops that self-correct

A support ticket router with a real branching decision and two real self-correcting loops, built to show exactly how loops and graphs fit together: a loop is a node that can retry itself against a real check, a graph is the decision about which node runs at all.

## What's actually in here

**The graph** (`src/graph/ticket_graph.py`) classifies a ticket, then routes to one of three structurally different paths. This is the actual decision point, not a fixed pipeline: a complaint never touches a loop at all.

**The billing loop** (`src/nodes/billing_loop.py`) proposes a refund, checks it against a real order database and a real policy limit, and retries with the specific failure fed back in until the check passes or the attempt budget runs out.

**The technical loop** (`src/nodes/technical_loop.py`) proposes an answer referencing a help-doc ID, checked against a real doc index. A model confidently inventing a doc ID that doesn't exist, a real and common failure mode, gets caught here directly.

**Escalate** (`src/nodes/escalate.py`) is deliberately the simplest node in the system: no loop, no model call. There's no programmatic check for a complaint, so no loop gets forced onto it.

**Compose reply** (`src/nodes/compose_reply.py`) only ever runs after a loop has already succeeded, confirmed by a test, not just a comment.

## Before you start

You need:
- Python 3.10 or newer
- A free Gemini key (aistudio.google.com, no card)
- A free Groq key (console.groq.com, no card). Default model: `openai/gpt-oss-120b`.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in both keys in `.env`.

## Running it

```bash
python src/main.py
```

Runs three real tickets, one down each path, so all three branches, including a loop actually retrying if one fires, are visible in a single run.

## Tests

```bash
pytest tests/
```

12 tests, fully offline, covering both loops' real checks, the graph's complete routing logic, and two real bugs found in live runs (a degenerate $0.01 refund, and the model guessing an amount it was never given enough information to know), each locked in with its own regression test so neither can silently come back.

## A note on how this was built

Every piece of logic that doesn't need a live model call (`check_refund`, `check_answer`, the graph's routing, the retry mechanism itself) was verified with scripted fake clients before this was considered done, the same discipline used throughout the project this builds on. The retry test specifically asserts the real failure reason appears in the second attempt's prompt, not just that a second attempt happened, since a loop that retries blindly without using the failure information isn't meaningfully different from no loop at all.

## What actually went wrong across real runs, and what each fix was

This section exists because the real debugging history here is more instructive than the original code, and it would be dishonest to bury it in commit messages nobody reads. Seven real issues, found by actually running this against live APIs, in the order they happened:

**1. A model had quietly retired.** The original default, `gemini-2.5-flash`, turned out to be retiring October 16, 2026, confirmed directly against Google's own deprecation schedule. Fixed by switching the default to `gemini-3.5-flash`, the current model at time of writing.

**2. Gemini's thinking silently ate the whole output budget.** `classify`'s `max_tokens=10` was enough for a one-word answer, except gemini-3.5-flash is a reasoning model, and its internal reasoning tokens come out of that same budget. The model spent all 10 tokens thinking and had nothing left to answer with, returning a response with no parseable text at all. Fixed by disabling thinking for simple calls (`thinkingConfig: {thinkingBudget: 0}`) and raising the budgets as a second layer of defense.

**3. The identical bug, on the other provider.** Groq's `openai/gpt-oss-120b` is also a reasoning model. The billing loop showed `order_id: None` on all 3 attempts, not because the model kept guessing wrong, but because it never produced parseable JSON at all, every attempt. Fixed with `reasoning_effort: "low"` plus higher token budgets.

**4. A real logic bug: a $0.01 refund passed every check.** Against a real $49.99 order, a one-cent refund proposal satisfied every rule that existed at the time: positive number, under the policy limit, not exceeding the order's value. The check was schema-valid and practically useless. Fixed by requiring the amount be within 90% of the order's real value, locked in with a permanent regression test.

**5. Rate limits needed a completely different response than server errors.** A `503` (temporary server hiccup) and a `429` (rate limit) are not the same problem. The original backoff used the same short waits for both, meaning every retry on a 429 still landed inside the same exhausted quota window. Fixed with a much longer, 429-specific backoff (30s, 60s, 90s, 120s) and a higher retry ceiling, plus making one ticket's exhausted retries no longer crash the entire run.

**6. The real API key was leaking into error messages.** Gemini puts the key directly in the request URL, and an unhandled error naturally prints that whole URL, key included. This showed up in real terminal output during testing. Fixed by redacting the key from every error message before it can reach a print statement, confirmed by a test that asserts the raw key never appears anywhere in the output.

**7. The most important one: the billing check was leaking its own answer.** The model was being asked to guess a refund amount the ticket text never stated, since "I never received my order" doesn't mention a price. When a wrong guess got rejected, the rejection message literally stated the correct amount ("exceeds the actual order amount of 49.99"), which the next attempt then simply copied. The loop wasn't testing whether the model could reason to the right answer, it was testing whether the model could read its own answer key. Fixed by having the model only extract the order ID, a task the ticket text actually supports, while the refund amount is looked up directly from the real order record, never guessed or proposed by the model at all.

The honest pattern across all seven: every one of them was caught by actually running the code against a real API and reading the output carefully, not by assuming the code worked because it was well-commented or because the logic looked right on paper.

## What you should be able to explain after running this

- The precise difference between a loop (self-correction inside one node) and a graph (the decision about which nodes run)
- Why some nodes get a loop and others structurally can't, tied to whether a real programmatic check exists
- A concrete example of a check that a schema alone would miss, and that only a real lookup against actual data catches
