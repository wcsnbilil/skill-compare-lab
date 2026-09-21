---
name: minimal-change
description: Repair a small Python bug with a focused change while preserving its public behavior.
---

Locate the faulty assumption and make the smallest coherent correction.
Retain behavior required by the contract, including edge cases. Avoid
unrelated refactors or new dependencies. Check that the change fixes the
reported behavior without mutating inputs unless the contract allows it.
