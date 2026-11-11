"""Check actual shared pages against every complete original field occurrence."""

from pydantic import JsonValue
from lab_generate_skill.domain.teacher_json import json_text, object_value
from lab_generate_skill.domain.teacher_projection import TeacherSharedPage
from lab_generate_skill.domain.context_transformation import (
    ContextChange,
    context_bytes_sha,
)
from lab_generate_skill.domain.errors import EvidenceIntegrityError


def fragment_sha(value: object) -> str:
    return context_bytes_sha(json_text(value).encode())


def layout_change(
    source_path: str, target_path: str, original: object, actual: object, reason: str
) -> ContextChange:
    return ContextChange(
        operation="layout",
        source_path=source_path,
        target_path=target_path,
        source_sha256=fragment_sha(original),
        target_sha256=fragment_sha(actual),
        related_source_paths=(),
        reason_code=reason,
    )


class CompletePageBindings:
    def __init__(self, pages: tuple[TeacherSharedPage, ...]) -> None:
        self.pages = pages
        self.seen: dict[str, tuple[str, str]] = {}
        self.changes: list[ContextChange] = []

    def check(self, reference: JsonValue, text: str, source_path: str) -> None:
        value = object_value(
            reference, "Complete original page requires direct shared reference"
        )
        if set(value) != {"page_ref"}:
            raise EvidenceIntegrityError("Only single-hop complete page refs allowed")
        if text not in self.seen:
            index = len(self.seen)
            if index >= len(self.pages):
                raise EvidenceIntegrityError("Missing complete original page")
            page = self.pages[index]
            expected = "p" + str(index)
            if page.page_id != expected or page.text != text:
                raise EvidenceIntegrityError(
                    "Full page text/order changed or duplicated"
                )
            self.seen[text] = (expected, source_path)
        pid, anchor = self.seen[text]
        if value["page_ref"] != pid:
            raise EvidenceIntegrityError(
                "Page reference changed its own original occurrence"
            )
        index = int(pid[1:])
        self.changes.append(
            ContextChange(
                operation="share_exact_body",
                source_path=source_path,
                target_path=f"/messages/1/content/pages/{index}/text",
                source_sha256=fragment_sha(text),
                target_sha256=fragment_sha(self.pages[index].text),
                related_source_paths=() if anchor == source_path else (anchor,),
                reason_code="EXACT_COMPLETE_PAGE_SHARED",
            )
        )

    def finish(self) -> None:
        if len(self.seen) != len(self.pages):
            raise EvidenceIntegrityError(
                "Unreferenced/new page material in Teacher view"
            )
