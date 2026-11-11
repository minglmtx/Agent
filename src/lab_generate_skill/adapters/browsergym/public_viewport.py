"""Project only public AX IDs from the same native BrowserGym observation.

Geometry and screenshot dimensions originate in one _get_obs return. We do not
evaluate the page again, infer visibility from text order, or publish raw DOM.
"""

import hashlib
import re
from typing import Any

from lab_generate_skill.domain.observation import Observation, ObservationArtifact
from lab_generate_skill.domain.observation_viewport import (
    ObservationViewport,
    ViewportBox,
    ViewportElement,
    VIEWPORT_NAME,
)


def public_viewport(
    raw: dict[str, Any], observed: Observation
) -> tuple[Observation, ObservationViewport]:
    if observed.text is None or observed.active_tab_id is None:
        raise ValueError("Viewport requires this complete inline public AX capture")
    shape = raw["screenshot"].shape
    if len(shape) != 3 or shape[2] != 3:
        raise ValueError("Native viewport RGB screenshot dimensions required")
    ids = sorted(set(re.findall(r"^\t*\[([^\]]+)\] ", observed.text, re.MULTILINE)))
    properties = raw["extra_element_properties"]
    elements = []
    for node_id in ids:
        captured = properties.get(node_id, {})
        box = captured.get("bbox")
        if box is not None and len(box) != 4:
            raise ValueError("Complete native x/y/width/height required")
        elements.append(
            ViewportElement(
                node_id=node_id,
                visibility=captured.get("visibility"),
                box=(
                    None
                    if box is None
                    else ViewportBox(x=box[0], y=box[1], width=box[2], height=box[3])
                ),
            )
        )
    viewport = ObservationViewport(
        observation_id=observed.observation_id,
        task=observed.task,
        context_id=observed.context_id,
        attempt_id=observed.attempt_id,
        sequence=observed.sequence,
        captured_at=observed.captured_at,
        tab_id=observed.active_tab_id,
        active_url=next(
            tab.url for tab in observed.tabs if tab.tab_id == observed.active_tab_id
        ),
        text_sha256=hashlib.sha256(observed.text.encode()).hexdigest(),
        width=int(shape[1]),
        height=int(shape[0]),
        elements=tuple(elements),
    )
    result = Observation.model_validate(
        observed.model_copy(
            update={
                "artifacts": (
                    *observed.artifacts,
                    ObservationArtifact(
                        name=VIEWPORT_NAME, reference=viewport.reference
                    ),
                )
            }
        )
    )
    viewport.require_observation(result)
    return result, viewport
