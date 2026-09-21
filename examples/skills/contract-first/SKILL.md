---
name: contract-first
description: Repair small Python functions by checking every part of the stated behavioral contract.
---

Translate the contract into a short checklist before editing. Include ordering,
empty inputs, invalid values, mutation and object identity whenever specified.
Choose an implementation that satisfies the whole checklist rather than only
the example that first exposed the bug.

Trace one boundary case and one ordinary case through the finished function.
Preserve the requested interface and produce the requested response format.
