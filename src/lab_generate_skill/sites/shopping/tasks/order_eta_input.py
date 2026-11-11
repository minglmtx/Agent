"""Pure binding of an explicit public task to its original local ETA fixture.

No account credentials, public goal synthesis, preparation or admission. Legacy
finish/answer syntax is replaced by the common declared browser terminal method
in public output requirements; expected dates remain private.
"""

from typing import Any
from urllib.parse import urlsplit
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task import PublicTask
from .order_eta_spec import OrderEtaSpec, OrderEtaInputs, OUTPUT_REQUIREMENTS

NATIVE_FIELDS = frozenset(
    {
        "task_id",
        "source_task_id",
        "domain",
        "goal",
        "derived_goal",
        "original_goal",
        "start_path",
        "recorded_start_paths",
        "recorded_start_urls",
        "source_trace_ids",
        "heldout_quarantine",
        "eligible_for_training",
        "is_explicit_derivative",
        "task_text_changed",
        "original_evaluation_equivalence",
        "query",
        "api_calls",
        "actor_attempts",
        "no_external_response_required",
        "goal_revision",
        "status",
        "initial_state_revision",
        "start_revision",
        "admission_result",
    }
)


def _object(value: object) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError("Expected native Shopping object")
    return value


def bind_order_eta_inputs(
    native: dict[str, Any], reference: EvidenceRef, public: PublicTask
) -> OrderEtaInputs:
    public = PublicTask.model_validate(public)
    native = _object(native)
    query = _object(native.get("query"))
    if set(native) != NATIVE_FIELDS or set(query) != {
        "family",
        "kind",
        "fields",
        "complete_scope",
        "order_number",
        "date",
        "fixture_version",
    }:
        raise ValueError("Unsupported native Shopping fields")
    if (
        native.get("domain"),
        query.get("family"),
        query.get("kind"),
        query.get("fields"),
        query.get("fixture_version"),
    ) != (
        "shopping",
        "shopping_complete_native_training",
        "recorded_order_eta",
        {"estimated_delivery_date": "string"},
        "native-local-recorded-order-date-v1",
    ):
        raise ValueError("Expected selected local recorded-order ETA contract")
    for key, expected in (
        ("heldout_quarantine", False),
        ("eligible_for_training", False),
        ("is_explicit_derivative", True),
        ("task_text_changed", True),
        ("original_evaluation_equivalence", False),
        ("no_external_response_required", True),
    ):
        if native.get(key) is not expected:
            raise ValueError("Shopping historical scope flag differs: " + key)
    if any(
        type(native.get(k)) is not int or native[k] != 0
        for k in ("api_calls", "actor_attempts")
    ):
        raise ValueError("Native input must precede model/Actor execution")
    if (
        native.get("source_task_id") != public.identity.source_task_id
        or native.get("goal") != public.goal
        or native.get("derived_goal") != public.goal
    ):
        raise ValueError("Explicit public Shopping source/goal differs from original")
    if "send_msg_to_user" not in public.allowed_actions or not all(
        x in public.output_requirements for x in OUTPUT_REQUIREMENTS
    ):
        raise ValueError(
            "Selected ETA task requires the declared common terminal answer protocol"
        )
    revision = _object(native.get("goal_revision"))
    start = _object(native.get("start_revision"))
    initial = _object(native.get("initial_state_revision"))
    if (
        type(revision.get("version")) is not int
        or revision["version"] != 1
        or revision.get("derived_goal") != public.goal
        or revision.get("original_goal") != native.get("original_goal")
        or not isinstance(revision.get("reason"), str)
        or not revision["reason"].strip()
    ):
        raise ValueError("Original Shopping goal lineage differs")
    if (
        not isinstance(native.get("original_goal"), str)
        or not native["original_goal"].strip()
        or native.get("recorded_start_paths") != ["/checkout/cart/"]
        or type(start.get("version")) is not int
        or start["version"] != 1
        or start.get("original_start") != "/checkout/cart/"
        or start.get("derived_start") != "/customer/account/"
        or not isinstance(start.get("reason"), str)
        or not start["reason"].strip()
    ):
        raise ValueError("Original Shopping start lineage differs")
    if (
        initial.get("fixture_version") != query["fixture_version"]
        or initial.get("external_delivery") is not False
        or initial.get("local_mail_capture") is not True
    ):
        raise ValueError("Local fixture/mail isolation declaration differs")
    url = urlsplit(public.start_url)
    if (
        native.get("start_path") != "/customer/account/"
        or url.scheme != "http"
        or url.hostname != "127.0.0.1"
        or url.port is None
        or not 1024 <= url.port <= 65535
        or url.path != native["start_path"]
        or url.query
        or url.fragment
    ):
        raise ValueError(
            "Explicit Shopping start must use its allocated local customer account"
        )
    private = OrderEtaSpec(
        task=public.identity,
        native_contract_ref=reference,
        legacy_runtime_task_id=native["task_id"],
        order_number=query["order_number"],
        recorded_date=query["date"],
    )
    return OrderEtaInputs(public_task=public, private_spec=private)
