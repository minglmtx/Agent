"""Optional Shopping normal interfaces; no actor policy or hidden input.

The three new query families delegate to the existing independent native
reference. Legacy shopping_product keeps its ordinary DB dispatch in the shared
reference module, avoiding a recursive call through this optional adapter.
"""
from copy import deepcopy
from urllib.parse import urlsplit, parse_qs

QUERY_FAMILIES = frozenset({"shopping_native_contact", "shopping_original_page_prices",
                            "shopping_native_category_price_subset"})


def family(contract, proof=None):
    if contract.get("domain") != "shopping":
        return None
    kind = contract.get("query", {}).get("family")
    result = "native_reviews" if contract.get("native_reviews") else (
        kind if kind in QUERY_FAMILIES or kind == "shopping_product" else None)
    if proof is not None:
        from .shopping_remaining_normal import VERSION
        if proof.get("admission_version") != VERSION:
            return None
    return result


def uses_normal_proof(contract, proof):
    """New families never fall back to an unrelated proof schema."""
    from .shopping_remaining_normal import VERSION
    kind = family(contract)
    return kind in QUERY_FAMILIES or kind == "native_reviews" or (
        kind == "shopping_product" and proof.get("admission_version") == VERSION)


def require_admission(contract, proof):
    if family(contract, proof) is None:
        raise ValueError("Exact optional Shopping normal family and version required")
    from .shopping_remaining_normal import require_normal_admission, fingerprint
    require_normal_admission(contract, proof)
    source = contract.get("source_task_id")
    if not isinstance(source, str) or not source:
        raise ValueError("Explicit original source binding required")
    for cycle in proof["cycles"]:
        original = cycle.get("contract")
        if (cycle.get("source_task_id") != source or not isinstance(original, dict)
            or original.get("source_task_id") != source
            or original.get("task_id") != contract.get("task_id")
            or fingerprint(original) != fingerprint(contract)
            or original.get("source_trace_ids") != contract.get("source_trace_ids")
            or original.get("recorded_start_paths") != contract.get("recorded_start_paths")):
            raise ValueError("Normal control belongs to another source, task or original start")
    before_reference(proof)


def reference(site, contract, *, auth=None):
    if family(contract) is None:
        raise ValueError("Only explicit remaining native families dispatch here")
    # Lazy import avoids the private control helper's import of query_reference.
    # Shared query dispatch only calls this for QUERY_FAMILIES, never the legacy
    # shopping_product branch which original_reference delegates back to.
    if auth is None:
        from .site_auth import credentials
        auth = credentials(site.root, "shopping")
    if family(contract) == "shopping_native_category_price_subset":
        # The proven normal controls use the full native search window before
        # its first render. The old toolbar reader can return only one page.
        # Keep every before/after capture; this private path is never a prompt.
        from pathlib import Path
        from uuid import uuid4
        from probe_shopping_failed_normal_controls import reference as complete_reference
        capture_path = Path(site.logs) / ("native-category-reference-" + uuid4().hex + ".json")
        return complete_reference(site, contract, auth, capture_path=capture_path)
    from probe_shopping_remaining_normal_controls import reference as original_reference
    return original_reference(site, contract, auth)


def before_reference(proof):
    from .shopping_remaining_normal import VERSION
    if proof.get("admission_version") != VERSION:
        raise ValueError("Independent normal reference proof required")
    cycles = proof.get("cycles")
    if not isinstance(cycles, list) or len(cycles) != 2 or not all(isinstance(c, dict) for c in cycles):
        raise ValueError("Two fresh normal cycles required")
    value = cycles[0].get("before_reference")
    if not isinstance(value, dict) or not value or any(
        c.get(key) != value for c in cycles for key in ("before_reference", "after_reference")):
        raise ValueError("Independent complete normal reference differs across before/after and both cycles")
    return deepcopy(value)


def _capture_current(page):
    from probe_shopping_plan_capabilities import READ
    from .shopping_collection_reference import public_collection
    return {"public": page.evaluate(READ), "collection": public_collection(page)}


def ui_values(page, contract):
    kind = family(contract)
    if kind not in QUERY_FAMILIES:
        raise ValueError("Explicit remaining native query family required")
    q = contract["query"]
    actual, expected = urlsplit(page.url), urlsplit(q["reference_path"])
    # Wrong public page is a model choice, not a broken environment reader.
    if actual.path != expected.path:
        return {}
    capture = _capture_current(page)
    if kind == "shopping_native_contact":
        forms = [f for f in capture["public"]["forms"] if f["visible"]
                 and f["method"] == "post" and urlsplit(f["action"]).path == "/contact/index/post/"]
        if len(forms) != 1 or not {"name", "email", "comment"} <= {
            f["name"] for f in forms[0]["fields"] if f["visible"]}:
            return {}
        return {"contact_form_url": page.url}
    from .shopping_remaining_normal import native_price_records
    if kind == "shopping_original_page_prices":
        if parse_qs(actual.query, keep_blank_values=True) != parse_qs(expected.query, keep_blank_values=True):
            return {}
        return {"products": native_price_records(capture["collection"]["products"],
                  capture["public"]["prices"], terms=q["name_terms"])}
    return {"products": native_price_records(capture["collection"]["products"],
              capture["public"]["prices"], upper="100")}


def review_terminal(page, *, timeline=()):
    from .shopping_remaining_normal import read_reviews
    return {"current_native_review_page": read_reviews(page),
            "observed_native_mounts": list(timeline), "unvisited_pages_filled": False}


def evaluate_review(contract, page, state, *, site_origin, runtime_error=None):
    if family(contract) != "native_reviews":
        raise ValueError("Explicit native review normal family required")
    from .shopping_remaining_normal import VERSION, evaluate_review as original_evaluate
    if not isinstance(state, dict) or "current_native_review_page" not in state or state.get("unvisited_pages_filled") is not False:
        return {"version": VERSION, "status": "unknown", "reward": None, "checks": {},
                "reason": "Current native review terminal capture unavailable"}
    # Timeline is diagnostic only. A valid current page (including page 2) is
    # sufficient; no all-pages requirement and no unvisited rows are filled.
    return original_evaluate(contract, page, state["current_native_review_page"],
                             site_origin=site_origin, runtime_error=runtime_error)


def review_feedback(judgment):
    from .shopping_product_panel import FEEDBACK
    text = dict(FEEDBACK, allowed_review_product="The visible native review page belongs to an allowed requested product.")
    return {"status": judgment["status"], "reward": judgment["reward"], "reason": judgment.get("reason"),
            "checks": [{"name": k, "passed": v, "condition": text.get(k, "A required observable review condition is satisfied.")}
                       for k, v in judgment.get("checks", {}).items()],
            "private_reference_values_provided": False, "action_sequence_provided": False}
