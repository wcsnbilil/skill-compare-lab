---
name: compare-skills
description: Compare instruction-only coding skills on paired Python repair tasks with Skill Compare Lab, or interpret an existing comparison report.
---

Use the installed skill-compare command, or python -m skill_compare_lab from
this repository. Read --help for current arguments.

For a comparison, establish the candidate SKILL.md paths and model, keep the
same task set and execution settings across conditions, and use a new output
directory. The tool automatically includes a no-injected-skill baseline.
Use at least three repeats for an exploratory comparison; the order seed is
not a model determinism guarantee.

Use demo to explain the workflow without model calls. Demo fixtures are
scripted examples, so describe their results only as a pipeline demonstration.
Live runs send skill contents to the configured model and consume its usage.
Use Docker grading for generated code; local grading executes it on the host.

Read manifest.json alongside the report. Check the experiment completed and
inspect failed trials before interpreting average metrics. Report the task
set, model, repeats, raw counts, paired wins/losses, missing usage and errors.
Treat tiny samples as exploratory; a tie on these tasks does not establish
equivalence. Distinguish injected instruction effects from native skill
discovery or skills that require scripts, tools, or reference files.

When sharing findings, link the evidence and state limitations. Raw prompts,
model responses and logs may contain private skill text; review before publishing.
