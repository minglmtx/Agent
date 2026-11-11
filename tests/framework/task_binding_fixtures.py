"""Real CAS bytes, explicitly synthetic baseline and task permissions."""

from dataclasses import dataclass
from pathlib import Path
from lab_generate_skill.bootstrap.admin_description import (
    load_product_description_inputs,
)
from lab_generate_skill.bootstrap.admin_description_records import (
    bind_product_description_records,
)
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.errors import OperationStopped, OwnershipConflict
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.task import PublicTask, TaskBinding
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.ports.task_bindings import TaskBindings
from evidence_control_fixtures import EvidenceFixtureStore
from test_admin_description_inputs import FIXTURE, public_task

BASELINE = b'{"kind":"unit baseline; not a website restore proof"}'


class TestControl:
    def __init__(self) -> None:
        self.stopped = False

    def checkpoint(self) -> float:
        if self.stopped:
            raise OperationStopped("TEST_STOP", "binding")
        return 30.0

    def wait(self, seconds: float) -> None:
        self.checkpoint()


class TestControls:
    def __init__(self) -> None:
        self.control = TestControl()
        self.operations: list[OperationContext] = []

    def bind(self, op: OperationContext) -> OperationControl:
        self.operations.append(op)
        return self.control


class RecordingStore(EvidenceFixtureStore):
    def __init__(self, path: Path, controls: TestControls) -> None:
        super().__init__(path)
        self.controls = controls
        self.read_controls: list[OperationControl | None] = []
        self.put_controls: list[OperationControl | None] = []
        self.puts = 0
        self.mode = "normal"
        self.last_ref: EvidenceRef | None = None
        self.original_error = ExceptionGroup(
            "unit commit/cleanup",
            [OSError("commit unknown"), RuntimeError("close failed")],
        )

    def read(
        self, reference: EvidenceRef, control: OperationControl | None = None
    ) -> bytes:
        self.read_controls.append(control)
        return super().read(reference, control)

    def put(
        self,
        data: bytes,
        metadata: EvidenceMetadata,
        control: OperationControl | None = None,
        *,
        exchange_id: str | None = None,
    ) -> EvidenceRef:
        self.puts += 1
        self.put_controls.append(control)
        if self.mode == "before_put":
            raise self.original_error
        ref = super().put(data, metadata, control, exchange_id=exchange_id)
        self.last_ref = ref
        if self.mode == "after_commit":
            raise self.original_error
        if self.mode == "after_return":
            self.controls.control.stopped = True
        if self.mode == "wrong_reference":
            return ref.model_copy(update={"sha256": "0" * 64})
        return ref


class UnitAuthority:
    def __init__(self, run_id: str = "run", owner_id: str = "owner") -> None:
        self.expected_owner = (run_id, owner_id)
        self.denied = False
        self.stop = False
        self.calls: list[OperationContext] = []

    def verify_binding(
        self,
        binding: TaskBinding,
        public_task: PublicTask,
        private_spec: bytes,
        baseline: bytes,
        op: OperationContext,
        control: OperationControl,
    ) -> None:
        self.calls.append(op)
        assert binding.identity == public_task.identity
        assert private_spec
        if (
            self.denied
            or (op.run_id, op.owner_id) != self.expected_owner
            or baseline != BASELINE
        ):
            raise OwnershipConflict("Unit task/baseline permission rejected")
        if self.stop:
            assert isinstance(control, TestControl)
            control.stopped = True


@dataclass
class Fixture:
    store: RecordingStore
    controls: TestControls
    authority: UnitAuthority
    records: TaskBindings
    binding: TaskBinding
    native: EvidenceRef

    def put(self, raw: bytes, schema: str, visibility: str = "private") -> EvidenceRef:
        return self.store.put(
            raw,
            EvidenceMetadata.model_validate(
                dict(
                    media_type="application/json",
                    content_schema=schema,
                    visibility=visibility,
                    producer="unit-binding-fixture",
                )
            ),
            self.controls.control,
        )


def fixture(path: Path) -> Fixture:
    controls = TestControls()
    store = RecordingStore(path, controls)
    authority = UnitAuthority()

    def put(raw: bytes, schema: str, visibility: str = "private") -> EvidenceRef:
        return store.put(
            raw,
            EvidenceMetadata.model_validate(
                dict(
                    media_type="application/json",
                    content_schema=schema,
                    visibility=visibility,
                    producer="unit-binding-fixture",
                )
            ),
            controls.control,
        )

    raw = FIXTURE.read_bytes()
    native = put(raw, "admin-native-contract/1")
    public = public_task()
    inputs = load_product_description_inputs(raw, native, public)
    binding = TaskBinding(
        identity=public.identity,
        registration_id="admin.product-description.v1",
        public_task_ref=put(
            public.model_dump_json().encode(), public.schema_version, "public"
        ),
        private_spec_ref=put(
            inputs.private_spec.model_dump_json().encode(),
            inputs.private_spec.schema_version,
        ),
        baseline_ref=put(BASELINE, "unit-admin-baseline/1"),
    )
    return Fixture(
        store,
        controls,
        authority,
        bind_product_description_records(store, controls, authority),
        binding,
        native,
    )
