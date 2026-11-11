"""Same configuration as original factory, no rereading known input documents."""

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast
import pytest
from production_actor_inputs import (
    declare_known_actor_inputs,
    publish_known_actor_inputs,
)
from production_inputs import OriginalDocuments
from production_installation import reference
from production_task_plan import freeze_actor_inputs
from lab_generate_skill.domain.actor_model_binding import ActorModelBinding
from lab_generate_skill.domain.actor_resource import ActorResourceSpec
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from actor_long_fixtures import long_config
from source_actor_context_fixtures import source_context_case

W = Path("/anvme/workspace/r102bf10-lab-generate-skill")
SOFTWARE = (
    W
    / "experiments/framework-combined-release-20261030-v1/actor-dispatch-inputs-verified-check-4947464/result.json"
)


@pytest.mark.parametrize("fail_on", [1, 2, 3])
def test_partial_publication_stops_without_ready_result_or_replay(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fail_on: int,
) -> None:
    c = source_context_case(tmp_path / "case", monkeypatch, engine_config=long_config())
    store = c.actor.evidence
    binding = ActorModelBinding.model_validate_json(
        store.read(c.actor.spec.model_binding_ref)
    )
    original = cast(Callable[..., EvidenceRef], store.put)
    calls = 0

    def interrupted(*args: Any, **kwargs: Any) -> EvidenceRef:
        nonlocal calls
        calls += 1
        if calls == fail_on:
            raise RuntimeError("Unit original metadata acknowledgement unconfirmed")
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "put", interrupted)
    software = SOFTWARE.read_bytes()
    try:
        with pytest.raises(RuntimeError, match="acknowledgement unconfirmed"):
            publish_known_actor_inputs(
                c.actor.spec,
                binding,
                c.params,
                reference(software, "framework-check/3"),
                software,
                OriginalDocuments(store, c.actor.controls),
                c.actor.op,
            )
        assert calls == fail_on
        assert c.loader.loads == c.loader.session.calls == c.session.calls == 0
    finally:
        c.client.close(c.actor.controls.bind(c.actor.op))


def test_same20_turn_profiles_and_canonical_bytes_without_configuration_read_rpcs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = source_context_case(tmp_path / "case", monkeypatch, engine_config=long_config())
    store = c.actor.evidence
    binding = ActorModelBinding.model_validate_json(
        store.read(c.actor.spec.model_binding_ref)
    )
    software = SOFTWARE.read_bytes()
    software_ref = reference(software, "framework-check/3")
    documents = OriginalDocuments(store, c.actor.controls)
    operation = c.actor.op.model_copy(update={"operation_id": "known-actor-config"})
    reads: list[EvidenceRef] = []
    original = cast(Callable[..., bytes], store.read)

    def counted(ref: EvidenceRef, *args: Any, **kwargs: Any) -> bytes:
        reads.append(ref)
        return original(ref, *args, **kwargs)

    monkeypatch.setattr(store, "read", counted)
    try:
        expected = freeze_actor_inputs(
            c.actor.spec, c.params, software_ref, software, documents, operation
        )
        assert len(reads) == 21
        reads.clear()

        def no_owner(*args: Any, **kwargs: Any) -> Any:
            pytest.fail("Pure Actor data must not construct or validate an allocation")

        with monkeypatch.context() as pure:
            pure.setattr(ActorResourceSpec, "model_validate", no_owner)
            declared = declare_known_actor_inputs(
                c.actor.spec.artifact,
                c.actor.spec.engine_config,
                binding,
                c.actor.spec.model_binding_ref,
                c.params,
                software_ref,
                software,
            )
        assert not reads
        actual = publish_known_actor_inputs(
            c.actor.spec,
            binding,
            c.params,
            software_ref,
            software,
            documents,
            operation,
        )
        assert not reads
        assert declared == actual == expected
        assert actual.context.model_dump_json() == expected.context.model_dump_json()
        assert len(actual.context.profiles) == 20
        assert all(
            p.configuration_ref == actual.parameters_ref
            for p in actual.context.profiles
        )
        assert all(
            p.routing_ref == c.actor.spec.model_binding_ref
            for p in actual.context.profiles
        )
        assert c.loader.loads == c.loader.session.calls == c.session.calls == 0
    finally:
        c.client.close(c.actor.controls.bind(c.actor.op))


@pytest.mark.parametrize(
    "fault", ["envelope", "config-size", "release", "reduced-output"]
)
def test_static_mismatches_refuse_before_any_cas_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    c = source_context_case(tmp_path / "case", monkeypatch, engine_config=long_config())
    store = c.actor.evidence
    binding = ActorModelBinding.model_validate_json(
        store.read(c.actor.spec.model_binding_ref)
    )
    actor, parameters = c.actor.spec, c.params
    if fault == "envelope":
        actor = actor.model_copy(
            update={
                "model_binding_ref": actor.model_binding_ref.model_copy(
                    update={"content_schema": "actor-model-binding/1"}
                )
            }
        )
    elif fault == "config-size":
        binding = binding.model_copy(
            update={
                "engine_config_ref": binding.engine_config_ref.model_copy(
                    update={"size_bytes": 1}
                )
            }
        )
        actor = actor.model_copy(
            update={
                "model_binding_ref": reference(
                    binding.model_dump_json().encode(), "model-binding/1"
                )
            }
        )
    elif fault == "release":
        binding = binding.model_copy(
            update={
                "release_ref": binding.release_ref.model_copy(
                    update={"producer": "different-release-reference"}
                )
            }
        )
    else:
        parameters = parameters.model_copy(update={"max_new_tokens": 4095})

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Bad static configuration reached CAS publication")

    monkeypatch.setattr(store, "put", forbidden)
    software = SOFTWARE.read_bytes()
    try:
        with pytest.raises((ValueError, OwnershipConflict)):
            publish_known_actor_inputs(
                actor,
                binding,
                parameters,
                reference(software, "framework-check/3"),
                software,
                OriginalDocuments(store, c.actor.controls),
                c.actor.op,
            )
    finally:
        c.client.close(c.actor.controls.bind(c.actor.op))


def test_obsolete_software_gate_is_rejected_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from lab_generate_skill.domain.errors import EvidenceIntegrityError

    c = source_context_case(tmp_path / "case", monkeypatch, engine_config=long_config())
    store = c.actor.evidence
    binding = ActorModelBinding.model_validate_json(
        store.read(c.actor.spec.model_binding_ref)
    )
    software = (
        W
        / "experiments/framework-admin-navigation-production-20261102-v1/check-isolated-4902507/result.json"
    ).read_bytes()

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("Obsolete software evidence reached publication")

    monkeypatch.setattr(store, "put", forbidden)
    try:
        with pytest.raises(
            EvidenceIntegrityError, match="omits exact context implementation pins"
        ):
            publish_known_actor_inputs(
                c.actor.spec,
                binding,
                c.params,
                reference(software, "framework-check/3"),
                software,
                OriginalDocuments(store, c.actor.controls),
                c.actor.op,
            )
        assert c.loader.loads == c.loader.session.calls == c.session.calls == 0
    finally:
        c.client.close(c.actor.controls.bind(c.actor.op))
