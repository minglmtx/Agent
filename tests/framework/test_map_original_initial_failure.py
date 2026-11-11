"""Read original failure facts only: native auto-pan, no Actor, three closed domains."""

import json
from pathlib import Path
from lab_generate_skill.domain.lifecycle import ResourceRecord
from lab_generate_skill.domain.browser_resource import BrowserResourceSpec
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.map_browser_initialization import MapNativeInitialization
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.sites.map.initial_readiness_rules import original_readiness
from lab_generate_skill.sites.map.native_view_rules import original_document
from source_review_records import ReadOnlyEvidence, raw_json
from source_review_browser import review_browser_initial
from test_slurm_commands import guard

ROOT = Path(
    "/anvme/workspace/r102bf10-lab-generate-skill/experiments/framework-map-intake-20261029-v1/check-4851453"
)


def test_original_ready_auto_pan_closed_before_actor_and_preserved_failure() -> None:
    store = ReadOnlyEvidence(ROOT / "map-actor-native/resource/evidence")
    control = guard(60)
    actor_bytes = (ROOT / "map-actor-native/facts.json").read_bytes()
    actor = json.loads(actor_bytes)
    site_path = Path(actor["site_facts_path"])
    site_bytes = site_path.read_bytes()
    site = json.loads(site_bytes)
    assert actor["actor"] == {} and actor["paid_calls"] == 0
    assert "started" in site and "preparation_records" in site
    assert not site["passed"] and not site["private_root_removed"]
    assert "prepared_browser" not in site and "restored" not in site
    browser_root = site_path.parent / "browser"
    actor_record = json.loads(
        next(
            (ROOT / "map-actor-native/resource/journal").glob("*.resource.json")
        ).read_bytes()
    )
    browser_record = json.loads(
        next((browser_root / "journal").glob("*.resource.json")).read_bytes()
    )
    browser_config = None
    observed = None
    for role, value in [
        ("actor", actor_record),
        ("browser", browser_record),
        ("site", site["resource_record"]),
    ]:
        record = ResourceRecord.model_validate_json(json.dumps(value))
        assert record.token.resource_kind == role
        assert [e.state for e in record.events] == [
            "registered",
            "acquiring",
            "acquired",
            "closing",
            "closed",
        ]
        acquisition = raw_json(store, record.events[1].evidence[0], control)
        acquired = raw_json(store, record.events[2].evidence[0], control)
        ended = raw_json(store, record.events[-1].evidence[0], control)
        assert (
            acquired["token"]
            == ended["token"]
            == acquisition["token"]
            == record.token.model_dump(mode="json")
        )
        assert (
            acquired["spec_sha256"]
            == ended["spec_sha256"]
            == acquisition["configuration_ref"]["sha256"]
        )
        ending = ended if role == "actor" else ended["details"]
        if role == "browser":
            config = raw_json(store, acquisition["configuration_ref"], control)
            started = review_browser_initial(
                config, acquired, ending, record.events[2].evidence[0], store, control
            ).model_dump(mode="json")
        else:
            started = (
                acquired["step"] if role == "actor" else acquired["details"]["ready"]
            )
        target = (
            started["controller"]["target"]
            if role != "browser"
            else started["step"]["controller"]["target"]
        )
        closed = ending["step_closed"]
        assert (
            closed["target"] == target
            and closed["quiescence"]["original"] == target["worker"]
        )
        assert closed["quiescence"]["writer_status"] in ("missing", "reused")
        assert ending["primary"]["type_name"] == "AssertionError"
        assert (
            ending["cleanup_errors"] == []
            and ending["termination"]["state"] == "reaped"
        )
        assert ending["termination"]["cleanup_errors"] == []
        raw = raw_json(store, closed["evidence"], control)
        assert raw["phase"] == "closed" and raw["target"] == target and raw["kernel"]
        assert raw["error"] is None and raw["commands"]
        assert all(c["complete"] and c["returncode"] == 0 for c in raw["commands"])
        if role == "browser":
            browser_config = BrowserResourceSpec.model_validate_json(
                store.read(
                    EvidenceRef.model_validate(acquisition["configuration_ref"]),
                    control,
                )
            )
            observed = ending["last_readout"]["observation"]
    assert browser_config is not None and observed is not None
    initialization = browser_config.configuration.initialization
    assert isinstance(initialization, MapNativeInitialization)
    task: PublicTask = browser_config.configuration.spec.task
    assert observed["sequence"] == 0 and observed["state"] == "ready"
    actual = observed["tabs"][0]["url"]
    assert task.start_url.endswith("#map=15/40.7695/-73.9738")
    assert actual.endswith("#map=14/40.7695/-73.9738") and actual != task.start_url
    assert original_document(task, actual)
    readiness = browser_root / "complete-files/working/map-initial-readiness.json"
    proof = original_readiness(readiness.read_bytes(), initialization, task)
    assert proof["native_view"]["path"] == actual.removeprefix("http://127.0.0.1:23062")
    assert proof["native_view"]["native_geo_uri"] == "geo:40.7695,-73.9738?z=14"
    assert proof["new_observation_created"] is False
    assert (ROOT / "map-actor-native/facts.json").read_bytes() == actor_bytes
    assert site_path.read_bytes() == site_bytes
