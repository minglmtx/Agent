"""Selected original contract and public input boundaries; no native effects."""

import base64
import hashlib
import json
from pathlib import Path
import struct
from typing import Any
import pytest
from lab_generate_skill.bootstrap.gitlab_ssh_key import load_ssh_key_inputs
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.errors import EvidenceIntegrityError
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.actor_prompt import ActorPublicTurn
from lab_generate_skill.domain.observation import ResolvedObservation
from lab_generate_skill.actor.prompting import prepare_actor
from lab_generate_skill.sites.gitlab.tasks.ssh_key_parameters import (
    canonical_public_key,
    SshKeyParameters,
)
from lab_generate_skill.sites.gitlab.tasks.ssh_key_spec import OUTPUT_REQUIREMENTS
from observation_fixtures import sample_observation
from test_actor_protocol import turn

FIXTURE = Path(__file__).parent / "fixtures/gitlab-profile-ssh-key-native.json"


def reference(raw: bytes, **updates: Any) -> EvidenceRef:
    return EvidenceRef(
        **{
            "uri": "cas:gitlab-ssh-native",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
            "media_type": "application/json",
            "content_schema": "gitlab-native-contract/1",
            "visibility": "private",
            "producer": "test",
            **updates,
        }
    )


def public_task(**updates: Any) -> PublicTask:
    n = json.loads(FIXTURE.read_bytes())
    # Independent original renderer spelling/layout; do not call new renderer.
    goal = (
        n["goal"]
        + "\n\nTask-supplied parameters:\n"
        + json.dumps(
            n["public_parameters"],
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    )
    return PublicTask(
        **{
            "identity": TaskIdentity(
                source_task_id=n["source_task_id"],
                task_id="gitlab-ssh-key-selected-v1",
                split="train",
                site="gitlab",
                family="profile_ssh_key",
                contract_version=1,
            ),
            "goal": goal,
            "start_url": "http://127.0.0.1:18080/",
            "allowed_actions": ("click", "fill", "send_msg_to_user"),
            "output_requirements": OUTPUT_REQUIREMENTS,
            **updates,
        }
    )


def test_original_exact_fixture_and_supplied_parameters_remain_unadmitted() -> None:
    raw = FIXTURE.read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == "80a583dc9bec473ce490af94ba9c03c4553cba9282336f4ab7854f29c22f4e30"
    )
    public = public_task()
    result = load_ssh_key_inputs(raw, reference(raw), public)
    assert (
        result.public_task == public and result.private_spec.admission == "unverified"
    )
    assert result.private_spec.parameters.title == "Skill Runtime Validation Key"
    assert (
        result.private_spec.parameters.public_key
        == "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAINdamAGCsQq31Uv+08lkBzoO4XLz2qYjJa8CGmj3B1Ea"
    )
    assert result.private_spec.native_contract_ref == reference(raw)
    assert load_ssh_key_inputs(raw, reference(raw), public) == result


def test_actual_actor_prompt_contains_approved_parameters_only_private_lineage_changes_do_not_leak() -> (
    None
):
    native = json.loads(FIXTURE.read_bytes())
    public = public_task()
    texts = []
    for marker in ("private-lineage-one", "private-lineage-two"):
        native["source_trace_ids"] = [marker]
        native["goal_revision"]["reason"] = marker
        raw = json.dumps(native).encode()
        result = load_ssh_key_inputs(raw, reference(raw), public)
        original = turn()
        obs = sample_observation(public.identity)
        prompt = prepare_actor(
            ActorPublicTurn(
                task=result.public_task,
                skill=original.skill,
                observation=ResolvedObservation(record=obs, text=obs.text),
                history=(),
                memory=original.memory,
            )
        )
        texts.append(prompt.model_dump_json())
        assert marker not in texts[-1] and "native_contract_ref" not in texts[-1]
        assert result.private_spec.parameters.public_key in texts[-1]
        assert result.private_spec.parameters.title in texts[-1]
    assert texts[0] == texts[1]


@pytest.mark.parametrize(
    "case",
    [
        "private_key",
        "truncated",
        "wrong_kind",
        "bad_length",
        "trailing_wire",
        "bad_base64",
        "multiline",
        "numeric_key",
        "empty_title",
        "newline_title",
        "bool_title",
        "extra_parameter",
        "missing_title",
        "public_input",
        "declaration",
        "protocol",
        "version",
        "source",
        "lineage",
        "heldout",
        "training",
        "equivalence",
        "bool_scope",
        "goal_revision",
        "trace_type",
        "trace_empty",
        "start_revision",
        "recorded_path",
        "recorded_credentials",
        "extra_root",
    ],
)
def test_invalid_native_input_rejected_before_any_resource(case: str) -> None:
    n = json.loads(FIXTURE.read_bytes())
    p = n["public_parameters"]
    if case == "private_key":
        p["public_key"] = "-----BEGIN OPENSSH PRIVATE KEY-----"
    elif case == "truncated":
        p["public_key"] = p["public_key"][:-4]
    elif case == "wrong_kind":
        p["public_key"] = p["public_key"].replace("ssh-ed25519", "ssh-rsa")
    elif case in ("bad_length", "trailing_wire"):
        wire = base64.b64decode(p["public_key"].split()[1])
        wire = (
            wire[:15] + struct.pack(">I", 31) + wire[19:]
            if case == "bad_length"
            else wire + b"x"
        )
        p["public_key"] = "ssh-ed25519 " + base64.b64encode(wire).decode()
    elif case == "bad_base64":
        p["public_key"] = "ssh-ed25519 !!!!"
    elif case == "multiline":
        p["public_key"] += "\ncomment"
    elif case == "numeric_key":
        p["public_key"] = 123
    elif case == "empty_title":
        p["title"] = " "
    elif case == "newline_title":
        p["title"] += "\nnext"
    elif case == "bool_title":
        p["title"] = False
    elif case == "extra_parameter":
        p["password"] = "private-not-allowed"
    elif case == "missing_title":
        del p["title"]
    elif case == "public_input":
        n["public_task_input"]["goal"] = "foreign"
    elif case == "declaration":
        n["gitlab_public_bridge"]["declaration"]["title"] = "foreign"
    elif case == "protocol":
        n["completion"] = {"family": "query"}
    elif case == "version":
        n["gitlab_public_bridge"]["version"] = "old"
    elif case == "source":
        n["source_task_id"] = "foreign"
    elif case == "lineage":
        n["task_id"] = "foreign--public-cpu-candidate-v1"
    elif case == "heldout":
        n["heldout_quarantine"] = True
    elif case == "training":
        n["eligible_for_training"] = True
    elif case == "equivalence":
        n["original_benchmark_equivalence"] = True
    elif case == "bool_scope":
        n["heldout_quarantine"] = 0
    elif case == "goal_revision":
        n["goal_revision"]["equivalent_to_original_goal"] = True
    elif case == "trace_type":
        n["source_trace_ids"] = [True]
    elif case == "trace_empty":
        n["source_trace_ids"] = []
    elif case == "start_revision":
        n["start_revision"] = {}
    elif case == "recorded_path":
        n["recorded_start_paths"][1] = "/foreign"
    elif case == "recorded_credentials":
        n["recorded_start_urls"][0] = "http://private:secret@localhost/"
    elif case == "extra_root":
        n["execute"] = "caller-program"
    raw = json.dumps(n).encode()
    with pytest.raises(EvidenceIntegrityError):
        load_ssh_key_inputs(raw, reference(raw), public_task())


@pytest.mark.parametrize(
    "case",
    [
        "missing_parameters",
        "wrong_key",
        "wrong_title",
        "remote",
        "path",
        "port",
        "query",
        "family",
        "split",
        "source",
        "terminal",
        "output",
    ],
)
def test_public_input_binding_mismatch_is_not_a_new_execution(case: str) -> None:
    public = public_task()
    values = public.model_dump()
    if case == "missing_parameters":
        values["goal"] = json.loads(FIXTURE.read_bytes())["goal"]
    elif case == "wrong_key":
        values["goal"] = public.goal.replace("B1Ea", "B1Eb")
    elif case == "wrong_title":
        values["goal"] = public.goal.replace("Validation Key", "Other Key")
    elif case == "remote":
        values["start_url"] = "http://example.invalid/"
    elif case == "path":
        values["start_url"] += "profile"
    elif case == "port":
        values["start_url"] = "http://127.0.0.1:80/"
    elif case == "query":
        values["start_url"] += "?x=1"
    elif case == "family":
        values["identity"]["family"] = "query"
    elif case == "split":
        values["identity"]["split"] = "test"
    elif case == "source":
        values["identity"]["source_task_id"] = "foreign"
    elif case == "terminal":
        values["allowed_actions"] = ("click",)
    elif case == "output":
        values["output_requirements"] = ()
    raw = FIXTURE.read_bytes()
    with pytest.raises(EvidenceIntegrityError):
        load_ssh_key_inputs(raw, reference(raw), PublicTask.model_validate(values))


@pytest.mark.parametrize(
    "case", ["wrong_hash", "public_ref", "wrong_schema", "duplicate_json", "not_bytes"]
)
def test_original_reference_and_bounded_decoder_boundary(case: str) -> None:
    raw: Any = FIXTURE.read_bytes()
    ref = reference(raw)
    if case == "wrong_hash":
        ref = reference(raw, sha256="0" * 64)
    elif case == "public_ref":
        ref = reference(raw, visibility="public")
    elif case == "wrong_schema":
        ref = reference(raw, content_schema="shopping-native-contract/1")
    elif case == "duplicate_json":
        raw = b'{"domain":"gitlab","domain":"gitlab"}'
        ref = reference(raw)
    elif case == "not_bytes":
        raw = bytearray(raw)
    with pytest.raises(EvidenceIntegrityError):
        load_ssh_key_inputs(raw, ref, public_task())


def test_complete_public_wire_comment_and_native_title_preserved() -> None:
    n = json.loads(FIXTURE.read_bytes())
    key = n["public_parameters"]["public_key"]
    parameters = SshKeyParameters(
        public_key=key + " public-comment", title="  explicit title  "
    )
    assert (
        parameters.public_key == key + " public-comment"
        and parameters.title == "  explicit title  "
    )
    assert canonical_public_key(parameters.public_key) == key
