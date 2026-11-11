"""Optional lifecycle for genuine Shopping normal proofs and public evidence.

Only public current DOM and actual observer timeline are captured. Independent
full references stay in evaluator files and never augment actor observations.
"""
from pathlib import Path
from .io_utils import atomic_write_json
from .shopping_remaining_runtime import (family, require_admission, before_reference,
                                         reference, review_terminal, evaluate_review)


class ShoppingRemainingHooks:
    def __init__(self, contract, proof, directory):
        require_admission(contract, proof)
        self.contract = contract
        self.proof = proof
        self.directory = Path(directory)
        self.kind = family(contract, proof)
        self.expected = before_reference(proof)

    def verify_baseline(self, actual_reference, initial_fingerprint):
        if actual_reference != self.expected or initial_fingerprint != self.proof["cycles"][0]["initial_fingerprint"]:
            raise RuntimeError("Original native Shopping reference/reset differs from both controls")

    def observe_initial(self, page):
        if self.kind != "shopping_original_page_prices":
            return
        from .shopping_remaining_runtime import _capture_current
        from .shopping_remaining_normal import original_page_membership
        from urllib.parse import urlsplit, parse_qs
        actual, original = urlsplit(page.url), urlsplit(self.contract["start_path"])
        if actual.path != original.path or parse_qs(actual.query, keep_blank_values=True) != parse_qs(original.query, keep_blank_values=True):
            raise RuntimeError("Original public initial collection URL changed")
        capture = _capture_current(page)
        original_page_membership(capture, self.expected["source_state"])
        atomic_write_json(self.directory / "initial-native-shopping-collection.json", capture)

    def current_reference(self, site):
        return reference(site, self.contract)

    def capture_terminal(self, page, terminal, *, timeline=()):
        if self.kind != "native_reviews":
            return
        wrapper = review_terminal(page, timeline=timeline)
        terminal["native_reviews"] = wrapper
        atomic_write_json(self.directory / "terminal-native-reviews.json", wrapper)
        atomic_write_json(self.directory / "terminal-page.json", terminal)

    def evaluate_reviews(self, page, actual_reference, *, site_origin, runtime_error=None):
        if self.kind != "native_reviews":
            raise ValueError("Review lifecycle used for a query")
        atomic_write_json(self.directory / "native-review-reference-state.json",
                          {"initial": self.expected, "final": actual_reference})
        result = evaluate_review(self.contract, page, (page or {}).get("native_reviews"),
                                 site_origin=site_origin, runtime_error=runtime_error)
        if result["status"] != "unknown":
            unchanged = actual_reference == self.expected
            result["checks"]["requested_records_unchanged"] = unchanged
            success = all(result["checks"].values())
            result.update(status="success" if success else "failure", reward=float(success))
        return result
