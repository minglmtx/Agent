"""Owner-local progress/facts, not a second request or attempt ledger."""

from dataclasses import dataclass, field
from contextlib import contextmanager
from collections.abc import Iterator
import sys
import time
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.preparation import EnvironmentBaseline
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.task_preparation import SiteTaskPrepared
from lab_generate_skill.domain.task_site_acquisition import SiteTaskAcquired
from lab_generate_skill.domain.errors import OwnershipConflict


@dataclass
class TaskPreparationState:
    phase: str = "new"
    stage_timings: list[tuple[str, str, float]] = field(default_factory=list)
    references: list[EvidenceRef] = field(default_factory=list)
    acquired: SiteTaskAcquired | None = None
    acquired_ref: EvidenceRef | None = None
    snapshot_request: SiteTaskRequest | None = None
    snapshot_result: SiteTaskResult | None = None
    snapshot_request_ref: EvidenceRef | None = None
    snapshot_result_ref: EvidenceRef | None = None
    snapshot_ref: EvidenceRef | None = None
    environment_selection_ref: EvidenceRef | None = None
    environment_ref: EvidenceRef | None = None
    environment: EnvironmentBaseline | None = None
    prepare_request: SiteTaskRequest | None = None
    prepare_result: SiteTaskResult | None = None
    prepare_request_ref: EvidenceRef | None = None
    prepare_result_ref: EvidenceRef | None = None
    result: SiteTaskPrepared | None = None
    result_ref: EvidenceRef | None = None

    def original_acquired(self) -> SiteTaskAcquired:
        if self.acquired is None or self.acquired_ref is None:
            raise OwnershipConflict("Original acquired binding is not confirmed")
        return self.acquired

    @contextmanager
    def stage(self, label: str) -> Iterator[None]:
        """Local diagnostics only; neither logging nor clock errors mask work.

        Call sites supply fixed stage names, without task data/paths/credentials.
        Nested intervals are recorded as events and must not be added together.
        """

        def mark(event: str) -> None:
            try:
                now = time.monotonic()
                self.stage_timings.append((label, event, now))
                sys.stderr.write(f"TASK_PREPARATION_STAGE {label} {event} {now:.6f}\n")
                sys.stderr.flush()
            except Exception:
                pass

        mark("begin")
        try:
            yield
        except BaseException:
            mark("failed")
            raise
        else:
            mark("end")
