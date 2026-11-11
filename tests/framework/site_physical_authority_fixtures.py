"""Actual file journals, explicitly synthetic source/kernel/transport for module gate."""

from contextlib import contextmanager
from collections.abc import Iterator
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.adapters.sites.physical_authority import (
    ObservedSiteResourceAuthority,
)
from lab_generate_skill.adapters.sites.resource import registered_site, RegisteredSite
from lab_generate_skill.adapters.sites import physical_authority as module, step
from lab_generate_skill.domain.evidence import EvidenceRef, EvidenceMetadata
from lab_generate_skill.domain.site_resource import SiteResourceReady, SiteStepClosed
from lab_generate_skill.domain.slurm_step import SlurmStepTarget
from lab_generate_skill.ports.lifecycle import OperationControl
from site_resource_fixtures import Case, resource_case, ready, closed


class Held:
    def __init__(self) -> None:
        self.closes = 0
        self.error: BaseException | None = None

    def close(self) -> None:
        self.closes += 1
        if self.error:
            raise self.error


def raw(
    c: Case,
    original_target: SlurmStepTarget,
    original_phase: str,
    control: OperationControl,
    **changes: Any,
) -> EvidenceRef:
    value = {
        "schema_version": "site-step-raw/1",
        "target": original_target.model_dump(mode="json"),
        "phase": original_phase,
        "kernel": [{"explicit_synthetic": True}],
        "commands": [{"explicit_synthetic": True}],
        "error": None,
        **changes,
    }
    return c.evidence.put(
        json.dumps(value).encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema="site-step-raw/1",
            visibility="private",
            producer="fixed-site-step-v1",
        ),
        control=control,
    )


@dataclass
class PhysicalCase:
    c: Case
    authority: ObservedSiteResourceAuthority
    held: list[Held]
    ready_reads: list[step.SiteStepState]
    closed_reads: list[step.SiteStepState]

    @contextmanager
    def enter(self) -> Iterator[RegisteredSite]:
        with self.authority:
            with registered_site(
                self.c.spec,
                self.c.op,
                journal=self.c.journal,
                evidence=self.c.evidence,
                controls=self.c.controls,
                clock=self.c.clock,
                authority=self.authority,
            ) as site:
                yield site


def physical_case(root: Path, monkeypatch: pytest.MonkeyPatch) -> PhysicalCase:
    c = resource_case(root, monkeypatch)
    authority = ObservedSiteResourceAuthority(
        c.spec, c.op, source=c.authority, evidence=c.evidence
    )
    p = PhysicalCase(c, authority, [], [], [])
    monkeypatch.setattr(
        module, "current_process_identity", lambda: c.spec.slurm.parent.writer
    )

    def observe_ready(*args: Any, **kwargs: Any) -> SiteResourceReady:
        result = ready(*args, **kwargs)
        state = args[1]
        p.ready_reads.append(state)
        result = result.model_copy(
            update={"evidence": raw(c, result.controller.target, "ready", args[4])}
        )
        state.ready = result
        if state is authority._state:
            held = Held()
            p.held.append(held)
            # Synthetic handle is limited to this explicit unit observer. It
            # supplies only close; the production adapter must never stop it.
            state.pin = held
        return result

    def observe_closed(*args: Any, **kwargs: Any) -> SiteStepClosed | None:
        result = closed(*args, **kwargs)
        p.closed_reads.append(args[1])
        if result is not None:
            result = result.model_copy(
                update={"evidence": raw(c, result.target, "closed", args[4])}
            )
        return result

    monkeypatch.setattr(step, "observe_ready", observe_ready)
    monkeypatch.setattr(step, "observe_closed", observe_closed)
    return p
