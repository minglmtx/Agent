"""Pure semantic check over explicitly synthetic Shopping initial-return facts."""

import hashlib
import json
from pathlib import Path
import pytest
from lab_generate_skill.domain.initial_observation import InitialObservationInputs
from lab_generate_skill.domain.errors import OwnershipConflict
from lab_generate_skill.sites.shopping.tasks.order_eta_initial_observation import (
    OrderEtaInitialObservationChecks,
)
from lab_generate_skill.sites.shopping.tasks.order_eta_policy import (
    order_eta_initial_spec,
)
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.browser_worker_acquisition import (
    BrowserWorkerAcquiredFact,
)
from initial_observation_fixtures import initial_case
from test_shopping_order_eta_inputs import public_task
from test_slurm_commands import guard


@pytest.mark.parametrize(
    "fault",
    [
        "none",
        "action_error",
        "wrong_url",
        "empty",
        "terminal",
        "extra_tab",
        "wrong_preparation",
    ],
)
def test_unique_customer_initial_view_and_rejected_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    # The old fixture supplies common immutable container shapes and synthetic
    # process IDs only. These replaced frames are never published as real CAS or
    # used to authorize a site, browser or Actor.
    with initial_case(tmp_path, monkeypatch) as c:
        original = c.records.reader.load(c.selection, c.op, guard())
        data = original.model_dump(mode="json")
        public = public_task(start_url="http://127.0.0.1:12001/customer/account/")
        scope = {
            **data["prepared"]["scope"],
            "task": public.identity.model_dump(mode="json"),
        }
        data["prepared"].update(scope=scope, public_task=public.model_dump(mode="json"))
        data["spec"] = order_eta_initial_spec(public.identity).model_dump(mode="json")
        config = data["browser"]["configuration"]
        config["spec"].update(scope=scope, task=public.model_dump(mode="json"))
        selected = config["initialization"]
        config["initialization"] = {
            **selected,
            "kind": "shopping_order_eta",
            "endpoint": "http://127.0.0.1:12001/",
        }
        data["returned"]["scope"] = scope
        view = data["observation"]["record"]
        view.update(
            task=public.identity.model_dump(mode="json"),
            text="Synthetic customer account",
            text_ref=None,
            artifacts=[],
        )
        view["tabs"][0]["url"] = public.start_url
        data["observation"]["text"] = view["text"]
        if fault == "action_error":
            view["last_action_error"] = "original browser error"
        elif fault == "wrong_url":
            view["tabs"][0]["url"] = "http://127.0.0.1:12001/customer/account/login/"
        elif fault == "empty":
            view["text"] = ""
            data["observation"]["text"] = ""
        elif fault == "terminal":
            data["returned"]["protocol_terminal"] = True
        elif fault == "extra_tab":
            view["tabs"].append({**view["tabs"][0], "tab_id": "another"})
        elif fault == "wrong_preparation":
            config["initialization"]["prepared_ref"]["producer"] = "other"
        data["returned"]["observation"] = view
        resource = BrowserResourceSpec.model_validate_json(json.dumps(data["browser"]))
        data["acquired"]["spec_sha256"] = hashlib.sha256(
            resource.model_dump_json().encode()
        ).hexdigest()
        data["worker_acquired"]["spec_sha256"] = data["acquired"]["spec_sha256"]
        worker_bytes = (
            BrowserWorkerAcquiredFact.model_validate_json(
                json.dumps(data["worker_acquired"])
            )
            .model_dump_json()
            .encode()
        )
        digest = hashlib.sha256(worker_bytes).hexdigest()
        data["acquired"]["details"]["worker_acquired_ref"].update(
            sha256=digest, uri="cas://sha256/" + digest, size_bytes=len(worker_bytes)
        )
        inputs = InitialObservationInputs.model_validate_json(json.dumps(data))
        checks = OrderEtaInitialObservationChecks()
        if fault == "wrong_preparation":
            with pytest.raises(OwnershipConflict):
                checks.check(inputs, guard())
        else:
            result = checks.check(inputs, guard())
            assert result.status == ("pass" if fault == "none" else "fail")
