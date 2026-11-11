"""Task composition capability/protocol/evidence compatibility, without I/O."""

from lab_generate_skill.domain.registration import RegistryComponent, TaskRegistration
from lab_generate_skill.domain.evidence import EvidenceRequirements


def _covers(provided: EvidenceRequirements, required: EvidenceRequirements) -> None:
    if not set(required.facts) <= set(provided.facts) or not set(
        required.events
    ) <= set(provided.events):
        raise ValueError("Collector evidence does not cover consumer facts/events")


def _protocol(component: RegistryComponent) -> str:
    return component.interface_id + "/" + component.contract_version.split(".")[0]


def check_composition(
    r: TaskRegistration,
    roles: dict[tuple[str, str], str],
    components: dict[str, RegistryComponent],
) -> tuple[RegistryComponent, ...]:
    try:
        pairs = [
            ("site", r.site_provider),
            ("task_adapter", r.task_adapter),
            ("collector", r.collector),
            ("evaluator", r.evaluator),
            ("evidence_schema", r.evidence_schema_provider),
            ("recovery", r.recovery_provider),
            ("reviewer", r.reviewer),
            ("browser", roles[("browser", r.registration_id)]),
            ("actor_protocol", roles[("actor_protocol", "global")]),
        ]
        selected = tuple(components[identifier] for _, identifier in pairs)
    except KeyError as error:
        raise ValueError("Incomplete task composition in registry/release") from error
    for (kind, _), component in zip(pairs, selected, strict=True):
        if component.kind != kind:
            raise ValueError("Task composition component kind differs")
    if any(
        roles.get((kind, r.registration_id)) != identifier
        for kind, identifier in (
            ("site", r.site_provider),
            ("evaluator", r.evaluator),
            ("reviewer", r.reviewer),
        )
    ):
        raise ValueError("Registration differs from exact release role scope")
    site, task, collector, evaluator, schema, recovery, reviewer, browser, actor = (
        selected
    )
    if (_protocol(schema), _protocol(recovery), _protocol(actor)) != (
        r.evidence_schema,
        r.recovery_contract,
        r.actor_protocol,
    ):
        raise ValueError("Schema/recovery/Actor protocol mismatch")
    if not set(r.required_capabilities) <= set(site.provides_capabilities):
        raise ValueError("Site does not provide required task capabilities")
    available = set(site.provides_capabilities) | set(browser.provides_capabilities)
    for component in selected:
        if not set(component.requires_capabilities) <= available:
            raise ValueError("Composition lacks required runtime capability")

    def combine(*providers: RegistryComponent) -> EvidenceRequirements:
        return EvidenceRequirements(
            facts=tuple(
                dict.fromkeys(f for p in providers for f in p.provides_evidence.facts)
            ),
            events=tuple(
                dict.fromkeys(e for p in providers for e in p.provides_evidence.events)
            ),
        )

    for base in (site, browser, schema):
        if base.requires_evidence.facts or base.requires_evidence.events:
            raise ValueError(
                "Base provider/schema cannot require later captured evidence"
            )
    _covers(schema.provides_evidence, collector.provides_evidence)
    _covers(combine(site, browser), collector.requires_evidence)
    _covers(combine(site, browser, collector), task.requires_evidence)
    _covers(collector.provides_evidence, evaluator.requires_evidence)
    _covers(combine(site, collector), recovery.requires_evidence)
    _covers(combine(collector, evaluator), reviewer.requires_evidence)
    _covers(browser.provides_evidence, actor.requires_evidence)
    return selected
