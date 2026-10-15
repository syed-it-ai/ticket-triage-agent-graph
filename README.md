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

## What you should be able to explain after running this

- The precise difference between a loop (self-correction inside one node) and a graph (the decision about which nodes run)
- Why some nodes get a loop and others structurally can't, tied to whether a real programmatic check exists
- A concrete example of a check that a schema alone would miss, and that only a real lookup against actual data catches
