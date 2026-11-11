"""Original separately selected contract; no replay of the prior unknown source."""

import json
from pathlib import Path
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.domain.identity import TaskIdentity
from lab_generate_skill.sites.reddit.tasks.image_spec import OUTPUT_REQUIREMENTS
from lab_generate_skill.sites.reddit.tasks.image_parameters import (
    ImageParameters,
    render_public_goal,
)
from lab_generate_skill.domain.reddit_browser_initialization import (
    RedditNativeImageInitialization,
)
from reddit_browser_initialization_fixtures import selection

CONTRACT = Path(
    "/anvme/workspace/r102bf10-lab-generate-skill/experiments/sft-reddit-native-media-formal-integration-v1/bound/bindings/contracts/dbab57fbe44ffe3192ec.json"
)


def public(endpoint: str = "http://127.0.0.1:18080/") -> PublicTask:
    raw = json.loads(CONTRACT.read_bytes())
    return PublicTask(
        identity=TaskIdentity(
            source_task_id=raw["source_task_id"],
            task_id=raw["task_id"],
            split="train",
            site="reddit",
            family="native_image_submission",
            contract_version=1,
        ),
        goal=render_public_goal(
            raw["goal"], ImageParameters.model_validate(raw["public_parameters"])
        ),
        start_url=endpoint + "forums/all",
        allowed_actions=("click", "fill", "upload_file", "send_msg_to_user"),
        output_requirements=OUTPUT_REQUIREMENTS,
    )


def selected() -> RedditNativeImageInitialization:
    old = selection()
    files = old.task_files.model_copy(
        update={
            "scope": old.task_files.scope.model_copy(update={"task": public().identity})
        }
    )
    return RedditNativeImageInitialization.model_validate(
        old.model_copy(update={"task_files": files})
    )
