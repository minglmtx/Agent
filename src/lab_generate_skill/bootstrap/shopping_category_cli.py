"""Installed single-member category production entry; no implicit replay."""

import argparse
from pathlib import Path
from pydantic import TypeAdapter
from lab_generate_skill.domain.closed_shopping_source import (
    ClosedCategoryNavigationReadMaterial,
)
from lab_generate_skill.domain.evidence import EvidenceRef
from lab_generate_skill.domain.task import PublicTask
from lab_generate_skill.adapters.processes.deadline import DeadlineControl
from .shopping_category_source_inputs import load_category_source_delta
from .shopping_category_runtime_supply import (
    CategoryNavigationSupplierInputs,
    supply_category_runtime,
)
from .shopping_category_production_entry import run_category_production


def _document(path: Path) -> bytes:
    if (
        path.resolve(strict=True) != path
        or not path.is_file()
        or not 0 < path.stat().st_size <= 8 * 1024**2
    ):
        raise ValueError("Bounded canonical original category input document required")
    raw = path.read_bytes()
    if not 0 < len(raw) <= 8 * 1024**2:
        raise ValueError("Category input changed size during read")
    return raw


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "supplier-inputs",
        "native-input",
        "native-reference",
        "public-task",
        "output",
        "claim-root",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--claim-scope", required=True)
    parser.add_argument("--retained-source", type=Path)
    parser.add_argument("--source-index", type=Path)
    parser.add_argument("--source-delta", type=Path)
    parser.add_argument("--source-delta-sha256")
    args = parser.parse_args()
    if (args.source_delta is None) != (args.source_delta_sha256 is None):
        raise ValueError("Both frozen Shopping source delta arguments required")
    if args.source_delta is not None and args.retained_source is not None:
        raise ValueError("Complete Shopping source must be selected inside its delta")
    selected = TypeAdapter(CategoryNavigationSupplierInputs).validate_json(
        _document(args.supplier_inputs)
    )
    if selected.stage_budgets is None:
        raise ValueError(
            "Current category CLI requires explicit stage budgets before effects"
        )
    raw = _document(args.native_input)
    native = EvidenceRef.model_validate_json(_document(args.native_reference))
    public = PublicTask.model_validate_json(_document(args.public_task))
    retained = (
        ClosedCategoryNavigationReadMaterial.model_validate_json(
            _document(args.retained_source)
        )
        if args.retained_source is not None
        else None
    )
    source_inputs = (
        load_category_source_delta(
            args.source_delta,
            args.source_delta_sha256,
            raw,
            native,
            public,
            DeadlineControl(120, "category-selected-source-delta"),
        )
        if args.source_delta is not None
        else None
    )
    with supply_category_runtime(
        selected,
        raw,
        native,
        public,
        args.output,
        args.claim_root,
        claim_scope=args.claim_scope,
        retained_source=retained,
        source_index=args.source_index,
        source_inputs=source_inputs,
    ) as supplied:
        run_category_production(supplied.runtime, raw, native, public, supplied.facts)


if __name__ == "__main__":
    main()
