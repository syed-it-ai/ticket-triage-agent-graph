# How this graph actually works

For the full, honest story of everything that went wrong building this against real APIs, and what each fix actually was, see [05_debugging_a_real_run.md](./05_debugging_a_real_run.md). It's arguably more valuable than the rest of this file.

## What the code proves, not just claims

A scripted test feeds the billing loop a fake order ID on its first attempt, confirms the loop's real check rejects it, confirms the actual rejection reason ("does not exist in the order database") gets fed back into the second attempt's prompt, and confirms the loop succeeds exactly on try two. A separate test confirms that when every attempt fails, the loop gives up after its attempt budget and `compose_reply` never runs at all, not even once, on an unverified result.

## The mental model this maps to directly

A **loop** is a node that can mark its own output pending and try again, because something inside that node can check correctness against real data: the order database, the help-doc index. A **graph** is the decision about which node runs at all. Classify never passes every ticket through the same pipeline, it looks at its own output and routes to one of three structurally different paths.

The deliberate asymmetry is the actual point. Billing and technical both get loops, because both have something real to check a proposal against. Complaint gets no loop, because a feeling has no database to verify it against, and forcing a retry loop onto a node with no real check would just be theater, a retry that can't tell success from failure.

## Where this reuses work already proven elsewhere

The billing loop's policy check is the same excessive-agency scoping idea: a refund past the limit never gets approved regardless of how it's phrased or how many times it's retried. The technical loop's doc-ID check is the same schema-vs-semantic distinction: a response can be perfectly formatted and still reference something that doesn't exist, and only a real lookup catches that.

## The one thing worth remembering

`compose_reply` is written to only ever see a loop result that already passed a real check. That's not a comment promising good behavior, it's a structural fact confirmed by a test: the code path from a failed loop straight to a customer-facing reply does not exist.
