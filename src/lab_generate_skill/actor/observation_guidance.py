"""Short current-view facts; model instructions never infer unseen page content."""

from lab_generate_skill.domain.actor_prompt import ActorPublicTurn
from lab_generate_skill.domain.observation_read import ObservationReadPayload
from lab_generate_skill.policies.observation_display import observation_read_body


def shared_observation_rules(tools: tuple[str, ...]) -> str:
    rules = [
        "Use sufficient displayed information directly. Unshown does not mean absent.",
    ]
    if tools:
        choices = []
        if "list_regions" in tools:
            choices.append("list the captured directory")
        if "search_regions" in tools:
            choices.append("search captured text")
        if "read_region" in tools:
            choices.append(
                "read captured ranges; known region_ids can be read directly"
            )
        rules.append(
            "When needed, " + "; ".join(choices) + ". Do not reread sufficient content."
        )
        rules.append(
            "Reads do not expand the webpage. Access unloaded or collapsed content through task-relevant controls, then use the new observation."
        )
    else:
        rules.append(
            "Access unloaded or collapsed content through task-relevant controls, then use the new observation."
        )
    if "search_regions" in tools:
        rules.append(
            "Search covers only its declared snapshot/regions. No match does not prove absence across the website."
        )
    rules.append(
        "Actions use current observed bids. "
        + (
            "Reads use current public region_ids. Do not invent or interchange them."
            if tools
            else "Do not invent element IDs."
        )
    )
    rules.append(
        "A rejected proposal was not executed. Correct the reported parameters; do not repeat invalid ones. Do not use submit, delete or purchase as generic probes."
    )
    return "\n".join(rules)


def current_observation_body(
    turn: ActorPublicTurn,
    *,
    full_body: str | None = None,
    window: ObservationReadPayload | None = None,
    viewport_applied: bool = False,
) -> str:
    source = turn.observation_source
    if source is None or turn.observation.text is None:
        raise ValueError("Actual public source and captured text required")
    if (full_body is None) == (window is None):
        raise ValueError("Exactly one actual full or local representation required")
    if window is None:
        if viewport_applied:
            raise ValueError("A complete view cannot claim viewport selection")
        assert full_body is not None
        return (
            "# Current view\n"
            "Complete captured content is displayed; other pages and unloaded content are excluded.\n"
            "Displayed: the complete captured text below.\n"
            "Captured but unshown: none.\n"
            "Uncaptured/pending content: unknown.\n"
            + (
                "Current snapshot_sha256: "
                + source.snapshot.observation_ref.sha256
                + "\n"
                if source.tools
                else ""
            )
            + full_body
        )
    if window.request.snapshot != source.snapshot or not source.tools:
        raise ValueError(
            "Local display requires its original snapshot and actual readers"
        )
    return observation_read_body(
        window,
        current_view="viewport_priority" if viewport_applied else "structural_local",
        captured_length=len(turn.observation.text),
        read_tools=source.tools,
    )
