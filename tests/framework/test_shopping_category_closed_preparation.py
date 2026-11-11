"""Original recorded producer to bounded readonly consumer after owner closure.

Run/claim/kernel, DOM and native services are explicit software premises. These
checks do not qualify a live source or replace its complete Reset/resource graph.
"""

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.plans.prepared_browser import read_operation
from lab_generate_skill.bootstrap.shopping_category_closed_preparation import (
    closed_category_preparations,
)
from lab_generate_skill.domain.errors import (
    EvidenceIntegrityError,
    OperationStopped,
    OwnershipConflict,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.shopping_navigation_browser_initialization import (
    ShoppingCategoryInitialization,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.sites.shopping.tasks.navigation_admission import task_input
from shopping_category_preparation_port_fixtures import producer
from shopping_prepared_family_fixtures import prepared_family_case
from test_shopping_category_navigation_input import originals as originals
from site_instance_fixtures import node_path as node_path


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "execute",
        "owner",
        "scope",
        "prepared",
        "native",
        "checks",
        "cancel",
        "missing-native",
        "private-bytes",
    ],
)
def test_actual_category_preparation_readonly_handoff_after_original_close(
    tmp_path: Path,
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    originals: Any,
    fault: str,
) -> None:
    saved: dict[str, Any] = {}
    observed: dict[str, Any] = {}

    def prepare(c: dict[str, Any]) -> dict[str, Any]:
        return producer(c, monkeypatch, "none", saved)

    def ready(c: dict[str, Any]) -> None:
        observed.update(c)

    prepared_family_case(
        tmp_path,
        node_path,
        monkeypatch,
        "none",
        category=(originals[0][0], originals[0][2]),
        prepare_with=prepare,
        on_ready=ready,
    )
    c, store = observed, observed["store"]
    site, browser = c["c"], c["browser_case"]
    end = site.op.cleanup(
        "category-closed-source-read", now=datetime.now(timezone.utc), seconds=30
    )
    assert site.journal.read(site.spec.token, end).state == "closed"
    browser_end = browser.op.cleanup(
        "category-closed-browser-read", now=datetime.now(timezone.utc), seconds=30
    )
    assert browser.journal.read(browser.spec.token, browser_end).state == "closed"
    assert [r.action for r in saved["requests"]] == ["snapshot", "prepare"]
    initial, spec = c["baseline_inputs"], browser.spec
    selected = spec.configuration.initialization
    assert isinstance(selected, ShoppingCategoryInitialization)
    if fault in ("owner", "scope"):
        scope = spec.configuration.spec.scope
        if fault == "owner":
            scope = scope.model_copy(
                update={
                    "owner": scope.owner.model_copy(
                        update={"owner_id": "another-owner"}
                    )
                }
            )
        else:
            scope = scope.model_copy(update={"attempt_id": "another-attempt"})
        # Reach the closed-source semantic gate with a schema-valid different
        # identity, rather than testing the upstream resource schema again.
        spec = type(spec).model_validate(
            spec.model_copy(
                update={
                    "token": spec.token.model_copy(
                        update={"owner": scope.owner, "attempt_id": scope.attempt_id}
                    ),
                    "configuration": spec.configuration.model_copy(
                        update={
                            "spec": spec.configuration.spec.model_copy(
                                update={"scope": scope}
                            )
                        }
                    ),
                }
            )
        )
    elif fault in ("prepared", "native"):
        selected = selected.model_copy(
            update=(
                {
                    "prepared_ref": selected.prepared_ref.model_copy(
                        update={"producer": "other"}
                    )
                }
                if fault == "prepared"
                else {"native_contract_sha256": "0" * 64}
            )
        )
        spec = spec.model_copy(
            update={
                "configuration": spec.configuration.model_copy(
                    update={"initialization": selected}
                )
            }
        )
    elif fault == "checks":
        old = initial.preparation.checks
        changed = old.model_copy(
            update={
                "checks": (
                    old.checks[0].model_copy(
                        update={"reason_code": "OTHER_MEASUREMENT"}
                    ),
                    *old.checks[1:],
                )
            }
        )
        initial = initial.model_copy(
            update={
                "preparation": initial.preparation.model_copy(
                    update={"checks": changed}
                )
            }
        )
    reads: Counter[EvidenceRef] = Counter()
    original_read = store.read
    private = c["binding"].private_spec_ref
    # Use the exact native full reference selected by the production request.
    native = task_input(c["prepare"]).spec.native_contract_ref

    def read(ref: EvidenceRef, control: OperationControl | None = None) -> bytes:
        reads[ref] += 1
        if fault == "missing-native" and ref == native:
            raise OSError("original category native dependency unavailable")
        raw: bytes = original_read(ref, control=control)
        return raw + b" " if fault == "private-bytes" and ref == private else raw

    def forbid_put(*args: Any, **kwargs: Any) -> EvidenceRef:
        raise AssertionError("readonly original preparation tried to publish")

    monkeypatch.setattr(store, "read", read)
    monkeypatch.setattr(store, "put", forbid_put)

    class Cancel:
        def checkpoint(self) -> float:
            raise OperationStopped("CANCELLED", "category-closed-source-read")

        def wait(self, seconds: float) -> None:
            self.checkpoint()

    if fault == "cancel":
        monkeypatch.setattr(site.controls, "bind", lambda op: Cancel())

    def consume() -> Any:
        records = closed_category_preparations(
            initial, site.spec, spec, store, site.controls
        )
        op = (
            c["prepare"].operation
            if fault == "execute"
            else read_operation(c["prepare"].operation, end)
        )
        return records.load(c["publication"], op)

    if fault == "none":
        assert consume() == c["prepared"]
        assert reads[private] == reads[native] == reads[c["prepare"].snapshot_ref] == 1
        assert consume() == c["prepared"]
        assert reads[private] == reads[native] == reads[c["prepare"].snapshot_ref] == 2
    else:
        expected = (
            OperationStopped
            if fault == "cancel"
            else (
                OSError
                if fault == "missing-native"
                else (
                    EvidenceIntegrityError
                    if fault == "private-bytes"
                    else OwnershipConflict
                )
            )
        )
        with pytest.raises(expected):
            consume()
        if fault in ("owner", "scope", "prepared", "cancel"):
            assert not reads
    assert [r.action for r in saved["requests"]] == ["snapshot", "prepare"]
