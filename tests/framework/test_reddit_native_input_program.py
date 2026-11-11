"""Original PHP receiving large private ranges through the current small stdin."""

import json
from pathlib import Path
import pytest
from lab_generate_skill.adapters.processes.commands import ProcessRunner
from lab_generate_skill.adapters.processes.native_input_commands import (
    CheckedNativeInputCommands,
)
from lab_generate_skill.adapters.processes.capture import CommandFailure
from lab_generate_skill.adapters.sites.reddit_read_inputs import NativeReadInputs
from lab_generate_skill.sites.reddit.native_input_program import READ_INPUT
from lab_generate_skill.sites.reddit.service_commands import container
from reddit_native_program_fixture import prepare, OriginalImageCommands
from test_reddit_native_read_inputs import request
from site_instance_fixtures import node_path as node_path
from test_slurm_commands import guard

RESULT = READ_INPUT + r"""
$value=reddit_read_selector();$p=$value['baseline_payload'];
echo json_encode(['mode'=>$value['selector']['mode'],'count'=>$p['count']??null,'ranges'=>isset($p)?count($p['ranges']):null,'database_started'=>false],JSON_THROW_ON_ERROR);
"""


def test_receiver_fixture_small_selector_contains_no_raw_baseline_ranges(
    node_path: Path,
) -> None:
    selected = prepare(node_path)
    store = NativeReadInputs(selected.native_input_root)
    req = request()
    result = store.publish(
        req, tuple((i * 2 + 1, i * 2 + 1) for i in range(2000)), 2000, guard(5)
    )
    payload = dict(
        mode="capture",
        task=req.task.model_dump(mode="json"),
        username="native-user",
        forum="EarthPorn",
        baseline=result.model_dump(mode="json"),
    )
    raw = json.dumps(payload).encode()
    assert len(raw) < 8192 and result.size_bytes > 8192 and "ranges" not in payload
    assert b'"ranges"' not in raw
    assert selected.native_input_root + ":/native-input:ro" in container(
        selected, seeded=False, native_input=True
    )


@pytest.mark.parametrize("mode", ["reference", "capture"])
def test_actual_original_php_receives_only_original_scoped_baseline(
    node_path: Path, mode: str
) -> None:
    selected = prepare(node_path)
    req = request()
    ref = None
    if mode == "capture":
        store = NativeReadInputs(selected.native_input_root)
        ref = store.publish(
            req, tuple((i * 2 + 1, i * 2 + 1) for i in range(2000)), 2000, guard(5)
        )
        store.verify(ref, guard(5))
    payload = dict(
        mode=mode,
        task=req.task.model_dump(mode="json"),
        username="native-user",
        forum="EarthPorn",
        baseline=ref.model_dump(mode="json") if ref else None,
    )
    argv = container(selected, seeded=False, native_input=mode == "capture") + (
        "/usr/local/bin/php",
        "-r",
        RESULT,
    )
    argv = OriginalImageCommands(selected).command(argv)
    reply = CheckedNativeInputCommands(ProcessRunner()).run_input(
        argv, json.dumps(payload).encode(), guard(30)
    )
    assert json.loads(reply) == dict(
        mode=mode,
        count=2000 if ref else None,
        ranges=2000 if ref else None,
        database_started=False,
    )


@pytest.mark.parametrize(
    "kind",
    [
        "wrong-task",
        "wrong-hash",
        "wrong-size",
        "missing-file",
        "bad-mode",
        "bool-size",
    ],
)
def test_actual_original_php_rejects_wrong_input_before_any_database(
    node_path: Path, kind: str
) -> None:
    selected = prepare(node_path)
    req = request()
    store = NativeReadInputs(selected.native_input_root)
    ref = store.publish(req, ((1, 2),), 2, guard(5))
    baseline = ref.model_dump(mode="json")
    payload = dict(
        mode="capture",
        task=req.task.model_dump(mode="json"),
        username="native-user",
        forum="EarthPorn",
        baseline=baseline,
    )
    if kind == "wrong-task":
        baseline["task"]["source_task_id"] = "different-source"
    elif kind == "wrong-hash":
        baseline["sha256"] = "e" * 64
    elif kind == "wrong-size":
        baseline["size_bytes"] += 1
    elif kind == "missing-file":
        (node_path / "native-input" / ref.filename).unlink()
    elif kind == "bad-mode":
        payload["mode"] = "unknown"
    else:
        baseline["size_bytes"] = True
    argv = container(selected, seeded=False, native_input=True) + (
        "/usr/local/bin/php",
        "-r",
        RESULT,
    )
    argv = OriginalImageCommands(selected).command(argv)
    with pytest.raises(CommandFailure):
        CheckedNativeInputCommands(ProcessRunner()).run_input(
            argv, json.dumps(payload).encode(), guard(30)
        )
