# Project execution rules

- Current priority: integrate all in-scope tasks into the new framework by compatibility group and complete target construction and SFT. First-batch delivery is a milestone, not the finish line. Reuse shared implementations; keep per-task outcomes and train/dev/test separation.
- Follow the user's current objective, scope and existing authorization; carry necessary work through to the agreed result without repeatedly asking to continue.
- Read `docs/DEVELOPMENT.md` once for environment constraints. Read module boundaries and architecture contracts only for the code or behavior being changed; do not load all historical documents.
- Use the current handoff and original result records for runtime facts. Historical examples and this published repository do not grant production permissions.
- State a concrete deliverable and its necessary checks once. Do not create extra approval, reporting or acceptance stages during routine progress.
- Perform authorized reversible edits and read-only investigation directly. Ask only for missing information that blocks work or actions outside existing authorization; continue independent work meanwhile.
- Validate the changed path and affected consumers. Reuse applicable accepted evidence; do not rerun checks solely because the agent, task, batch or directory changed.
- Expand diagnosis for an actual failure, conflicting evidence, stalled progress or a changed dependency. Allow at most two extra analysis rounds per event, then obtain evidence, make a testable change or park that branch. Rewording hypotheses does not reset the limit; new evidence or a substantive change can reopen diagnosis. Stop once required checks pass.
- When required checks pass, continue to the next authorized stage. Reserve full regression for an explicit delivery requirement or demonstrated broad impact.
- Batch compatible checks and ready tasks within actual resource limits. While jobs wait, do useful independent work; avoid repeated polling without new information.
- Preserve original evidence and data-split isolation. Do not replay unknown side effects, exceed authorized cost/resource limits, or overwrite running jobs' frozen inputs.
- Keep domain/ports/policies independent of adapters; compose in bootstrap. Do not add cross-site or scripts-to-scripts imports.
- Run tests, imports, installation, models, websites and database work through Slurm. Login nodes are for source/documents, lightweight metadata and submission.
- This repository contains source/documentation only: no credentials, private config, logs, task datasets, databases, models or environments.
- Update docs in place. Documentation-only edits need relevant format/link checks, not production runs.
- Maintain one existing task summary with outcome, evidence and next action; do not generate a new audit document for every step.
- Report completed work, checks and remaining concrete blockers. Stop expanding scope once the agreed deliverable is complete.

Operational details are lookup material: [targeted checks](docs/FRAMEWORK_CHECK_WORKFLOW.md#change-evidence-scope), [execution quick guide](docs/FRAMEWORK_CHECK_WORKFLOW.md#execution-defaults). Start-task template: [GOAL-PROMPT](docs/GOAL-PROMPT.zh-CN.md).
