"""Pure source coordinates for one verified public tab AX snapshot.

This is structural indexing, not a registered reader, token fit, website action,
permission check or model-understanding proof. Native/code/spatial adapters must
declare their own supported source representation before using other schemas.
"""

from bisect import bisect_right
from dataclasses import dataclass, replace
import hashlib
import re
import unicodedata
from lab_generate_skill.domain.errors import EvidenceIntegrityError, OwnershipConflict
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.observation import Observation, ResolvedObservation
from lab_generate_skill.domain.observation_viewport import (
    ObservationViewport,
    viewport_reference,
)
from lab_generate_skill.domain.observation_read import (
    PublicObservationSnapshot,
    ObservationRegion,
    ObservationRegionRange,
    ObservationSourceSpan,
    ObservationReadFragment,
    ObservationOverview,
)
from lab_generate_skill.domain.observation_read_policy import ObservationReadPolicy
from lab_generate_skill.domain.state_scope import StateScope
from lab_generate_skill.domain.verified_evidence_body import VerifiedEvidenceBody

_NODE = re.compile(r"^(\t*)(?:\[([0-9]+)\] )?([A-Za-z][A-Za-z0-9_-]*)(?= |,|$)")
_TABLES = {"table", "grid", "treegrid"}


@dataclass(frozen=True)
class AxSourceNode:
    line: int
    end_line: int
    depth: int
    role: str
    node_id: str | None
    parent: int | None


@dataclass(frozen=True)
class ObservationIndex:
    snapshot: PublicObservationSnapshot
    policy: ObservationReadPolicy
    text: str
    lines: tuple[str, ...]
    offsets: tuple[int, ...]
    nodes: tuple[AxSourceNode, ...]
    regions: tuple[ObservationRegion, ...]
    overview: ObservationOverview
    mandatory_context: tuple[ObservationReadFragment, ...] = ()
    viewport: ObservationViewport | None = None

    def require_snapshot(self, snapshot: PublicObservationSnapshot) -> None:
        if PublicObservationSnapshot.model_validate(snapshot) != self.snapshot:
            raise OwnershipConflict(
                "Read changed original snapshot/scope/tab/frame/policy"
            )

    def mandatory_fragments(self) -> tuple[ObservationReadFragment, ...]:
        return self.mandatory_context

    def capture_mandatory_context(self) -> tuple[ObservationReadFragment, ...]:
        """Called once while building this immutable index, never by each reader."""
        required: dict[ObservationSourceSpan, ObservationReadFragment] = {}
        for node in self.nodes:
            # Only role/attribute structure outside quoted public labels is
            # interpreted; a code/comment string saying focused=True grants
            # neither focus nor an operation on that object.
            raw = self.lines[node.line]
            outside = []
            quote = None
            escaped = False
            for character in raw:
                if quote is not None:
                    if escaped:
                        escaped = False
                    elif character == "\\":
                        escaped = True
                    elif character == quote:
                        quote = None
                elif character in ("'", '"'):
                    quote = character
                else:
                    outside.append(character)
            focused = (
                re.search(
                    r"(?:^|[, ])focused(?:=True)?(?=[, \r\n]|$)", "".join(outside)
                )
                is not None
            )
            if node.role not in ("dialog", "alert", "alertdialog") and not focused:
                continue
            if node.role == "RootWebArea":
                # Document focus is a captured state of the document node,
                # not a requirement to display every descendant on every read.
                # Preserve its exact opening/attributes. The unchanged index,
                # directory and source ranges keep the subtree addressable.
                opening = self.regions[node.line].opening_span
                required[opening] = ObservationReadFragment(
                    span=opening, purpose="current_state", text=self.source(opening)
                )
                continue
            region = self.at(self.offsets[node.line])
            if node.role in ("dialog", "alert", "alertdialog"):
                region = self.regions[node.line]
            for fragment in self.fragments(
                (
                    ObservationRegionRange(
                        region_id=region.region_id, unit="whole_region"
                    ),
                )
            ):
                required[fragment.span] = ObservationReadFragment(
                    span=fragment.span, purpose="current_state", text=fragment.text
                )
        return tuple(
            required[span]
            for span in sorted(required, key=lambda span: (span.start, span.end))
        )

    def region(self, region_id: str) -> ObservationRegion:
        # Coordinates are source line identities, never guessed current node IDs.
        if (
            type(region_id) is not str
            or len(region_id) > 256
            or not region_id.startswith("ax-line-")
        ):
            raise ValueError("Unknown public AX region")
        suffix = region_id[len("ax-line-") :]
        if not suffix.isdecimal() or str(int(suffix)) != suffix:
            raise ValueError("Canonical original region identity required")
        index = int(suffix)
        if not 0 <= index < len(self.regions):
            raise ValueError("Region is outside original public snapshot")
        return self.regions[index]

    def at(self, position: int) -> ObservationRegion:
        if type(position) is not int or not 0 <= position < len(self.text):
            raise ValueError("Original public source coordinate required")
        line = bisect_right(self.offsets, position) - 1
        current: int | None = line
        while current is not None:
            node = self.nodes[current]
            if node.role in {"row", "code", "article", "comment"}:
                return self.regions[current]
            current = node.parent
        return self.regions[line]

    def source(self, span: ObservationSourceSpan) -> str:
        span = ObservationSourceSpan.model_validate(span)
        if span.end > len(self.text):
            raise ValueError("Read range left original snapshot")
        return self.text[span.start : span.end]

    def selected_spans(
        self, selection: ObservationRegionRange
    ) -> tuple[ObservationSourceSpan, ...]:
        selection = ObservationRegionRange.model_validate(selection)
        region = self.region(selection.region_id)
        if selection.unit == "whole_region":
            return (region.span,)
        assert selection.start is not None and selection.end is not None
        if selection.unit == "data_rows":
            if region.kind != "table" or selection.end > len(region.data_row_spans):
                raise ValueError("Requested loaded data rows are unavailable")
            return region.data_row_spans[selection.start : selection.end]
        if selection.end > region.span.end - region.span.start:
            raise ValueError("Codepoint slice left its original region")
        return (
            ObservationSourceSpan(
                start=region.span.start + selection.start,
                end=region.span.start + selection.end,
            ),
        )

    def headers_for(
        self, region: ObservationRegion
    ) -> tuple[ObservationSourceSpan, ...]:
        current = region
        while current.kind != "table" and current.parent_region_id is not None:
            current = self.region(current.parent_region_id)
        return current.header_spans

    def fragments(
        self, selections: tuple[ObservationRegionRange, ...]
    ) -> tuple[ObservationReadFragment, ...]:
        if (
            type(selections) is not tuple
            or not 0 < len(selections) <= self.policy.max_ranges
        ):
            raise ValueError("One bounded explicit multi-range read required")
        # Deduplicate exact source coordinates, never equal text or object labels.
        fragments: dict[ObservationSourceSpan, ObservationReadFragment] = {}
        for selection in selections:
            region = self.region(selection.region_id)
            selected = self.selected_spans(selection)
            related = list(region.context_spans)
            headers = list(self.headers_for(region))
            row_identity = []
            for node in self.nodes:
                if node.role == "row":
                    row = self.regions[node.line]
                    if any(
                        span.start < row.span.end and row.span.start < span.end
                        for span in selected
                    ):
                        related.extend(row.context_spans)
                        headers.extend(self.headers_for(row))
                        if row.span not in selected:
                            row_identity.append(row.opening_span)
            identity = (region.opening_span,) if selection.unit == "codepoints" else ()
            for purpose, spans in (
                ("ancestor", tuple(related)),
                ("table_header", tuple(headers)),
                ("row_identity", (*identity, *row_identity)),
                ("content", selected),
            ):
                for span in spans:
                    fragments[span] = ObservationReadFragment.model_validate(
                        dict(span=span, purpose=purpose, text=self.source(span))
                    )
        required = [
            item
            for item in fragments.values()
            if not any(
                other.purpose == "content"
                and other.span != item.span
                and other.span.start <= item.span.start
                and item.span.end <= other.span.end
                for other in fragments.values()
            )
        ]
        return tuple(
            sorted(required, key=lambda item: (item.span.start, item.span.end))
        )


def index_public_ax(
    reference: EvidenceRef,
    raw_record: bytes,
    resolved: ResolvedObservation,
    scope: StateScope,
    policy: ObservationReadPolicy,
    *,
    frame_id: str | None = None,
    viewport: ObservationViewport | None = None,
) -> ObservationIndex:
    policy = ObservationReadPolicy.model_validate(policy)
    scope = StateScope.model_validate(scope)
    resolved = ResolvedObservation.model_validate(resolved)
    body = VerifiedEvidenceBody(reference, raw_record)
    if (reference.visibility, reference.content_schema) != ("public", "observation/1"):
        raise ValueError("Original public observation record required")
    record = Observation.model_validate_json(body.raw)
    if record != resolved.record or (
        record.task,
        record.context_id,
        record.attempt_id,
    ) != (scope.task, scope.context_id, scope.attempt_id):
        raise OwnershipConflict("Public index changed original observation/scope")
    if record.state != "ready" or resolved.text is None or record.active_tab_id is None:
        raise ValueError("Available public current tab text required")
    if policy.unicode_version != unicodedata.unidata_version:
        raise ValueError("Search Unicode implementation differs from frozen policy")
    if frame_id is not None:
        raise ValueError(
            "observation/1 does not prove a per-frame identity; no invented frame"
        )
    text = resolved.text
    lines = tuple(text.splitlines(keepends=True))
    if len(lines) > policy.max_source_lines:
        raise ValueError("Public structure exceeds frozen indexing boundary")
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    parsed: list[tuple[int, str, str | None, int | None]] = []
    ends = [len(lines)] * len(lines)
    stack: list[int] = []
    ids: set[str] = set()
    for index, line in enumerate(lines):
        match = _NODE.match(line.rstrip("\r\n"))
        if match is None:
            raise ValueError("Unsupported public AX syntax; no silent trimming")
        if index == 0 and match[3] != "RootWebArea":
            raise ValueError(
                "Unknown public structure; original full tab AX root required"
            )
        depth = len(match[1])
        if (
            depth > 511
            or (not parsed and depth != 0)
            or (parsed and depth > parsed[-1][0] + 1)
        ):
            raise ValueError("Public AX lost its actual parent hierarchy")
        while stack and parsed[stack[-1]][0] >= depth:
            ends[stack.pop()] = index
        parent = stack[-1] if stack else None
        if depth and (parent is None or parsed[parent][0] != depth - 1):
            raise ValueError("Public AX parent is unavailable")
        node_id = match[2]
        if node_id is not None:
            if node_id in ids:
                raise EvidenceIntegrityError("Original public node ID is repeated")
            ids.add(node_id)
        parsed.append((depth, match[3], node_id, parent))
        stack.append(index)
    nodes = tuple(AxSourceNode(i, ends[i], *parts) for i, parts in enumerate(parsed))
    viewport_ref = viewport_reference(record)
    if (viewport_ref is None) != (viewport is None):
        raise EvidenceIntegrityError(
            "Viewport dependency missing or foreign; no structural fallback"
        )
    if viewport is not None:
        viewport.require_observation(record, text)
        if {element.node_id for element in viewport.elements} != ids:
            raise EvidenceIntegrityError(
                "Viewport elements must match the public AX IDs exactly"
            )

    def span(first: int, last: int) -> ObservationSourceSpan:
        return ObservationSourceSpan(start=offsets[first], end=offsets[last])

    table_rows: dict[int, list[int]] = {}
    header_rows: set[int] = set()
    for node in nodes:
        if node.role == "row":
            parent = node.parent
            while parent is not None and nodes[parent].role not in _TABLES:
                parent = nodes[parent].parent
            if parent is not None:
                table_rows.setdefault(parent, []).append(node.line)
        elif node.role == "columnheader":
            parent = node.parent
            while parent is not None and nodes[parent].role != "row":
                parent = nodes[parent].parent
            if parent is not None:
                header_rows.add(parent)
    regions = []
    for node in nodes:
        ancestors = []
        parent = node.parent
        while parent is not None:
            ancestors.append(span(parent, parent + 1))
            parent = nodes[parent].parent
        rows = table_rows.get(node.line, [])
        kind = (
            "table"
            if node.role in _TABLES
            else (
                "table_row"
                if node.role == "row"
                else (
                    "code"
                    if node.role == "code"
                    else ("comment" if node.role == "comment" else "ax_subtree")
                )
            )
        )
        regions.append(
            ObservationRegion.model_validate(
                dict(
                    region_id=f"ax-line-{node.line}",
                    kind=kind,
                    span=span(node.line, node.end_line),
                    opening_span=span(node.line, node.line + 1),
                    parent_region_id=(
                        None if node.parent is None else f"ax-line-{node.parent}"
                    ),
                    context_spans=tuple(reversed(ancestors)),
                    data_row_spans=tuple(
                        span(i, nodes[i].end_line) for i in rows if i not in header_rows
                    ),
                    header_spans=tuple(
                        span(i, nodes[i].end_line) for i in rows if i in header_rows
                    ),
                    original_node_id=node.node_id,
                )
            )
        )
    snapshot = PublicObservationSnapshot(
        observation_ref=reference,
        scope=scope,
        sequence=record.sequence,
        tab_id=record.active_tab_id,
        frame_id=frame_id,
        text_sha256=hashlib.sha256(text.encode()).hexdigest(),
        policy_sha256=policy.digest,
    )
    overview = ObservationOverview(
        active_tab_id=record.active_tab_id,
        tabs=record.tabs,
        last_action_error=record.last_action_error,
    )
    indexed = ObservationIndex(
        snapshot,
        policy,
        text,
        lines,
        tuple(offsets),
        nodes,
        tuple(regions),
        overview,
        viewport=viewport,
    )
    return replace(indexed, mandatory_context=indexed.capture_mandatory_context())
