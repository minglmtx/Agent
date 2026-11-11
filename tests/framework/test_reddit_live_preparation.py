"""Pure installed-source plan/preparation boundaries; no site/model execution."""

from pathlib import Path
from typing import Any
import pytest
from lab_generate_skill.domain.native_private_json import REDDIT_PRIVATE_JSON
from lab_generate_skill.domain.site_worker import SiteWorkerConfiguration
from lab_generate_skill.sites.reddit.tasks.image_spec import NativeImageSpec
from lab_generate_skill.sites.reddit.tasks.image_policy import image_initial_spec
from reddit_preparation_native import RedditPreparation
from reddit_site_native_plan import private_site_plan, native_configuration
from site_storage_fixtures import (
    private_configuration as original_private_configuration,
)
from site_resource_fixtures import resource_case
from site_worker_fixtures import configuration
from test_reddit_image_inputs import public_task
from test_slurm_commands import guard


def private_configuration(root: Path) -> SiteWorkerConfiguration:
    base = original_private_configuration(root)
    assert base.private_evidence is not None
    return native_configuration(
        base.installation,
        job_id=base.token.owner.job_id,
        parent=Path("/tmp/reddit-preparation-unit"),
        private_evidence=base.private_evidence.model_copy(
            update={"profile": REDDIT_PRIVATE_JSON}
        ),
    )


def test_actual_source_layout_is_canonical_unwrapped_and_unadmitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    c = resource_case(tmp_path, monkeypatch, config=private_configuration(tmp_path))
    native = RedditPreparation(
        c,
        "http://127.0.0.1:12001/",
        state_spec=image_initial_spec(public_task().identity),
    )
    spec = NativeImageSpec.model_validate_json(native.private_input_json())
    assert (
        spec == native.image_spec
        and native.native_contract_ref == spec.native_contract_ref
    )
    assert native.bindings.load(native.binding_ref, c.op) == native.binding
    assert (
        native.public.start_url == "http://127.0.0.1:12001/submit"
        and spec.admission == "unverified"
    )
    assert native.request is None and native.result is None
    assert not c.channels


@pytest.mark.parametrize(
    "endpoint",
    [
        "",
        None,
        1,
        [],
        "http://remote:12001/",
        "http://127.0.0.1:12001/-/profile/keys",
        "http://127.0.0.1:12001/?x=1",
    ],
)
def test_bad_start_is_refused_before_any_new_source_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    endpoint: Any,
) -> None:
    c = resource_case(tmp_path, monkeypatch, config=private_configuration(tmp_path))
    before = tuple(sorted((tmp_path / "evidence/blobs").iterdir()))
    with pytest.raises((TypeError, ValueError)):
        RedditPreparation(
            c, endpoint, state_spec=image_initial_spec(public_task().identity)
        )
    assert (
        tuple(sorted((tmp_path / "evidence/blobs").iterdir())) == before
        and not c.channels
    )


def test_original_private_plan_and_image_are_inert_before_registered_acquisition(
    tmp_path: Path,
) -> None:
    base = configuration(job_id="4752096")
    plan = private_site_plan(
        base.token.owner,
        base.installation,
        evidence_root=tmp_path / "evidence",
        session_root=tmp_path / "sessions",
        journal_root=tmp_path / "journal",
    )
    cfg = native_configuration(
        base.installation,
        job_id=base.token.owner.job_id,
        parent=Path("/tmp/reddit-predeclared-original"),
        private_evidence=plan,
    )
    assert SiteWorkerConfiguration.model_validate_json(cfg.model_dump_json()) == cfg
    assert cfg.private_evidence == plan and cfg.files.image.size_bytes == 43292033024
    assert (
        cfg.token.owner == plan.binding.owner
        and plan.config.capacity.max_exchanges >= 6
    )
    assert not list(tmp_path.iterdir())
    with pytest.raises(ValueError, match="original allocation job"):
        native_configuration(
            base.installation,
            job_id="999999",
            parent=Path("/tmp/foreign"),
            private_evidence=plan,
        )
    assert not list(tmp_path.iterdir())
