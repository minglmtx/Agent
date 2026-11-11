"""Browser-specific namespace over shared raw worker evidence recording."""

from lab_generate_skill.adapters.slurm.worker_evidence import WorkerStepEvidence

_records = WorkerStepEvidence("browser")
save = _records.save
retain_failure = _records.retain_failure
diagnostic_candidates = _records.diagnostic_candidates
