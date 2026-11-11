"""Exact declared fixture, no target prefill, measured initialization and failures."""

import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.bootstrap.admin_product_seed import load_admin_product_seed
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.sites.shopping_admin.tasks.product_seed import (
    AdminProductSeed,
    ProductStateReplyError,
)
from lab_generate_skill.sites.shopping_admin.tasks.product_seed_contract import (
    ProductSeed,
    ProductState,
)
from lab_generate_skill.ports.lifecycle import OperationControl
from test_admin_description_inputs import FIXTURE, reference, load
from test_admin_services import spec
from test_slurm_commands import guard

SEED_FILE = Path(__file__).parent / "fixtures/admin-description-seed.json"


def seed(raw: bytes | None = None) -> ProductSeed:
    raw = SEED_FILE.read_bytes() if raw is None else raw
    return load_admin_product_seed(
        raw, reference(raw, content_schema="admin-product-fixture/1")
    )


def record(**updates: Any) -> ProductState:
    values: dict[str, Any] = dict(
        product_id=2041,
        store_id=0,
        sku="TRAIN-sony-headphones",
        name="Sony Headphones",
        price="29.990000",
        qty="0",
        weight="0.000000",
        tax_class_id=2,
        tax_class_label="Taxable Goods",
        visibility=1,
        status=1,
        is_in_stock=False,
        website_ids=(1,),
        category_ids=(),
        url_key="gobrowse-pilot-sony-headphones",
        type_id="simple",
        short_description=None,
        description=None,
    )
    values.update(updates)
    return ProductState(**values)


class Commands:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.reply = record().model_dump_json().encode()
        self.error: BaseException | None = None

    def run(self, argv: tuple[str, ...], control: OperationControl) -> bytes:
        control.checkpoint()
        self.calls.append(argv)
        if self.error:
            raise self.error
        return self.reply


def initializer(tmp_path: Path, commands: Commands) -> AdminProductSeed:
    return AdminProductSeed(
        spec(tmp_path), load(FIXTURE.read_bytes()).private_spec, seed(), commands
    )


def test_actual_fixture_is_private_and_does_not_seed_goal(tmp_path: Path) -> None:
    commands = Commands()
    worker = initializer(tmp_path, commands)
    assert worker.initialize(guard()) == record()
    payload = json.loads(commands.calls[0][-1])
    assert payload["values"]["extra_attributes"] == {}
    assert "description" not in payload["values"]
    assert worker.task.description not in commands.calls[0][-1]
    assert worker.seed.scenario.scope == "declared_training_derivative"
    with pytest.raises(RuntimeError):
        worker.initialize(guard())
    assert len(commands.calls) == 1
    commands.reply = (
        record(description="actual later value", price="25.00")
        .model_dump_json()
        .encode()
    )
    assert worker.inspect(guard()).description == "actual later value"
    assert json.loads(commands.calls[-1][-1]) == {
        "operation": "inspect",
        "product_id": 2041,
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", True),
        ("weight", False),
        ("is_in_stock", False),
        ("website_ids", [True]),
        ("website_ids", []),
        ("price", "NaN"),
        ("price", "-1.00"),
        ("price", "29.999"),
        ("qty", "1"),
        ("name", ""),
        ("sku", None),
        ("extra_attributes", {"description": "target"}),
    ],
)
def test_unsupported_initial_state_rejected(field: str, value: Any) -> None:
    raw = json.loads(SEED_FILE.read_bytes())
    raw["products"][0][field] = value
    with pytest.raises(ValueError):
        seed(json.dumps(raw).encode())


@pytest.mark.parametrize(
    "kind", ["empty", "duplicate", "source", "products", "unknown"]
)
def test_bad_fixture_document_rejected(kind: str) -> None:
    raw = json.loads(SEED_FILE.read_bytes())
    if kind == "empty":
        data = b""
    elif kind == "duplicate":
        data = SEED_FILE.read_bytes().replace(
            b'"scope":', b'"scope":"other","scope":', 1
        )
    else:
        if kind == "source":
            raw["source_task_id"] = "different"
        elif kind == "products":
            raw["products"] *= 2
        else:
            raw["extra"] = "unrecognized"
        data = json.dumps(raw).encode()
    expected_error = EvidenceIntegrityError if kind == "empty" else ValueError
    with pytest.raises(expected_error):
        seed(data)


def test_reference_bytes_and_visibility_checked() -> None:
    raw = SEED_FILE.read_bytes()
    for updates in (
        {"sha256": "a" * 64},
        {"size_bytes": 1},
        {"visibility": "public"},
        {"content_schema": "other/1"},
    ):
        expected_error = (
            EvidenceIntegrityError
            if "sha256" in updates or "size_bytes" in updates
            else ValueError
        )
        with pytest.raises(expected_error):
            load_admin_product_seed(
                raw,
                reference(
                    raw, **({"content_schema": "admin-product-fixture/1"} | updates)
                ),
            )


@pytest.mark.parametrize(
    "changes",
    [
        {"price": "30.00"},
        {"description": "already completed"},
        {"qty": "1"},
        {"sku": "other"},
        {"tax_class_label": "other"},
        {"website_ids": (1, 2)},
        {"category_ids": (4,)},
    ],
)
def test_wrong_measured_initial_state_retained_without_retry(
    tmp_path: Path, changes: dict[str, Any]
) -> None:
    commands = Commands()
    commands.reply = record(**changes).model_dump_json().encode()
    worker = initializer(tmp_path, commands)
    with pytest.raises(ValueError, match="initial fixture") as caught:
        worker.initialize(guard())
    assert getattr(caught.value, "product_state") == record(**changes)
    with pytest.raises(RuntimeError):
        worker.initialize(guard())
    assert len(commands.calls) == 1


@pytest.mark.parametrize(
    "reply", [b"", b"{}", b"null", b"[]", b'{"product_id":2041,"product_id":2042}']
)
def test_bad_native_reply_keeps_raw_and_cause(tmp_path: Path, reply: bytes) -> None:
    commands = Commands()
    commands.reply = reply
    with pytest.raises(ProductStateReplyError) as caught:
        initializer(tmp_path, commands).initialize(guard())
    assert caught.value.raw_reply == reply and caught.value.__cause__ is not None


def test_unknown_write_preserves_original_failure_and_read_only_exit(
    tmp_path: Path,
) -> None:
    commands = Commands()
    worker = initializer(tmp_path, commands)
    original = ExceptionGroup(
        "write and cleanup", [OSError("write"), RuntimeError("cleanup")]
    )
    commands.error = original
    with pytest.raises(ExceptionGroup) as caught:
        worker.initialize(guard())
    assert caught.value is original
    with pytest.raises(RuntimeError):
        worker.initialize(guard())
    commands.error = None
    assert worker.inspect(guard()) == record()
    assert len(commands.calls) == 2


def test_python_immutable_website_scope_and_json_roundtrip() -> None:
    original = seed()
    values = original.scenario.products[0].model_dump()
    from lab_generate_skill.sites.shopping_admin.tasks.product_seed_contract import (
        ProductSeedValues,
    )

    assert ProductSeedValues.model_validate(values) == original.scenario.products[0]
    assert ProductSeed.model_validate_json(original.model_dump_json()) == original
    values["website_ids"] = [1]
    with pytest.raises(ValueError):
        ProductSeedValues.model_validate(values)


def test_cancel_before_initialization_does_not_commit_attempt(tmp_path: Path) -> None:
    commands = Commands()
    worker = initializer(tmp_path, commands)
    error = RuntimeError("cancel before side effects")

    class Stop:
        def checkpoint(self) -> float:
            raise error

        def wait(self, seconds: float) -> None:
            raise AssertionError("unused")

    with pytest.raises(RuntimeError) as caught:
        worker.initialize(Stop())
    assert caught.value is error and not worker.attempted and commands.calls == []


def test_fixture_size_boundary(tmp_path: Path) -> None:
    original = SEED_FILE.read_bytes()
    maximum = original + b" " * (64 * 1024 - len(original))
    assert seed(maximum).scenario == seed().scenario
    with pytest.raises(EvidenceIntegrityError):
        seed(maximum + b" ")


@pytest.mark.parametrize(
    "field,value",
    [
        ("store_id", 1),
        ("product_name", "Other Headphones"),
        ("source_task_id", "another-source"),
    ],
)
def test_task_fixture_scope_mismatch_rejected_before_native_call(
    tmp_path: Path, field: str, value: Any
) -> None:
    from lab_generate_skill.sites.shopping_admin.tasks.product_description_spec import (
        ProductDescriptionSpec,
    )

    values = load(FIXTURE.read_bytes()).private_spec.model_dump()
    if field == "source_task_id":
        values["task"]["source_task_id"] = value
    else:
        values[field] = value
    task = ProductDescriptionSpec.model_validate(values)
    commands = Commands()
    with pytest.raises(ValueError, match="Fixture scope"):
        AdminProductSeed(spec(tmp_path), task, seed(), commands)
    assert commands.calls == []


@pytest.mark.parametrize("raw", [None, {}, "{}", bytearray(b"{}")])
def test_wrong_raw_fixture_type_rejected(raw: Any) -> None:
    original = SEED_FILE.read_bytes()
    with pytest.raises(EvidenceIntegrityError):
        load_admin_product_seed(
            raw, reference(original, content_schema="admin-product-fixture/1")
        )


def test_wrong_native_product_id_retained_without_changing_target(
    tmp_path: Path,
) -> None:
    commands = Commands()
    commands.reply = record(product_id=2042).model_dump_json().encode()
    worker = initializer(tmp_path, commands)
    with pytest.raises(ProductStateReplyError) as caught:
        worker.initialize(guard())
    assert caught.value.raw_reply == commands.reply and worker.task.product_id == 2041
    assert json.loads(commands.calls[0][-1])["product_id"] == 2041
    with pytest.raises(RuntimeError):
        worker.initialize(guard())
    assert len(commands.calls) == 1
