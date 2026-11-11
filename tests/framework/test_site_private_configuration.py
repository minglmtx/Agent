"""Explicit v5 private-artifact declaration before any site effects."""

import json
from pathlib import Path
import pytest
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.adapters.sites.worker_protocol import (
    SiteWorkerCommand,
    decode_command,
    MAX_PACKET,
)
from lab_generate_skill.adapters.processes.worker_identity import (
    current_process_identity,
)
from site_worker_fixtures import configuration, operation
from test_gitlab_private_evidence import c as c, Case


def gitlab(c: Case) -> SiteWorkerConfiguration:
    plan, context = c.transport.plan, c.transport.context
    return SiteWorkerConfiguration(
        site_id="gitlab",
        token=context.token,
        files=context.instance.files,
        apptainer="/usr/bin/apptainer",
        installation=plan.config.installation,
        private_evidence=plan,
    )


def test_explicit_private_plan_canonical_wire_repeat_and_no_effects(
    c: Case, tmp_path: Path
) -> None:
    before = {str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")}
    config = gitlab(c)
    for _ in range(2):
        assert (
            SiteWorkerConfiguration.model_validate_json(config.model_dump_json())
            == config
        )
        command = SiteWorkerCommand(
            session_id="original-site",
            sequence=1,
            phase="configure",
            operation=operation(config),
            remaining_seconds=30.0,
            controller=current_process_identity(),
            configuration=config,
        )
        assert decode_command(command.model_dump_json().encode()) == command
        assert command.schema_version == "site-worker-command/8"
        assert len(command.model_dump_json().encode()) < MAX_PACKET
    assert before == {str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")}


@pytest.mark.parametrize("site", ["shopping_admin", "shopping"])
def test_existing_sites_explicitly_do_not_request_new_private_storage(
    site: str,
) -> None:
    data = configuration().model_dump(mode="json")
    data["site_id"] = site
    value = SiteWorkerConfiguration.model_validate_json(json.dumps(data))
    assert value.private_evidence is None and value.token.provider_version == "6"
    assert '"private_evidence":null' in value.model_dump_json()


@pytest.mark.parametrize(
    "change",
    [
        "missing_plan",
        "null_plan",
        "wrong_type",
        "foreign_owner",
        "old_configuration",
        "old_provider",
        "foreign_site",
        "extra",
    ],
)
def test_invalid_or_undeclared_private_scope_rejected(
    c: Case, tmp_path: Path, change: str
) -> None:
    config = gitlab(c)
    data = config.model_dump(mode="json")
    before = {str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")}
    if change == "missing_plan":
        data.pop("private_evidence")
    elif change == "null_plan":
        data["private_evidence"] = None
    elif change == "wrong_type":
        data["private_evidence"] = False
    elif change == "foreign_owner":
        data["token"]["owner"]["owner_id"] = "foreign"
    elif change == "old_configuration":
        data["schema_version"] = "site-worker-configuration/4"
    elif change == "old_provider":
        data["token"]["provider_version"] = "4"
    elif change == "foreign_site":
        data["site_id"] = "shopping"
    else:
        data["implicit_storage_fallback"] = True
    expected_error = OwnershipConflict if change == "foreign_owner" else ValueError
    with pytest.raises(expected_error):
        SiteWorkerConfiguration.model_validate_json(json.dumps(data))
    assert before == {str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")}


def test_old_site_wire_not_inferred_from_new_configuration(c: Case) -> None:
    config = gitlab(c)
    command = SiteWorkerCommand(
        session_id="original-site",
        sequence=1,
        phase="configure",
        operation=operation(config),
        remaining_seconds=30.0,
        controller=current_process_identity(),
        configuration=config,
    )
    data = command.model_dump(mode="json")
    data["schema_version"] = "site-worker-command/6"
    with pytest.raises(ValueError):
        decode_command(json.dumps(data).encode())
