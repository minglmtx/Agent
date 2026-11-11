"""Real selected Map resource domain around the existing full task/Actor chain."""

from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
import json
import tempfile
import shutil
import pytest
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.adapters.sites.resource import registered_site
from lab_generate_skill.adapters.processes.remote_errors import describe_error
from map_source_inputs import source_inputs, check_source_scope
from map_site_engineering_authority import MapEngineeringAuthority
from map_qualified_source_native import MapQualifiedSource
from map_source_lifecycle_native import run
from map_startup_log_preservation import preserve_closed_startup_logs
from source_task_hooks import SourceTaskHooks
from site_resource_fixtures import resource_case
from installed_source_fixtures import InstalledFixture
from storage_installation_fixtures import storage_installation
from test_slurm_commands import guard


def run_source(
    installed: InstalledFixture,
    root: Path,
    patch: pytest.MonkeyPatch,
    hooks: SourceTaskHooks,
    *,
    scope: StateScope,
    evidence_root: Path,
) -> None:
    if hooks.reddit_selection is not None or hooks.gitlab_selection is not None:
        raise ValueError("Foreign selected input cannot enter the original Map source")
    scope = check_source_scope(hooks.owner, scope, hooks.map_selection)
    parent = Path(tempfile.mkdtemp(prefix="lab-map-selected-", dir="/tmp"))
    inputs = source_inputs(
        hooks.evidence,
        hooks.owner,
        storage_installation(installed),
        root,
        parent,
        guard(30),
        scope=scope,
        evidence_root=evidence_root,
        selection=hooks.map_selection,
    )
    c = resource_case(
        root, patch, config=inputs.configuration, real_step=True, store=hooks.evidence
    )
    # Preserve the exact predeclared environment recovery, before registration.
    c.spec = c.spec.model_copy(update={"configuration": inputs.configuration})
    c.op = c.op.model_copy(
        update={
            "recovery_ref": c.spec.token.recovery_ref,
            "deadline": datetime.now(timezone.utc) + timedelta(seconds=7200),
        }
    )
    authority = MapEngineeringAuthority(c, parent)
    c.authority = authority
    facts: dict[str, Any] = dict(
        passed=False,
        engineering_only=True,
        formal_source_admission=False,
        paid_calls=0,
        private_root=str(parent),
        configuration=c.spec.model_dump(mode="json"),
    )
    try:
        with registered_site(
            c.spec,
            c.op,
            journal=c.journal,
            evidence=c.evidence,
            controls=c.controls,
            clock=c.clock,
            authority=authority,
        ) as site:
            facts["started"] = site.site.model_dump(mode="json")
            source = MapQualifiedSource(
                c, site, inputs, allowed_actions=hooks.allowed_actions
            )
            authority.task_input = source.native.private_input_json()
            run(source, hooks, root, patch, facts)
        read = c.op.cleanup(
            "map-final-site-closed-read", now=datetime.now(timezone.utc), seconds=30
        )
        record = c.journal.read(c.spec.token, read)
        facts["resource_record"] = record.model_dump(mode="json")
        assert record.state == "closed" and authority.closed is not None
        ending = json.loads(
            c.evidence.read(
                record.events[-1].evidence[0], control=c.controls.bind(read)
            )
        )
        assert not ending["details"]["cleanup_errors"]
        facts.update(
            passed=True,
            ending=ending,
            original_domain=authority.closed.model_dump(mode="json"),
        )
    except BaseException as error:
        facts["error"] = describe_error(error).model_dump(mode="json")
        raise
    finally:
        try:
            final_read = c.op.cleanup(
                "map-preserved-resource-read",
                now=datetime.now(timezone.utc),
                seconds=30,
            )
            facts["resource_record"] = c.journal.read(
                c.spec.token, final_read
            ).model_dump(mode="json")
        except BaseException as record_error:
            facts["resource_record_error"] = describe_error(record_error).model_dump(
                mode="json"
            )
        if authority.closed is not None:
            facts["original_domain"] = authority.closed.model_dump(mode="json")
            if not facts["passed"] and "started" not in facts:
                try:
                    facts["startup_service_logs"] = preserve_closed_startup_logs(
                        parent,
                        root / "map-startup-service-logs",
                        c.controls.bind(
                            c.op.cleanup(
                                "map-startup-log-preservation",
                                now=datetime.now(timezone.utc),
                                seconds=30,
                            )
                        ),
                    )
                except BaseException as diagnostic_error:
                    # Keep the original start failure and this separate capture error.
                    facts["startup_service_log_capture_error"] = describe_error(
                        diagnostic_error
                    ).model_dump(mode="json")
        safe = facts["passed"] and authority.closed is not None
        if safe:
            assert parent.resolve(strict=True) == parent and not parent.is_symlink()
            shutil.rmtree(parent)
        facts["private_root_removed"] = safe and not parent.exists()
        (root / "map-source-facts.json").write_text(json.dumps(facts, indent=2) + "\n")
