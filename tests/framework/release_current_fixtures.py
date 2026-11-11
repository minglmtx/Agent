"""Unit-only activation authority; never installed as a production default."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from lab_generate_skill.adapters.clock import SystemClock
from lab_generate_skill.adapters.releases.current import FileReleaseCurrent
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceMetadata, EvidenceRef
from lab_generate_skill.domain.evidence_identity import evidence_reference
from lab_generate_skill.domain.lifecycle import OperationContext
from lab_generate_skill.domain.release_activation import (
    ReleaseDeployment,
    ReleaseActivation,
    ReleaseSwitch,
)
from lab_generate_skill.domain.release_current import ReleaseCurrentSnapshot
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.runtime.lifecycle import OperationGuards
from test_slurm_commands import Cancel


def op(name: str = "initialize") -> OperationContext:
    return OperationContext(
        operation_id=name,
        run_id="publication",
        owner_id="publisher",
        deadline=datetime.now(timezone.utc) + timedelta(seconds=60),
    )


def ref(schema: str, value: str = "one") -> EvidenceRef:
    return evidence_reference(
        value.encode(),
        EvidenceMetadata(
            media_type="application/json",
            content_schema=schema,
            visibility="private",
            producer="unit-current",
        ),
    )


def switch(revision: int = 0, name: str = "one") -> ReleaseSwitch:
    return ReleaseSwitch(
        expected_revision=revision,
        operation=op("switch-" + name),
        activation=ReleaseActivation(
            release_id="release-" + name,
            manifest_ref=ref("release-manifest/1", name),
            registry_ref=ref("task-registry/1", name),
            acceptance_ref=ref("release-acceptance/1", name),
        ),
    )


class UnitCurrentAuthority:
    def __init__(self) -> None:
        self.deny_access = False
        self.deny_switch = False
        self.switches = 0

    def authorize_access(
        self,
        deployment: ReleaseDeployment,
        operation: OperationContext,
        control: OperationControl,
    ) -> None:
        if self.deny_access:
            raise OwnershipConflict("unit access denied")

    def authorize_switch(
        self,
        prior: ReleaseCurrentSnapshot,
        change: ReleaseSwitch,
        control: OperationControl,
    ) -> None:
        if self.deny_switch:
            raise OwnershipConflict("unit switch denied")
        self.switches += 1


def store(
    root: Path, authority: UnitCurrentAuthority | None = None, limit: int = 5
) -> FileReleaseCurrent:
    return FileReleaseCurrent(
        root,
        ReleaseDeployment(deployment_id="main", max_switches=limit),
        OperationGuards(SystemClock(), Cancel()),
        authority if authority is not None else UnitCurrentAuthority(),
    )


def disk(root: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
