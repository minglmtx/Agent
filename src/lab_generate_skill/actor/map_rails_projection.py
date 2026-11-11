"""Explicit selected MapData diagnostic-page view; healthy pages keep full AX."""

from urllib.parse import urlsplit
from lab_generate_skill.domain.actor_prompt import ActorPublicTurn, ActorPrompt
from lab_generate_skill.domain.actor_projection import (
    MapRailsDiagnosticProjection,
    MapRailsAddressableProjection,
    actor_projection_configuration,
    check_projection_task,
)
from .prompting import prepare_actor
from .message_layout import actor_messages
from .rails_diagnostic_ax import diagnostic_ax_view

SCOPE = (
    "\n\nAX scope: every named cell/control node and its attributes are preserved; "
    "repeated non-addressable StaticText leaves already present on an ancestor "
    "cell or rendered text are omitted; empty rows, rowgroups and paragraphs "
    "have no target IDs. All cell/control IDs, values, attributes and tree depth "
    "are preserved."
)

ADDRESSABLE_SCOPE = (
    "\n\nAX scope v2: every original target ID, including empty rows, rowgroups "
    "and paragraphs, is preserved with its name, values, attributes and depth. "
    "Only ID-free StaticText leaves exactly repeated on an ancestor cell or "
    "rendered text are omitted. Space indentation retains original tree depth. "
    "An ID identifies a possible action target; it does not prove an action "
    "is valid or will succeed."
)


class MapRailsActorProjection:
    def __init__(
        self,
        configuration: MapRailsDiagnosticProjection | MapRailsAddressableProjection,
    ) -> None:
        checked = actor_projection_configuration(configuration)
        if not isinstance(
            checked, (MapRailsDiagnosticProjection, MapRailsAddressableProjection)
        ):
            raise TypeError("Explicit Map diagnostic version required")
        self.configuration = checked

    def __call__(self, turn: ActorPublicTurn) -> ActorPrompt:
        turn = ActorPublicTurn.model_validate(turn)
        check_projection_task(self.configuration, turn.task.identity)
        current = next(
            tab
            for tab in turn.observation.record.tabs
            if tab.tab_id == turn.observation.record.active_tab_id
        )
        origin = urlsplit(turn.task.start_url)
        text = turn.observation.text
        assert text is not None
        if not (
            current.title == "Action Controller: Exception caught"
            and current.url == f"{origin.scheme}://{origin.netloc}/map"
            and origin.scheme == "http"
            and origin.hostname == "127.0.0.1"
            and origin.port is not None
            and 1024 <= origin.port <= 65535
            and text.startswith("RootWebArea 'Action Controller: Exception caught'")
            and "heading 'Routing Error'" in text
            and "heading 'No route matches [GET] \"/map\"'" in text
            and "heading 'Routes'" in text
        ):
            return prepare_actor(turn)
        preserve_ids = isinstance(self.configuration, MapRailsAddressableProjection)
        view = diagnostic_ax_view(text, preserve_ids=preserve_ids)
        return ActorPrompt(
            prompt_version=(
                "browsergym-map-rails-diagnostic-ax-v2"
                if preserve_ids
                else "browsergym-map-rails-diagnostic-ax-v1"
            ),
            messages=actor_messages(
                turn, view.text + (ADDRESSABLE_SCOPE if preserve_ids else SCOPE)
            ),
        )
