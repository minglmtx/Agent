"""Synthetic full Shopping task/native effects; never source or website rights."""

import json
from pathlib import Path
from typing import Any, Literal
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.site_files import SiteFilesPlan
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.bootstrap.shopping_order_eta import load_order_eta_inputs
from lab_generate_skill.sites.shopping.instance import ShoppingInstance
from lab_generate_skill.sites.shopping.query_state import PROTECTED_TABLES
from lab_generate_skill.sites.shopping.query_programs import (
    CORE_FINGERPRINT,
    LOCAL_MAIL,
)
from lab_generate_skill.sites.shopping.snapshot_program import INVENTORY
from lab_generate_skill.sites.shopping.tasks.order_eta_native import SHOPPING_IMAGE_SHA
from lab_generate_skill.sites.shopping.tasks.order_eta_programs import (
    PROTECTION,
    RECORDED_ETA,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_state import (
    OrderEtaExecutionInput,
    SOURCE_HASHES,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_lifecycle import (
    OrderEtaLifecycle,
)
from shopping_services_fixtures import Commands, Group, plan
from test_shopping_instance import Files, Ports
from test_shopping_order_eta_inputs import FIXTURE, public_task, reference
from site_worker_fixtures import configuration, operation
from test_slurm_commands import guard
from lab_generate_skill.sites.shopping.snapshot import ShoppingInventory
from lab_generate_skill.sites.shopping.tasks.navigation_database_program import (
    DATABASE_CONTENTS,
)
from lab_generate_skill.sites.shopping.tasks.navigation_search_program import (
    SEARCH_CONTENTS,
)
from lab_generate_skill.sites.shopping.tasks.navigation_file_program import (
    FILE_CONTENTS,
)
from shopping_navigation_contents_replies import (
    database_reply,
    search_reply,
    file_reply,
)

COVERAGE = "Every row and column of explicit account/address/order/payment/cart/coupon/history/review tables. No ignored columns. Sessions, visitors, guest compare collection and authentication log are mutable runtime metadata and not claimed protected."


def protection(initialized: bool = False) -> dict[str, Any]:
    tables: dict[str, Any] = {
        name: {
            "rows": 2,
            "sha256": "a" * 64,
            "primary_key": ["id"],
            "columns": ["id"],
            "ignored_columns": [],
            "chunks": 1,
        }
        for name in sorted(PROTECTED_TABLES)
    }
    if initialized:
        tables["sales_order_status_history"]["rows"] = 3
        tables["sales_order_status_history"]["sha256"] = "b" * 64
    return {
        "version": "shopping-complete-native-query-full-rows-v1",
        "tables": tables,
        "coverage": COVERAGE,
        "statement_budget_seconds": 20,
    }


def native_fixture() -> dict[str, Any]:
    order = {
        "entity_id": "1",
        "customer_id": "2",
        "increment_id": "000000148",
        "status": "complete",
        "created_at": "2020-01-01 00:00:00",
    }
    note = {
        "entity_id": "3",
        "parent_id": "1",
        "status": "complete",
        "created_at": order["created_at"],
        "comment": "Recorded estimated delivery date: 2023-02-03",
        "is_customer_notified": "0",
        "is_visible_on_front": "1",
        "entity_name": "order",
    }
    return {
        "order_id": 1,
        "customer_id": 2,
        "order_number": "000000148",
        "date": "2023-02-03",
        "order": order,
        "history_note": note,
        "native_history_rows": [note],
        "initialized_native_visible_note": True,
        "fixture_version": "native-local-recorded-order-date-v1",
        "source_hashes": SOURCE_HASHES,
        "external_delivery": False,
    }


class QueryCommands(Commands):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.initialized = False
        self.native_fail: str | None = None
        self.changed_core = False
        self.changed_table: str | None = None
        self.contents_fault: str | None = None
        self.database_reads = 0
        self.search_reads = 0

    def run(self, argv: tuple[str, ...], control: OperationControl) -> bytes:
        if any(p in argv for p in (DATABASE_CONTENTS, SEARCH_CONTENTS, FILE_CONTENTS)):
            control.checkpoint()
            self.calls.append(argv)
            if DATABASE_CONTENTS in argv:
                self.database_reads += 1
                # Category-only proof now accounts for its full configured files;
                # ETA never enters this branch, retaining its original fixture.
                self.inventory = ShoppingInventory(
                    sha256="b" * 64, files=3, directories=1, bytes=3
                )
                if self.contents_fault == (
                    "before-database" if self.database_reads == 1 else "after-database"
                ):
                    raise OSError("isolated contents database failure")
                offset = argv.index(DATABASE_CONTENTS)
                endpoint, search_port, deadline = argv[offset + 1 :]
                assert deadline.isdecimal() and int(deadline) > 0
                return database_reply(
                    endpoint,
                    int(search_port),
                    different=self.contents_fault == "database-difference"
                    and self.database_reads > 1,
                )
            if SEARCH_CONTENTS in argv:
                self.search_reads += 1
                if self.contents_fault == (
                    "before-search" if self.search_reads == 1 else "after-search"
                ):
                    raise OSError("isolated contents search failure")
                return search_reply(
                    int(argv[-2]),
                    different=self.contents_fault == "search-difference"
                    and self.search_reads > 1,
                )
            if self.contents_fault == "files":
                raise OSError("isolated contents file failure")
            return file_reply(argv[-5], [int(x) for x in argv[-4:]])
        if any(
            p in argv for p in (PROTECTION, RECORDED_ETA, CORE_FINGERPRINT, LOCAL_MAIL)
        ):
            control.checkpoint()
            self.calls.append(argv)
            if PROTECTION in argv:
                value = protection(self.initialized)
                if self.changed_table:
                    # Intentional corruption for exact protected-scope tests.
                    value["tables"][self.changed_table]["sha256"] = "c" * 64
                return json.dumps(value).encode()
            if CORE_FINGERPRINT in argv:
                return ("d" if self.changed_core else "c").encode() * 64
            if LOCAL_MAIL in argv:
                return b'{"backend":"local_sendmail_capture_v1","messages":[],"external_delivery":false}'
            parameters = json.loads(argv[-1])
            if parameters["operation"] == "initialize":
                if self.initialized or self.native_fail == "before_initialize":
                    raise OSError("native initialization rejected")
                self.initialized = True
                if self.native_fail == "after_initialize":
                    raise TimeoutError("original initialization return unknown")
            assert self.initialized
            return json.dumps(native_fixture()).encode()
        if INVENTORY in argv and argv[-1] == "clear":
            self.initialized = False
            self.changed_core = False
            self.changed_table = None
        return super().run(argv, control)


def request(
    action: Literal["snapshot", "prepare", "inspect", "restore"] = "snapshot",
    operation_id: str = "eta-snapshot",
    snapshot_ref: EvidenceRef | None = None,
) -> SiteTaskRequest:
    raw = FIXTURE.read_bytes()
    data = OrderEtaExecutionInput(
        spec=load_order_eta_inputs(raw, reference(raw), public_task()).private_spec
    )
    op = operation(configuration()).model_copy(
        update={"operation_id": operation_id, "attempt_id": "attempt"}
    )
    return SiteTaskRequest(
        task=data.spec.task,
        binding_ref=reference(b"binding", content_schema="task-binding/1"),
        operation=op,
        action=action,
        snapshot_ref=snapshot_ref,
        private_input=data.model_dump_json(),
    )


def case(
    root: Path, *, declared_files: SiteFilesPlan | None = None
) -> tuple[OrderEtaLifecycle, QueryCommands, list[Group]]:
    root = root / "instance"
    if declared_files is None:
        files = plan(root)
        files = files.model_copy(
            update={
                "image": files.image.model_copy(update={"sha256": SHOPPING_IMAGE_SHA}),
            }
        )
    else:
        files = SiteFilesPlan.model_validate(declared_files)
        if files.node_root != str(root) or files.image.sha256 != SHOPPING_IMAGE_SHA:
            raise ValueError("Native fixture changed declared root or image")
    commands = QueryCommands(root)
    groups: list[Group] = []

    def factory(log_root: str, control: OperationControl) -> Group:
        group = Group(len(groups))
        groups.append(group)
        return group

    instance = ShoppingInstance(
        files, files=Files(), ports=Ports(), commands=commands, services=factory
    )
    instance.prepare(guard())
    instance.start(guard())
    return (
        OrderEtaLifecycle(instance, lambda c: "unit@example.invalid"),
        commands,
        groups,
    )
