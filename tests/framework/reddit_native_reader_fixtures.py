"""Explicit synthetic PDO envelopes, current spec and private file inputs."""

from copy import deepcopy
import json
from pathlib import Path
from lab_generate_skill.bootstrap.reddit_native_image import load_image_inputs
from lab_generate_skill.adapters.sites.reddit_read_inputs import NativeReadInputs
from lab_generate_skill.ports.lifecycle import OperationControl
from lab_generate_skill.domain.reddit_native_read_input import BaselineIdsRef
from lab_generate_skill.sites.reddit.native_schema import NativeMedia
from lab_generate_skill.sites.reddit.native_reader import RedditNativeReader
from lab_generate_skill.sites.reddit.tasks.image_spec import NativeImageSpec
from reddit_services_fixtures import spec
from reddit_image_state_fixtures import reference_data, posted_data
from test_reddit_image_inputs import FIXTURE, reference, public_task
from test_reddit_native_read_inputs import request


def private_spec() -> NativeImageSpec:
    raw = FIXTURE.read_bytes()
    return load_image_inputs(raw, reference(raw), public_task()).private_spec


class Commands:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], bytes]] = []
        self.reply: bytes | None = None
        self.failure: BaseException | None = None

    def run_input(
        self, argv: tuple[str, ...], data: bytes, control: OperationControl
    ) -> bytes:
        control.checkpoint()
        self.calls.append((argv, data))
        if self.failure is not None:
            raise self.failure
        if self.reply is not None:
            return self.reply
        selector = json.loads(data)
        initial = reference_data()
        mode = selector["mode"]
        capture = deepcopy(initial["capture"]) if mode == "reference" else posted_data()
        del capture["native_media"]
        header = (
            {k: v for k, v in initial.items() if k != "capture"}
            if mode == "reference"
            else None
        )
        return json.dumps(
            dict(
                schema_version="reddit-native-database-capture/1",
                task=selector["task"],
                mode=mode,
                reference=header,
                capture=capture,
            )
        ).encode()


class Media:
    def __init__(self) -> None:
        self.value = NativeMedia.model_validate_json(
            json.dumps(reference_data()["capture"]["native_media"])
        )
        self.failure: BaseException | None = None

    def capture(self, control: OperationControl) -> NativeMedia:
        control.checkpoint()
        if self.failure is not None:
            raise self.failure
        return self.value


def case(
    root: Path,
) -> tuple[
    RedditNativeReader,
    Commands,
    Media,
    NativeImageSpec,
    NativeReadInputs,
    BaselineIdsRef,
]:
    selected = spec(root)
    commands = Commands()
    media = Media()
    inputs = NativeReadInputs(selected.native_input_root)
    current = private_spec()
    original = request().model_copy(update={"task": current.task})
    from test_slurm_commands import guard

    baseline = inputs.publish(original, ((1, 2),), 2, guard(5))
    return (
        RedditNativeReader(selected, commands, inputs, media),
        commands,
        media,
        current,
        inputs,
        baseline,
    )
