"""Current Reddit transport contract on the same once-only CAS implementation."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.sites.reddit_private_evidence import (
    RedditPrivateEvidence,
    check_payload,
)
from lab_generate_skill.adapters.sites.gitlab_private_evidence import (
    check_payload as gitlab_payload,
)
from lab_generate_skill.domain.native_private_json import (
    GITLAB_PRIVATE_JSON,
    REDDIT_PRIVATE_JSON,
    NativePrivateJsonProfile,
)
from lab_generate_skill.domain.site_private_fact import SitePrivateEvidenceContext
from lab_generate_skill.domain.site_task import SiteTaskRequest
from lab_generate_skill.domain.errors import (
    OwnershipConflict,
    InvalidTransition,
    EvidenceIntegrityError,
)
from lab_generate_skill.bootstrap.reddit_native_image import load_image_inputs
from test_gitlab_private_evidence import c as c, Case as GitlabCase, Admission
from test_reddit_image_inputs import FIXTURE, reference, public_task
from test_slurm_commands import guard


@dataclass
class Case:
    transport: RedditPrivateEvidence
    request: SiteTaskRequest
    original: GitlabCase


@pytest.fixture
def native(c: GitlabCase) -> Case:
    context = SitePrivateEvidenceContext.model_validate_json(
        c.transport.context.model_copy(update={"site_id": "reddit"}).model_dump_json()
    )
    raw = FIXTURE.read_bytes()
    inputs = load_image_inputs(raw, reference(raw), public_task())
    request = c.request.model_copy(
        update={
            "task": inputs.public_task.identity,
            "operation": c.request.operation.model_copy(
                update={
                    "operation_id": "reddit-private-capture",
                    "attempt_id": "reddit-attempt",
                }
            ),
            "private_input": inputs.private_spec.model_dump_json(),
        }
    )
    plan = c.transport.plan.model_copy(update={"profile": REDDIT_PRIVATE_JSON})
    return Case(
        RedditPrivateEvidence(plan, context, c.store, Admission(plan, context)),
        request,
        c,
    )


def test_complete_reddit_json_uses_distinct_metadata_and_never_expands_rpc(
    native: Case,
) -> None:
    raw = b'{"synthetic_complete_reference":"' + b"x" * (1024 * 1024) + b'"}'
    result = native.transport.publish(native.request, raw, control=guard(30))
    check_payload(result.payload_ref, native.transport.plan)
    assert (
        result.context.site_id == "reddit"
        and result.request_sha256 == native.request.digest
    )
    assert result.payload_ref.content_schema == REDDIT_PRIVATE_JSON.content_schema
    assert result.payload_ref.producer == REDDIT_PRIVATE_JSON.producer
    assert native.transport.read(native.request, result, control=guard(30)) == raw
    assert native.transport.read(native.request, result, control=guard(30)) == raw
    with pytest.raises(EvidenceIntegrityError):
        gitlab_payload(result.payload_ref, native.transport.plan)
    with pytest.raises(InvalidTransition):
        native.transport.publish(native.request, raw, control=guard())


@pytest.mark.parametrize(
    "case",
    ["site", "family", "split", "version_bool", "operation", "context", "metadata"],
)
def test_wrong_site_scope_or_reference_never_receives_native_read_or_write_right(
    native: Case, case: str
) -> None:
    request = native.request
    if case in ("site", "family", "split", "version_bool", "operation"):
        if case == "site":
            request = request.model_copy(
                update={"task": request.task.model_copy(update={"site": "gitlab"})}
            )
        elif case == "family":
            request = request.model_copy(
                update={
                    "task": request.task.model_copy(update={"family": "post_reading"})
                }
            )
        elif case == "split":
            request = request.model_copy(
                update={"task": request.task.model_copy(update={"split": "test"})}
            )
        elif case == "version_bool":
            request = request.model_copy(
                update={
                    "task": request.task.model_copy(update={"contract_version": True})
                }
            )
        else:
            request = request.model_copy(
                update={
                    "operation": request.operation.model_copy(
                        update={"run_id": "foreign"}
                    )
                }
            )
        with pytest.raises((ValueError, OwnershipConflict)):
            native.transport.publish(request, b"{}", control=guard())
        assert not native.transport.attempted
    else:
        result = native.transport.publish(request, b"{}", control=guard())
        if case == "context":
            result = result.model_copy(
                update={"context": native.original.transport.context}
            )
        else:
            result = result.model_copy(
                update={
                    "payload_ref": result.payload_ref.model_copy(
                        update={"content_schema": GITLAB_PRIVATE_JSON.content_schema}
                    )
                }
            )
        with pytest.raises((OwnershipConflict, EvidenceIntegrityError)):
            native.transport.read(request, result, control=guard())


@pytest.mark.parametrize(
    "raw",
    [
        None,
        b"",
        b"null",
        b"[]",
        b'{"key":1,"key":2}',
        b'{"number":NaN}',
        bytearray(b"{}"),
    ],
)
def test_invalid_json_and_wrong_types_are_refused_before_native_publication(
    native: Case, raw: Any
) -> None:
    with pytest.raises(ValueError):
        native.transport.publish(native.request, raw, control=guard())
    assert not native.transport.attempted


@pytest.mark.parametrize(
    "field,value",
    [
        ("family", "profile_ssh_key"),
        ("producer", "fixed-gitlab-native-private-v1"),
        ("content_schema", "gitlab-native-private-json/1"),
        ("site_id", None),
    ],
)
def test_transport_profile_cannot_mix_contract_variants(field: str, value: Any) -> None:
    with pytest.raises(ValueError):
        NativePrivateJsonProfile.model_validate(
            {**REDDIT_PRIVATE_JSON.model_dump(), field: value}
        )
