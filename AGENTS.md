# Source publication development rules

Read [development notes](docs/DEVELOPMENT.md), [module boundaries](docs/FRAMEWORK_MODULES.md) and the relevant architecture contract before changing code.

- Keep domain/ports/policies independent of concrete adapters; compose implementations in bootstrap. Do not add cross-site imports or scripts-to-scripts imports.
- Run tests, imports, installation, models, websites and database work through Slurm. Login nodes are for source/documents, lightweight metadata and submission.
- Preserve original evidence, unknown outcomes, request budgets and resource identity. Never use software acceptance as current runtime authority or retry an unknown side effect.
- Test the changed path and affected consumers; reuse unchanged accepted evidence. Do not start production to validate documentation changes.
- Keep this repository source/document only. Do not commit private configuration, credentials, experimental logs, task data, databases, models or environments.
- Update documentation in place and check links. This publication contains no active production permissions, claims or deployment state.
