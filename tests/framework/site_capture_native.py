"""Exact original prepared fixture admission; never formal training authority."""

from datetime import datetime, timezone, timedelta
import hashlib
from typing import Any
from lab_generate_skill.domain.site_capture import SiteCaptureRequest, SiteCaptureIntent
from lab_generate_skill.domain.site_task import SiteTaskRequest, SiteTaskResult
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.adapters.sites.recorded_capture import RecordedSiteCapture
from lab_generate_skill.ports.site_handle import SiteHandle
from lab_generate_skill.sites.shopping_admin.product_catalog_contract import (
    ProductCatalogState,
)
from lab_generate_skill.sites.shopping_admin.tasks.product_recovery_contract import (
    ProductRecoverySnapshot,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_recovery import (
    OrderEtaRecoverySnapshot,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_state import OrderEtaState
from site_resource_fixtures import Case
from test_slurm_commands import guard


def capture_original(
    case: Case, site: SiteHandle, prepared: SiteTaskRequest, label: str
) -> dict[str, Any]:
    if case.spec.configuration.site_id == "reddit":
        from reddit_capture_native import capture_original as reddit_capture

        return reddit_capture(case, site, prepared, label)
    if case.spec.configuration.site_id == "gitlab":
        from gitlab_capture_native import capture_original as gitlab_capture

        return gitlab_capture(case, site, prepared, label)
    assert prepared.action == "prepare" and prepared.snapshot_ref is not None
    shopping = case.spec.configuration.site_id == "shopping"
    seconds = 180 if shopping else 30
    snapshot_type = OrderEtaRecoverySnapshot if shopping else ProductRecoverySnapshot
    snapshot = snapshot_type.model_validate_json(
        case.evidence.read(prepared.snapshot_ref, control=guard(10))
    )
    assert snapshot.request.binding_ref == prepared.binding_ref
    assert snapshot.request.task == prepared.task
    if isinstance(snapshot, OrderEtaRecoverySnapshot):
        assert snapshot.state.service.files == case.spec.configuration.files
    else:
        assert (
            snapshot.state.plan.service.layout.node_root
            == case.spec.configuration.files.node_root
        )
    inspection = prepared.model_copy(
        update={
            "action": "inspect",
            "operation": prepared.operation.model_copy(
                update={
                    "operation_id": "native-catalog-" + label,
                    "deadline": datetime.now(timezone.utc) + timedelta(seconds=seconds),
                }
            ),
        }
    )
    request = SiteCaptureRequest(
        inspection=inspection,
        collector_id="shopping-order-eta" if shopping else "admin-product-catalog",
        collector_version="1",
    )

    class Authority:
        def verify_capture(
            self,
            configuration: SiteWorkerConfiguration,
            req: SiteCaptureRequest,
            intent_ref: EvidenceRef,
            control: OperationControl,
        ) -> None:
            assert configuration == case.spec.configuration and req == request
            req.check_site(configuration)
            intent = SiteCaptureIntent.model_validate_json(
                case.evidence.read(intent_ref, control=control)
            )
            assert intent.request == request
            assert (
                intent.configuration_sha256
                == hashlib.sha256(configuration.model_dump_json().encode()).hexdigest()
            )
            assert prepared.snapshot_ref is not None
            assert (
                case.evidence.read(prepared.snapshot_ref, control=control)
                == snapshot.model_dump_json().encode()
            )
            read_op = case.op.model_copy(
                update={
                    "operation_id": "catalog-ledger-" + label,
                    "deadline": req.operation.deadline,
                }
            )
            assert case.journal.read(configuration.token, read_op).state == "acquired"
            control.checkpoint()

    recorder = RecordedSiteCapture(site.capture, case.evidence, Authority())
    result_ref = recorder.capture(request, control=guard(seconds))
    result = SiteTaskResult.model_validate_json(
        case.evidence.read(result_ref, control=guard(10))
    )
    assert result == recorder.result and result.request_sha256 == request.digest
    catalog: OrderEtaState | ProductCatalogState
    if shopping:
        catalog = OrderEtaState.model_validate_json(result.private_result)
        assert catalog.task == prepared.task
    else:
        catalog = ProductCatalogState.model_validate_json(result.private_result)
        assert catalog.product_id == 2041 and catalog.target_record_json is not None
        assert catalog.other_product_count == 2040
    assert recorder.intent_ref is not None
    return dict(
        request=request.model_dump(mode="json"),
        intent_ref=recorder.intent_ref.model_dump(mode="json"),
        result_ref=result_ref.model_dump(mode="json"),
        catalog=catalog.model_dump(mode="json"),
        engineering_only=True,
    )
