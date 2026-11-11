"""Exact lookup and metadata preflight; never import declared implementations."""

from pathlib import Path
import sys
import pytest
from pydantic import ValidationError
from lab_generate_skill.domain.registration import (
    RegistrationKey,
    RegistryManifest,
    TaskRegistration,
    SupportedInterface,
)
from lab_generate_skill.domain.release import ReleaseManifest
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.registry.resolve import TaskRegistry, RegistrationNotFound
from lab_generate_skill.adapters.releases.registry_manifest import load_registry
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRequirements
from registry_fixtures import fixture, bind
from lab_generate_skill.domain.task import TaskBinding
from lab_generate_skill.domain.identity import TaskIdentity


def test_exact_lookup_repeat_and_no_component_imports(tmp_path: Path) -> None:
    f = fixture(tmp_path)
    before = set(sys.modules)
    registry = f.registry()
    result = registry.lookup(f.index.registrations[0].key)
    assert (
        result.registration == f.index.registrations[0] and len(result.components) == 9
    )
    assert registry.lookup(result.registration.key) == result
    assert not any(
        name.startswith("lab_generate_skill.sites.")
        for name in set(sys.modules) - before
    )
    raw = f.index.model_dump_json().encode()
    assert load_registry(raw, f.reference) == f.index


@pytest.mark.parametrize(
    "change",
    [{"site": "shopping"}, {"family": "customer_read"}, {"contract_version": 2}],
)
def test_no_nearest_site_family_or_version(
    tmp_path: Path, change: dict[str, object]
) -> None:
    f = fixture(tmp_path)
    key = RegistrationKey.model_validate(
        {**f.index.registrations[0].key.model_dump(), **change}
    )
    with pytest.raises(RegistrationNotFound):
        f.registry().lookup(key)


@pytest.mark.parametrize("fault", ["same_key", "same_id", "component_id", "empty"])
def test_ambiguous_registry_rejected(tmp_path: Path, fault: str) -> None:
    f = fixture(tmp_path)
    data = f.index.model_dump()
    original = data["registrations"][0]
    if fault == "same_key":
        data["registrations"] += ({**original, "registration_id": "other"},)
    elif fault == "same_id":
        data["registrations"] += ({**original, "family": "other"},)
    elif fault == "component_id":
        data["components"] += (data["components"][0],)
    else:
        data["registrations"] = ()
    with pytest.raises(ValidationError):
        RegistryManifest.model_validate(data)


@pytest.mark.parametrize(
    "fault",
    [
        "capability",
        "schema",
        "recovery",
        "actor",
        "missing_component",
        "kind",
        "capture_fact",
        "capture_event",
        "review_fact",
    ],
)
def test_incompatible_composition_fails_preflight(tmp_path: Path, fault: str) -> None:
    f = fixture(tmp_path)
    data = f.index.model_dump()
    r = data["registrations"][0]
    cs = list(data["components"])
    if fault == "capability":
        r = {**r, "required_capabilities": ("unsupported",)}
    elif fault in ("schema", "recovery", "actor"):
        field = {
            "schema": "evidence_schema",
            "recovery": "recovery_contract",
            "actor": "actor_protocol",
        }[fault]
        r = {**r, field: "other/1"}
    elif fault == "missing_component":
        r = {**r, "collector": "missing"}
    elif fault == "kind":
        cs = [
            {**c, "kind": "task_adapter"} if c["component_id"] == "collector" else c
            for c in cs
        ]
    elif fault == "capture_fact":
        cs = [
            (
                {
                    **c,
                    "provides_evidence": EvidenceRequirements(
                        events=("before_action", "after_action")
                    ).model_dump(),
                }
                if c["component_id"] == "collector"
                else c
            )
            for c in cs
        ]
    elif fault == "capture_event":
        cs = [
            (
                {**c, "provides_evidence": {**c["provides_evidence"], "events": ()}}
                if c["component_id"] == "collector"
                else c
            )
            for c in cs
        ]
    else:
        cs = [
            (
                {
                    **c,
                    "requires_evidence": {
                        **c["requires_evidence"],
                        "events": ("download",),
                    },
                }
                if c["component_id"] == "reviewer"
                else c
            )
            for c in cs
        ]
    index = RegistryManifest.model_validate(
        {**data, "registrations": (r,), "components": tuple(cs)}
    )
    with pytest.raises(ValueError):
        bind(index, f.release).registry()


def test_release_pins_and_supported_major_are_mandatory(tmp_path: Path) -> None:
    f = fixture(tmp_path)
    with pytest.raises(ValueError):
        TaskRegistry(f.index, f.reference, f.release, ())
    wrong = tuple(
        SupportedInterface(interface_id=x.interface_id, contract_major=2)
        for x in f.supported
    )
    with pytest.raises(ValueError):
        TaskRegistry(f.index, f.reference, f.release, wrong)
    other = ReleaseManifest.model_validate(
        {**f.release.model_dump(), "release_id": "other"}
    )
    with pytest.raises(OwnershipConflict):
        TaskRegistry(f.index, f.reference, other, f.supported)
    with pytest.raises(EvidenceIntegrityError):
        TaskRegistry(
            f.index,
            f.reference.model_copy(update={"sha256": "f" * 64}),
            f.release,
            f.supported,
        )


@pytest.mark.parametrize(
    "entry",
    [
        "experiments/x.py",
        "os:system",
        "lab_generate_skill.scripts.old:run",
        "lab_generate_skill.old:run",
        "lab_generate_skill.sites.other:Factory",
    ],
)
def test_arbitrary_script_or_unpinned_module_rejected(
    tmp_path: Path, entry: str
) -> None:
    from lab_generate_skill.domain.registration import RegistryComponent

    component = fixture(tmp_path).index.components[0]
    with pytest.raises(ValidationError):
        RegistryComponent.model_validate(
            {**component.model_dump(), "entrypoint": entry}
        )


def test_two_families_and_compatible_replacement_are_explicit(tmp_path: Path) -> None:
    f = fixture(tmp_path)
    original = f.index.registrations[0]
    second = TaskRegistration.model_validate(
        {
            **original.model_dump(),
            "family": "customer_read",
            "registration_id": "customer-read-v1",
        }
    )
    index = RegistryManifest.model_validate(
        {**f.index.model_dump(), "registrations": (original, second)}
    )
    combined = bind(index, f.release).registry()
    assert combined.lookup(second.key).registration == second
    replacement = next(
        c for c in f.index.components if c.component_id == "evaluator"
    ).model_copy(
        update={
            "entrypoint": "lab_generate_skill.sites.shopping_admin.evaluator:Replacement"
        }
    )
    updated = RegistryManifest.model_validate(
        {
            **f.index.model_dump(),
            "components": tuple(
                replacement if c.component_id == "evaluator" else c
                for c in f.index.components
            ),
        }
    )
    result = bind(updated, f.release).registry().lookup(original.key)
    assert next(
        c for c in result.components if c.kind == "evaluator"
    ).entrypoint.endswith(":Replacement")
    assert f.registry().lookup(original.key).registration == result.registration


def test_noncanonical_or_duplicate_registry_json_rejected(tmp_path: Path) -> None:
    f = fixture(tmp_path)
    for raw in (
        f.index.model_dump_json(indent=2).encode(),
        b'{"schema_version":"task-registry/1","schema_version":"task-registry/1"}',
    ):
        ref = evidence_reference(
            raw,
            EvidenceMetadata(
                media_type="application/json",
                content_schema="task-registry/1",
                visibility="private",
                producer="unit",
            ),
        )
        with pytest.raises(EvidenceIntegrityError):
            load_registry(raw, ref)


def test_task_binding_resolves_exact_id_without_consuming_private_data(
    tmp_path: Path,
) -> None:
    f = fixture(tmp_path)
    registration = f.index.registrations[0]
    public = evidence_reference(
        b"public",
        EvidenceMetadata(
            media_type="application/json",
            content_schema="public-task/1",
            visibility="public",
            producer="unit",
        ),
    )
    private = evidence_reference(
        b"private",
        EvidenceMetadata(
            media_type="application/json",
            content_schema="private-spec/1",
            visibility="private",
            producer="unit",
        ),
    )
    task = TaskBinding(
        identity=TaskIdentity(
            source_task_id="source-1",
            task_id="task-1",
            split="test",
            **registration.key.model_dump(),
        ),
        registration_id=registration.registration_id,
        public_task_ref=public,
        private_spec_ref=private,
        baseline_ref=private,
    )
    registry = f.registry()
    assert registry.resolve(task) == registry.lookup(registration.key)
    assert registry.resolve(task) == registry.resolve(task)
    with pytest.raises(OwnershipConflict, match="registration ID"):
        registry.resolve(task.model_copy(update={"registration_id": "another"}))


@pytest.mark.parametrize("value", [True, 0, -1, "1", None, 1.5])
def test_invalid_contract_version_never_coerced(tmp_path: Path, value: object) -> None:
    r = fixture(tmp_path).index.registrations[0]
    with pytest.raises(ValidationError):
        TaskRegistration.model_validate({**r.model_dump(), "contract_version": value})


@pytest.mark.parametrize(
    "caps", [("persisted_mutation", "persisted_mutation"), ("",), (), ("x",) * 129]
)
def test_explicit_capability_bounds(tmp_path: Path, caps: tuple[str, ...]) -> None:
    f = fixture(tmp_path)
    data = {**f.index.registrations[0].model_dump(), "required_capabilities": caps}
    if not caps:
        r = TaskRegistration.model_validate(data)
        index = RegistryManifest.model_validate(
            {**f.index.model_dump(), "registrations": (r,)}
        )
        assert (
            bind(index, f.release)
            .registry()
            .lookup(r.key)
            .registration.required_capabilities
            == ()
        )
    else:
        with pytest.raises(ValidationError):
            TaskRegistration.model_validate(data)
