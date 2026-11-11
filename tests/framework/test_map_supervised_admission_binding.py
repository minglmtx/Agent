"""Map selects the already tested whole-graph ports on its actual bootstrap.

This is a bootstrap boundary check. Original retained material is read only;
admission is intercepted before any plan, claim, native, or model effect. The
installed graph algorithms and live revocation have separate integration tests.
"""

from pathlib import Path
from dataclasses import fields
from typing import Any
import pytest

import lab_generate_skill.bootstrap.map_execution_admission as module
from lab_generate_skill.adapters.plans.closed_source_transport import (
    ClosedSourceReadTransport,
)
from lab_generate_skill.adapters.plans.closed_source_records import (
    SupervisedRunPlanInputChecks,
    SupervisedExecutionTaskSourceChecks,
    SupervisedSourceTaskBindingAuthority,
)
from lab_generate_skill.adapters.ledger.execution_claim_authority import (
    OriginalExecutionClaimAuthority,
)
from lab_generate_skill.bootstrap.map_closed_source import ClosedMapSourceDeclarations
from task_resource_owner_fixtures import owned_task
from site_instance_fixtures import node_path as node_path
from test_closed_source_read_protocol import original_material


def test_map_uses_one_installed_reader_for_full_inputs_source_and_binding(
    node_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    material, _ = original_material()

    class NoEffectsReader(ClosedSourceReadTransport):
        def __init__(self) -> None:
            pass

    transport = NoEffectsReader()
    with owned_task(node_path, monkeypatch) as (c, r):
        j, p = c.journals, c.p
        run = j.plans.load(r.owner.run, p.plan.read_operation)

        class Caller(OriginalExecutionClaimAuthority):
            def __init__(self) -> None:
                self.run, self.task = r.owner.run, r.owner.task

        sentinel = object()
        calls: list[dict[str, Any]] = []

        def stop(*args: Any, **kwargs: Any) -> Any:
            checks = kwargs["plan_input_checks"]
            assert isinstance(checks, SupervisedRunPlanInputChecks)
            source = kwargs["source_checks"](Caller())
            binding = kwargs["binding_load_checks"](Caller())
            assert isinstance(source, SupervisedExecutionTaskSourceChecks)
            assert isinstance(binding, SupervisedSourceTaskBindingAuthority)
            assert (
                checks.transport is source.transport is binding.transport is transport
            )
            assert checks.material == source.material == binding.material == material
            calls.append(kwargs)
            return sentinel

        monkeypatch.setattr(module, "admit_closed_execution_source", stop)
        original_claims = {f.name: f.read_bytes() for f in j.claims._root.iterdir()}
        result = module.admit_map_execution_source(
            run,
            r.owner.run,
            ClosedMapSourceDeclarations(
                **{
                    f.name: getattr(material, f.name)
                    for f in fields(ClosedMapSourceDeclarations)
                }
            ),
            r.owner.authority.execution,
            r.owner.authority.controller,
            p.plan.read_operation,
            claim_root=j.claims._root,
            claim_scope=j.claims._scope,
            evidence=r.owner.evidence,
            controls=p.original.resource.controls,
            source_reads=transport,
        )
        assert result is sentinel and len(calls) == 1
        assert original_claims == {
            f.name: f.read_bytes() for f in j.claims._root.iterdir()
        }
        assert p.requests == [] and c.native.loader.session.calls == 0
