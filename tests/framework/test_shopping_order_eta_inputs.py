"""Exact historical input, public/private boundary, no native effects or admission."""

import hashlib
import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.bootstrap.shopping_order_eta import load_order_eta_inputs
from lab_generate_skill.adapters.plans.native_input import MAX_NATIVE_BYTES
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.sites.shopping.tasks.order_eta_spec import OUTPUT_REQUIREMENTS
from lab_generate_skill.actor.prompting import prepare_actor
from lab_generate_skill.domain.actor_prompt import ActorPublicTurn
from lab_generate_skill.domain.observation import ResolvedObservation
from observation_fixtures import sample_observation
from test_actor_protocol import turn

FIXTURE = Path(__file__).parent / "fixtures/shopping-order-eta-native.json"


def reference(raw: bytes, **updates: Any) -> EvidenceRef:
    values: dict[str, Any] = dict(
        uri="cas:shopping-order-eta-native",
        sha256=hashlib.sha256(raw).hexdigest(),
        size_bytes=len(raw),
        media_type="application/json",
        content_schema="shopping-native-contract/1",
        visibility="private",
        producer="test",
    )
    values.update(updates)
    return EvidenceRef(**values)


def public_task(**updates: Any) -> PublicTask:
    native = json.loads(FIXTURE.read_bytes())
    values: dict[str, Any] = dict(
        identity=TaskIdentity(
            source_task_id=native["source_task_id"],
            task_id="shopping-order-eta-selected-v1",
            split="train",
            site="shopping",
            family="recorded_order_eta",
            contract_version=1,
        ),
        goal=native["goal"],
        start_url="http://127.0.0.1:18080/customer/account/",
        allowed_actions=("click", "fill", "send_msg_to_user"),
        output_requirements=OUTPUT_REQUIREMENTS,
    )
    values.update(updates)
    return PublicTask(**values)


def test_original_input_preserves_order_identifier_and_private_date() -> None:
    raw = FIXTURE.read_bytes()
    public = public_task()
    result = load_order_eta_inputs(raw, reference(raw), public)
    assert result.public_task == public
    assert (
        result.private_spec.order_number == "000000148"
        and result.private_spec.recorded_date == "2023-02-03"
    )
    assert result.private_spec.admission == "unverified"
    assert result.private_spec.native_contract_ref == reference(raw)


def test_private_date_never_enters_actual_public_actor_projection() -> None:
    native = json.loads(FIXTURE.read_bytes())
    public = public_task()
    texts = []
    for date in ("2023-02-03", "2024-02-29"):
        native["query"]["date"] = date
        raw = json.dumps(native).encode()
        result = load_order_eta_inputs(raw, reference(raw), public)
        original = turn()
        obs = sample_observation(public.identity)
        prompt = prepare_actor(
            ActorPublicTurn(
                task=result.public_task,
                skill=original.skill,
                observation=ResolvedObservation(record=obs, text=obs.text),
                history=(),
                memory=original.memory,
            )
        )
        texts.append(prompt.model_dump_json())
        assert date not in texts[-1] and "native_contract_ref" not in texts[-1]
        assert "000000148" in texts[-1] and "estimated_delivery_date" in texts[-1]
    assert texts[0] == texts[1]


@pytest.mark.parametrize(
    "case",
    [
        "numeric_order",
        "short_order",
        "long_order",
        "order_newline",
        "unicode_digits",
        "date_bool",
        "date_missing",
        "date_format",
        "impossible_date",
        "goal",
        "source",
        "lineage",
        "heldout",
        "training_flag",
        "external",
        "mail",
        "extra",
        "fields",
        "bool_count",
    ],
)
def test_invalid_native_inputs_rejected_before_effects(case: str) -> None:
    n = json.loads(FIXTURE.read_bytes())
    if case == "numeric_order":
        n["query"]["order_number"] = 148
    elif case == "short_order":
        n["query"]["order_number"] = "00000148"
    elif case == "long_order":
        n["query"]["order_number"] = "0000000148"
    elif case == "order_newline":
        n["query"]["order_number"] = "000000148\n"
    elif case == "unicode_digits":
        n["query"]["order_number"] = "００００００１４８"
    elif case == "date_bool":
        n["query"]["date"] = True
    elif case == "date_missing":
        del n["query"]["date"]
    elif case == "date_format":
        n["query"]["date"] = "2023-2-3"
    elif case == "impossible_date":
        n["query"]["date"] = "2023-02-29"
    elif case == "goal":
        n["goal"] = "changed"
    elif case == "source":
        n["source_task_id"] = "foreign"
    elif case == "lineage":
        n["task_id"] = "foreign--complete-native-training-v1"
    elif case == "heldout":
        n["heldout_quarantine"] = True
    elif case == "training_flag":
        n["eligible_for_training"] = True
    elif case == "external":
        n["initial_state_revision"]["external_delivery"] = True
    elif case == "mail":
        n["initial_state_revision"]["local_mail_capture"] = False
    elif case == "extra":
        n["query"]["execute"] = "caller-script"
    elif case == "fields":
        n["query"]["fields"] = {"estimated_delivery_date": "integer"}
    elif case == "bool_count":
        n["actor_attempts"] = False
    raw = json.dumps(n).encode()
    with pytest.raises(EvidenceIntegrityError):
        load_order_eta_inputs(raw, reference(raw), public_task())


@pytest.mark.parametrize(
    "change",
    [
        "goal",
        "remote",
        "port",
        "route",
        "query",
        "fragment",
        "family",
        "version",
        "split",
        "source",
        "terminal",
        "output",
    ],
)
def test_wrong_public_binding_or_incomplete_action_protocol_rejected(
    change: str,
) -> None:
    public = public_task()
    updates: dict[str, Any] = {}
    if change == "goal":
        updates["goal"] = "different goal"
    elif change == "remote":
        updates["start_url"] = "http://example.org:18080/customer/account/"
    elif change == "port":
        updates["start_url"] = "http://127.0.0.1/customer/account/"
    elif change == "route":
        updates["start_url"] = "http://127.0.0.1:18080/checkout/cart/"
    elif change == "query":
        updates["start_url"] = public.start_url + "?x=1"
    elif change == "fragment":
        updates["start_url"] = public.start_url + "#x"
    elif change == "family":
        updates["identity"] = public.identity.model_copy(update={"family": "other"})
    elif change == "version":
        updates["identity"] = public.identity.model_copy(update={"contract_version": 2})
    elif change == "split":
        updates["identity"] = public.identity.model_copy(update={"split": "test"})
    elif change == "source":
        updates["identity"] = public.identity.model_copy(
            update={"source_task_id": "foreign"}
        )
    elif change == "terminal":
        updates["allowed_actions"] = ("click",)
    elif change == "output":
        updates["output_requirements"] = ()
    raw = FIXTURE.read_bytes()
    with pytest.raises(EvidenceIntegrityError):
        load_order_eta_inputs(raw, reference(raw), public.model_copy(update=updates))


@pytest.mark.parametrize(
    "change",
    [
        "hash",
        "size",
        "visibility",
        "schema",
        "media",
        "duplicate",
        "nonfinite",
        "array",
        "utf8",
    ],
)
def test_native_decoder_identity_and_invalid_json(change: str) -> None:
    raw = FIXTURE.read_bytes()
    updates: dict[str, Any] = {}
    if change == "hash":
        updates["sha256"] = "f" * 64
    elif change == "size":
        updates["size_bytes"] = len(raw) + 1
    elif change == "visibility":
        updates["visibility"] = "public"
    elif change == "schema":
        updates["content_schema"] = "admin-native-contract/1"
    elif change == "media":
        updates["media_type"] = "text/plain"
    elif change == "duplicate":
        raw = b'{"goal":"one","goal":"two"}'
    elif change == "nonfinite":
        raw = b'{"date":NaN}'
    elif change == "array":
        raw = b"[]"
    elif change == "utf8":
        raw = b"\xff"
    with pytest.raises(EvidenceIntegrityError):
        load_order_eta_inputs(raw, reference(raw, **updates), public_task())


@pytest.mark.parametrize("extra", [-1, 0, 1])
def test_exact_native_byte_boundary(extra: int) -> None:
    original = FIXTURE.read_bytes()
    raw = original + b" " * (MAX_NATIVE_BYTES - len(original) + extra)
    if extra <= 0:
        assert (
            load_order_eta_inputs(
                raw, reference(raw), public_task()
            ).private_spec.admission
            == "unverified"
        )
    else:
        with pytest.raises(EvidenceIntegrityError):
            load_order_eta_inputs(raw, reference(raw), public_task())
