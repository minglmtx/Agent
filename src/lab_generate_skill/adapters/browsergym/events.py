"""Bounded private event buffer attached before task navigation.

Response action_id stays null: asynchronous responses are not falsely assigned
by their arrival time. This captures URL/status, not bodies or download bytes.
Callback failures persist until close; browser event dispatch cannot swallow them.
"""

from typing import Any, Literal
from lab_generate_skill.domain.browser_session import BrowserRuntimeEvent


class BrowserEvents:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.events: list[BrowserRuntimeEvent] = []
        self.error: BaseException | None = None
        self.context: Any = None

    def add(
        self,
        kind: Literal[
            "before_navigation", "response", "before_action", "after_action", "terminal"
        ],
        *,
        action_id: str | None = None,
        url: str | None = None,
        status: int | None = None,
    ) -> None:
        self.check()
        if len(self.events) >= self.limit:
            self.error = RuntimeError(
                "Browser event capacity exceeded; capture is incomplete"
            )
            raise self.error
        self.events.append(
            BrowserRuntimeEvent(
                sequence=len(self.events),
                kind=kind,
                action_id=action_id,
                url=url,
                status=status,
            )
        )

    def response(self, response: Any) -> None:
        try:
            self.add("response", url=response.url, status=response.status)
        except BaseException as error:
            self.error = error

    def attach(self, context: Any) -> None:
        if self.context is not None:
            raise RuntimeError("Browser capture is already attached")
        self.context = context
        context.on("response", self.response)

    def check(self) -> None:
        if self.error is not None:
            raise self.error

    def close(self) -> None:
        if self.context is not None:
            self.context.remove_listener("response", self.response)
            self.context = None
