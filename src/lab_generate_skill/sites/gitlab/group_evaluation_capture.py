"""Complete concrete Group capture bindings over existing SiteCapture intents."""

from lab_generate_skill.domain.evaluation import EvaluationContract
from lab_generate_skill.domain.site_capture import SiteCaptureIntent
from lab_generate_skill.domain.site_resource import SiteResourceSpec
from lab_generate_skill.domain.trace import InteractionTrace
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.ports.lifecycle import OperationControl
from .evidence_schema import GitlabSiteCapture
from .evaluation_capture import native_capture_request
from .tasks.group_spec import GroupSpec
from .tasks.group_recovery import GroupObserved, GroupRecoverySnapshot
from .tasks.group_reads import GroupStateReads
from .tasks.group_capture import GroupCapturedFacts
from .tasks.group_request import task_input
from .tasks.group_snapshot_identity import same_snapshot


def group_native_capture(
    reads: GroupStateReads,
    pair: GitlabSiteCapture,
    contract: EvaluationContract,
    spec: GroupSpec,
    site: SiteResourceSpec,
    snapshot: GroupRecoverySnapshot,
    trace: InteractionTrace,
    snapshot_sha: str,
    control: OperationControl,
) -> tuple[SiteCaptureIntent, GroupCapturedFacts]:
    intent, result = native_capture_request(
        reads,
        pair,
        contract,
        site,
        trace,
        snapshot_sha,
        ("gitlab-group-creation", "1"),
        control,
    )
    task = intent.request.inspection
    if task_input(task) != spec:
        raise EvidenceIntegrityError("Group capture changed original private input")
    observed = GroupObserved.model_validate_json(result.private_result)
    if (
        observed.model_dump_json() != result.private_result
        or observed.request != task
        or observed.snapshot != snapshot
    ):
        raise EvidenceIntegrityError("Group capture lost original complete snapshot")
    same_snapshot(task, snapshot, task.snapshot_ref)
    if observed.native.context != snapshot.native_before.context:
        raise EvidenceIntegrityError("Group capture changed original native worker")
    return intent, reads.native(observed.native, task, control)
