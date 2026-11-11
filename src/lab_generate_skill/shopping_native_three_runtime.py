"""Optional native Shopping completion adapters; no execution strategy.

Only the original goal is public. Native references, saved cart/guest rows and
normal-control proofs stay in evaluator storage. Toolbar changes are read from
the current document, never proposed to an actor or applied automatically.
"""
from copy import deepcopy
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlencode, urlsplit

from lab_generate_skill.shopping_seven_native import (
    COMPARE_READ, compare_checks, decimal, digest, option_map, positive_int,
    read_saved_cart, validate_reorder_reference,
)

VERSION = "shopping-native-three-normal-v1"
FAMILY = "shopping_native_three"
KINDS = frozenset({"price_filter", "guest_compare", "reorder"})
TOOLBAR_KEYS = frozenset({"p", "product_list_limit", "product_list_order", "product_list_dir", "product_list_mode"})
PUBLIC_PRICE_READ = r'''() => {
 const visible=e=>!!e&&e.getClientRects().length>0&&![...function*(n){while(n){yield n;n=n.parentElement}}(e)].some(n=>{const s=getComputedStyle(n);return s.display==='none'||s.visibility==='hidden'||n.hidden||n.getAttribute('aria-hidden')==='true'});
 return [...document.querySelectorAll('main .price-box')].filter(visible).map(e=>({product_id:e.getAttribute('data-product-id'),text:e.innerText.trim(),amounts:[...e.querySelectorAll('[data-price-amount]')].filter(visible).map(n=>({type:n.getAttribute('data-price-type'),amount:n.getAttribute('data-price-amount')}))}));
}'''
PUBLIC_TOOLBAR_READ = r'''() => {
 const visible=e=>!!e&&e.getClientRects().length>0&&getComputedStyle(e).visibility!=='hidden';
 const selected=selector=>[...document.querySelectorAll(selector)].filter(visible).map(e=>e.value);
 return {page:[...document.querySelectorAll('.pages .item.current')].filter(visible).map(e=>(e.innerText.match(/[0-9]+/g)||[])),
   limit:selected('[data-role="limiter"]'),order:selected('[data-role="sorter"]'),
   next_direction:[...document.querySelectorAll('[data-role="direction-switcher"]')].filter(visible).map(e=>e.getAttribute('data-value'))};
}'''
NEGATIVES = {
    "price_filter": {"no_op", "wrong_coarse_range", "wrong_category", "404", "login"},
    "guest_compare": {"no_op", "partial", "heading_only", "hidden_table", "wrong_identity", "404", "login"},
    "reorder": {"no_op", "wrong_owned_order", "wrong_quantity_reference", "404", "login"},
}


def enabled(contract):
    return contract.get("completion", {}).get("family") == FAMILY


def validate(contract):
    if not enabled(contract) or contract.get("domain") != "shopping":
        raise ValueError("Explicit optional Shopping native family required")
    spec = contract["completion"].get("native")
    if not isinstance(spec, dict) or spec.get("kind") not in KINDS:
        raise ValueError("Explicit supported native completion kind required")
    if contract.get("eligible_for_training") is not False or contract.get("heldout_quarantine") is not False:
        raise ValueError("Non-heldout development task required")
    if contract.get("task_text_changed") is not False:
        raise ValueError("This adapter requires an unchanged original task")
    required = ("task_id", "source_task_id", "goal", "start_path", "source_trace_ids", "recorded_start_paths")
    if any(not contract.get(k) for k in required):
        raise ValueError("Complete original source binding required")
    if contract["start_path"] != contract["recorded_start_paths"][0]:
        raise ValueError("Original first start must be preserved")
    start = urlsplit(contract["start_path"])
    if start.scheme or start.netloc or not start.path.startswith("/"):
        raise ValueError("Original local first start required")
    guest = spec["kind"] == "guest_compare"
    if contract.get("private_authentication") != ("guest" if guest else "native_benchmark_account"):
        raise ValueError("Original native account/guest profile required")
    if spec["kind"] == "price_filter":
        positive_int(spec.get("category_id"))
        path = urlsplit(spec.get("category_path", ""))
        if path.scheme or path.netloc or path.query or path.fragment or not path.path.startswith("/"):
            raise ValueError("Native category route required")
        if not isinstance(spec.get("category_name"), str) or not spec["category_name"]:
            raise ValueError("Native category identity required")
        if decimal(spec.get("lower")) < 0 or decimal(spec.get("upper")) <= decimal(spec["lower"]):
            raise ValueError("Native positive price interval required")
        if spec.get("upper_bound_semantics") != "native_exclusive":
            raise ValueError("Native renderer interval semantics required")
    elif spec["kind"] == "guest_compare":
        products = spec.get("products")
        if not isinstance(products, list) or len(products) != 2:
            raise ValueError("Two original comparison products required")
        ids = [positive_int(p.get("entity_id")) for p in products]
        if len(set(ids)) != 2 or any(not p.get("name") or not p.get("url_key") for p in products):
            raise ValueError("Two unique native comparison identities required")
    elif not re.fullmatch(r"[0-9]+", spec.get("order_increment_id", "")):
        raise ValueError("Original literal order number required")
    return spec


def fingerprint(contract):
    return digest({k: v for k, v in contract.items() if k != "admission_result"})


def require_admission(contract, proof):
    spec = validate(contract)
    if (proof.get("admission_version") != VERSION or proof.get("passed") is not True
            or proof.get("contract_fingerprint") != fingerprint(contract)
            or proof.get("source_task_id") != contract["source_task_id"]):
        raise ValueError("Exact source-bound normal proof required; capability is insufficient")
    cycles = proof.get("cycles")
    if not isinstance(cycles, list) or len(cycles) != 2 or {c.get("cycle") for c in cycles} != {0, 1}:
        raise ValueError("Two complete independent fresh normal cycles required")
    required = {"positive": "success", **{k: "failure" for k in NEGATIVES[spec["kind"]]}}
    if spec["kind"] == "price_filter": required["positive_native_page2"] = "success"
    for c in cycles:
        if (c.get("source_task_id") != contract["source_task_id"]
                or c.get("contract_fingerprint") != fingerprint(contract)
                or c.get("original_contract") != {k: v for k, v in contract.items() if k != "admission_result"}
                or c.get("initial_valid") is not True or c.get("normal_controls_real_native") is not True
                or c.get("fresh_instance_disposed") is not True or c.get("protected_restored") is not True
                or not c.get("initial_fingerprint") or c["initial_fingerprint"] != c.get("final_fingerprint")
                or c.get("before_reference") != c.get("after_reference") or not c.get("before_reference")
                or not c.get("before_protected") or c["before_protected"] != c.get("after_protected")
                or len(c["before_protected"].get("tables", {})) != 22
                or any(c.get("checks", {}).get(k) != v for k, v in required.items())):
            raise ValueError("Original start, real controls, complete reference or reset proof failed")
    if (cycles[0].get("fresh_instance_id") == cycles[1].get("fresh_instance_id")
            or not all(c.get("fresh_instance_id") for c in cycles)
            or cycles[0]["before_reference"] != cycles[1]["before_reference"]
            or cycles[0]["before_protected"] != cycles[1]["before_protected"]
            or cycles[0]["initial_fingerprint"] != cycles[1]["initial_fingerprint"]):
        raise ValueError("Independent native baseline/provenance differs across fresh cycles")
    return True


def price_scope(spec, public_url, site_origin):
    """Validate only actual current native filtering/toolbar state; no navigation."""
    actual, origin = urlsplit(public_url), urlsplit(site_origin)
    query = parse_qs(actual.query, keep_blank_values=True)
    if ((actual.scheme, actual.netloc) != (origin.scheme, origin.netloc)
            or actual.path != spec["category_path"] or actual.fragment
            or any(len(v) != 1 for v in query.values())
            or set(query) - (TOOLBAR_KEYS | {"price"})
            or query.get("price") != [str(spec["lower"]) + "-" + str(spec["upper"])]):
        return None
    for k in ("p", "product_list_limit"):
        if k in query and not re.fullmatch(r"[1-9][0-9]*", query[k][0]): return None
    if "product_list_order" in query and query["product_list_order"][0] not in {"position", "name", "price"}: return None
    if "product_list_dir" in query and query["product_list_dir"][0] not in {"asc", "desc"}: return None
    if "product_list_mode" in query and query["product_list_mode"][0] not in {"grid", "list"}: return None
    return {"kind": "category", "category_id": spec["category_id"],
            "path": actual.path + "?" + urlencode({k: v[0] for k, v in query.items()})}


def native_page_reference(site, spec, username):
    """Reuse the native PHP collection implementation for the observed toolbar page.

    Existing first-page Python helper intentionally rejects pagination; this
    optional adapter validates the requested current page instead. The native
    PHP implementation, filter and toolbar code are unchanged.
    """
    from lab_generate_skill.site_database import select_rows
    from lab_generate_skill import shopping_collection_reference as collection
    account = select_rows(site, "SELECT entity_id,group_id FROM customer_entity WHERE email='" + username.replace("'", "''") + "'")
    if len(account) != 1: raise ValueError("Unique native collection account required")
    args = dict(spec, host=urlsplit(site.url).netloc, customer_group_id=int(account[0]["group_id"]))
    php = Path(collection.__file__).with_name("shopping_native_collection.php").read_text().removeprefix("<?php")
    result = site.command(["php", "-d", "memory_limit=1024M", "-r", php, json.dumps(args)],
                          capture_output=True, text=True, timeout=60)
    value = json.loads(result.stdout)
    params = parse_qs(urlsplit(spec["path"]).query)
    ids = [positive_int(p["id"]) for p in value["products"]]
    if (not ids or len(ids) != len(set(ids)) or type(value["page"]) is not int or value["page"] < 1
            or type(value["limit"]) is not int or value["limit"] <= 0
            or value["total"] < len(ids) or len(ids) > value["limit"]
            or value["category"]["id"] != spec["category_id"] or value["category"]["active"] is not True
            or not value.get("source_hashes")):
        raise ValueError("Actual native toolbar collection is inconsistent")
    # Native toolbar validation/clamping is authoritative. An actor-selected
    # unsupported page size is not a broken native DB reader; the actual current
    # native page membership must still match the public document below.
    value["account_group"] = int(account[0]["group_id"])
    return value


def observed_toolbar_scope(scope, toolbar):
    """Bind private native replay to actual selected toolbar values, including
    native remembered order/limit that the current URL need not spell out.
    This only constructs evaluator reader arguments; it never changes a URL.
    """
    value = deepcopy(scope);url = urlsplit(scope["path"]);query = parse_qs(url.query,keep_blank_values=True)
    for name, parameter in (("page","p"),("limit","product_list_limit"),("order","product_list_order")):
        rows=toolbar.get(name,[])
        if name=="page": rows=[r[0] for r in rows if isinstance(r,list)and len(r)==1]
        if rows:
            if len(set(rows))!=1:raise ValueError("Native visible toolbar controls disagree")
            selected=rows[0]
            if name in ("page","limit") and not re.fullmatch(r"[1-9][0-9]*",selected):raise ValueError("Malformed native visible toolbar value")
            if name=="order"and selected not in {"position","name","price"}:raise ValueError("Unsupported native visible toolbar sort")
            query[parameter]=[selected]
    directions=toolbar.get("next_direction",[])
    if directions:
        if len(set(directions))!=1 or directions[0]not in {"asc","desc"}:raise ValueError("Malformed native direction switcher")
        # Magento's data-value is the next direction, not the current one.
        query["product_list_dir"]=["desc"if directions[0]=="asc"else"asc"]
    value["path"]=url.path+"?"+urlencode({k:v[0]for k,v in query.items()})
    return value


def price_reference_identity(value):
    return {k: deepcopy(value[k]) for k in ("category", "total", "active_filters", "source_hashes", "account_group")}


def price_checks(spec, reference, public, prices, *, site_origin):
    from lab_generate_skill.shopping_collection_reference import normalized_label, total_from_toolbar
    scope = price_scope(spec, public.get("url", ""), site_origin)
    category = reference["category"]
    if category["id"] != spec["category_id"] or category["name"] != spec["category_name"] or category["active"] is not True:
        raise ValueError("Original independent native category changed")
    products = reference["products"]
    # Public wrong/empty products are ordinary failure, not an oracle failure.
    observed = public.get("products", [])
    identity = [(str(r["id"]), r["name"]) for r in products] == [(str(r.get("id")), r.get("name")) for r in observed]
    try: total = total_from_toolbar(public.get("amount", [])) == reference["total"]
    except ValueError: total = False
    amounts = {str(r["product_id"]): [decimal(a["amount"]) for a in r["amounts"] if a["type"] == "finalPrice"] for r in prices}
    lo, hi = decimal(spec["lower"]), decimal(spec["upper"])
    expected_filter = [{"label": r["label"], "value": normalized_label(r["value"])} for r in reference["active_filters"]]
    return {"requested_native_category_range": scope is not None,
            "current_native_page_members": bool(products) and identity,
            "native_total_matches_public_toolbar": total,
            "native_interval_and_visible_final_prices": bool(products) and all(lo <= decimal(r["price"]) < hi and amounts.get(str(r["id"])) == [decimal(r["price"])] for r in products),
            "active_native_range_is_public": bool(expected_filter) and public.get("active_filters") == expected_filter,
            "visible_native_category_identity": public.get("heading") == spec["category_name"] and "catalog-category-view" in public.get("classes", "").split()}


def guest_saved(before, now):
    """Read the actual native guest collection delta, never an actor-picked ID."""
    old = {r["catalog_compare_item_id"]: r for r in before}
    if any(next((n for n in now if n["catalog_compare_item_id"] == k), None) != r for k, r in old.items()):
        raise ValueError("Existing all-account comparison rows changed")
    added = [r for r in now if r["catalog_compare_item_id"] not in old]
    visitors = {r["visitor_id"] for r in added}
    if any(r.get("customer_id") is not None for r in added) or len(visitors) != 1:
        return {"customer_id": None, "visitor_id": None, "products": []}
    return {"customer_id": None, "visitor_id": next(iter(visitors)), "products": [r["product_id"] for r in added]}


def reorder_checks(before, after, reference, events, page, *, site_origin):
    expected = validate_reorder_reference(reference)
    if (before["user_id"] != reference["account"]["entity_id"] or after["user_id"] != before["user_id"]
            or after["cart_id"] != before["cart_id"]): raise ValueError("Independent native cart/account baseline changed")
    old = {r["item_id"]: r for r in before["saved_items"]}
    new = {r["item_id"]: r for r in after["saved_items"]}
    if any(r["product_id"] in expected for r in before["items"]): raise ValueError("Original reordered products must be absent in this verified initial cart")
    added = [r for r in after["items"] if r["item_id"] not in old]
    actual = [(r["product_id"], r["name"], r["sku"], decimal(r["qty"]), tuple(sorted(option_map(after, r["item_id"]).items()))) for r in added]
    wanted = [(k, r["name"], r["sku"], r["qty"], tuple(sorted(r["options"].items()))) for k, r in expected.items()]
    target = "/sales/order/reorder/order_id/" + str(reference["orders"][0]["entity_id"])
    return {"completed_owned_order_used": any(r.get("method") == "POST" and r.get("path", "").rstrip("/") == target for r in events.get("posts", [])) and any(r.get("trusted") is True and r.get("path", "").rstrip("/") == target for r in events.get("trusted_activations", [])),
            "complete_native_products_quantities_options_saved": sorted(actual) == sorted(wanted),
            "original_cart_items_all_columns_unchanged": all(new.get(k) == v for k, v in old.items()),
            "original_cart_options_all_columns_unchanged": [r for r in after["item_options"] if r["item_id"] in old] == before["item_options"],
            "coupon_unchanged": after["coupon_code"] == before["coupon_code"]}


def reference(site, contract, auth):
    spec = validate(contract)
    if spec["kind"] == "price_filter":
        scope = {"kind": "category", "category_id": spec["category_id"], "path": spec["category_path"] + "?price=" + spec["lower"] + "-" + spec["upper"]}
        return native_page_reference(site, scope, auth["username"])
    if spec["kind"] == "guest_compare":
        from lab_generate_skill.site_database import select_rows
        products = []
        for p in spec["products"]:
            rows = select_rows(site, "SELECT p.entity_id,p.sku,p.type_id,n.value AS name,u.value AS url_key FROM catalog_product_entity p JOIN catalog_product_entity_varchar n ON n.entity_id=p.entity_id AND n.store_id=0 AND n.attribute_id=(SELECT attribute_id FROM eav_attribute WHERE entity_type_id=4 AND attribute_code='name') JOIN catalog_product_entity_varchar u ON u.entity_id=p.entity_id AND u.store_id=0 AND u.attribute_id=(SELECT attribute_id FROM eav_attribute WHERE entity_type_id=4 AND attribute_code='url_key') WHERE p.entity_id=" + str(positive_int(p["entity_id"])))
            if rows != [p]: raise ValueError("Original independent comparison product changed")
            products.extend(rows)
        return {"products": products}
    from probe_shopping_plan_capabilities import reference as original_reference, schema
    value = original_reference(site, auth, {"kind": "reorder", "order_increment_id": spec["order_increment_id"]}, schema(site))
    validate_reorder_reference(value)
    return value


def evaluate(contract, page, state, reference_value, *, site_origin, before=None, runtime_error=None):
    spec = validate(contract)
    def result(status, checks, reason=None): return {"version": VERSION, "status": status, "reward": {"success": 1., "failure": 0., "unknown": None}[status], "checks": checks, "reason": reason}
    if runtime_error: return result("unknown", {}, "Environment or inference error")
    if not isinstance(page, dict) or any(k not in page for k in ("url", "http_status", "login_page", "error_page")):
        return result("unknown", {}, "Terminal document capture unavailable")
    if not isinstance(page["url"],str) or type(page["http_status"]) is not int or any(type(page[k]) is not bool for k in ("login_page", "error_page")):
        return result("unknown", {}, "Malformed terminal document capture")
    if page["http_status"] >= 500 or page["http_status"] < 200:
        return result("unknown", {}, "Native document transport or server error")
    actual, origin = urlsplit(page["url"]), urlsplit(site_origin)
    checks = {"correct_local_site": (actual.scheme, actual.netloc) == (origin.scheme, origin.netloc),
              "terminal_page_valid": 200 <= page["http_status"] < 300 and not page["login_page"] and not page["error_page"]}
    if not all(checks.values()): return result("failure", checks)
    if not isinstance(state, dict): return result("unknown", checks, "Native terminal adapter was not captured")
    try:
        if spec["kind"] == "price_filter":
            if price_scope(spec, page["url"], site_origin) is None:
                return result("failure", dict(checks, requested_native_category_range=False))
            checks.update(price_checks(spec, reference_value, state["public"], state["prices"], site_origin=site_origin))
        elif spec["kind"] == "guest_compare":
            if actual.path.rstrip("/") not in ("/catalog/product_compare", "/catalog/product_compare/index"):
                return result("failure", dict(checks, native_guest_comparison_page=False))
            checks.update(compare_checks(reference_value["products"], state["public"], state["saved"], site_origin=site_origin))
        else:
            checks.update(reorder_checks(before, state["saved"], reference_value, state["events"], page, site_origin=site_origin))
    except (ValueError, KeyError, TypeError) as exc:
        return result("unknown", checks, "Native reference/capture consistency error: " + type(exc).__name__)
    return result("success" if all(checks.values()) else "failure", checks)


def feedback(judgment):
    labels = {"completed_owned_order_used": "The actual native Reorder submission belongs to the requested completed order.",
              "complete_native_products_quantities_options_saved": "The requested native order contents, quantities and options are saved in the cart.",
              "requested_native_category_range": "The requested native category and price interval are active.",
              "native_guest_saved_collection_exact": "The guest comparison contains the requested products.",
              "complete_correct_visible_comparison_products": "The visible native comparison shows the requested products."}
    return {"status": judgment["status"], "reward": judgment["reward"], "reason": judgment.get("reason"),
            "checks": [{"name": k, "passed": v, "condition": labels.get(k, "A required native completion condition is satisfied.")} for k, v in judgment.get("checks", {}).items()],
            "private_reference_values_provided": False, "action_sequence_provided": False}


def evaluate_terminal(contract, page, *, site_origin):
    """Shared evaluator facade; the rich terminal record is private storage only."""
    state = page.get("shopping_native_three") if isinstance(page, dict) else None
    reference_value = state.get("private_current_reference", state.get("private_baseline_reference")) if isinstance(state, dict) else None
    return evaluate(contract, page, state, reference_value, site_origin=site_origin,
                    before=state.get("private_initial_saved") if isinstance(state, dict) else None)


def protected_state(site, spec, *, cart_id=None):
    """Full unrelated native rows, with only the task's intended cart delta allowed.

    The existing 22-table native full-row reader remains authoritative. For
    Reorder, its two whole-cart-item hashes are replaced with complete rows for
    every other cart; the evaluator independently checks all OLD own-cart rows,
    options, coupon and the exact newly reordered contents. Guest comparison is
    outside those 22 tables and additionally guards its original rows in
    guest_saved. No entire account/order/coupon table is dropped.
    """
    from probe_shopping_seven_native import protected
    value = protected(site)
    if spec["kind"] != "reorder": return value
    from lab_generate_skill.site_database import select_rows
    cart_id = positive_int(cart_id)
    value = deepcopy(value)
    for table in ("quote_item", "quote_item_option"): value["tables"].pop(table)
    others = select_rows(site, f"SELECT * FROM quote_item WHERE quote_id<>{cart_id} ORDER BY item_id")
    # Preserve every orphan option too; only options of this exact active cart
    # are excluded from the unrelated-record signature.
    options = select_rows(site, f"SELECT * FROM quote_item_option WHERE item_id NOT IN (SELECT item_id FROM quote_item WHERE quote_id={cart_id}) ORDER BY option_id")
    value["all_other_cart_item_rows"] = [{k:v for k,v in row.items() if k != "updated_at"} for row in others]
    value["all_other_cart_option_rows"] = options
    return value


class NativeReorderObserver:
    """Passive actual trusted activation/POST evidence, including current document."""
    SCRIPT = r'''(()=>{if(window.__labNativeReorderInstalled)return;window.__labNativeReorderInstalled=true;
      document.addEventListener('click',e=>{if(!e.isTrusted)return;const a=e.target.closest('[data-post]');if(!a)return;
       try{const d=JSON.parse(a.dataset.post),u=new URL(d.action,location.href);if(u.origin!==location.origin||!/^\/sales\/order\/reorder\/order_id\/[1-9][0-9]*\/?$/.test(u.pathname))return;
        void window.__labNativeReorder({trusted:true,path:u.pathname});}catch{}},true)})()'''

    def __init__(self, context, site_origin):
        self.context, self.origin = context, urlsplit(site_origin)
        self.activations, self.posts, self.closed = [], [], False
        context.expose_binding("__labNativeReorder", self._record)
        context.add_init_script(self.SCRIPT)
        context.on("request", self._request)

    def _record(self, source, event):
        if self.closed or source["frame"] != source["page"].main_frame: return
        if (not isinstance(event, dict) or set(event) != {"trusted", "path"} or event["trusted"] is not True
                or not re.fullmatch(r"/sales/order/reorder/order_id/[1-9][0-9]*/?", event["path"])): return
        u = urlsplit(source["page"].url)
        if (u.scheme, u.netloc) == (self.origin.scheme, self.origin.netloc): self.activations.append(deepcopy(event))

    def _request(self, request):
        if self.closed: return
        u = urlsplit(request.url)
        if request.method == "POST" and (u.scheme, u.netloc) == (self.origin.scheme, self.origin.netloc) and re.fullmatch(r"/sales/order/reorder/order_id/[1-9][0-9]*/?", u.path):
            self.posts.append({"method": "POST", "path": u.path})

    def install_current(self, page): page.evaluate(self.SCRIPT)
    def snapshot(self): return {"trusted_activations": deepcopy(self.activations), "posts": deepcopy(self.posts)}
    def close(self):
        if not self.closed: self.context.remove_listener("request", self._request)
        self.closed = True


class NativeThreeHooks:
    """Optional runner lifecycle. All stored references remain private."""
    def __init__(self, contract, proof, directory):
        require_admission(contract, proof)
        self.contract, self.spec, self.directory = contract, validate(contract), Path(directory)
        self.expected = deepcopy(proof["cycles"][0]["before_reference"])
        self.reference, self.before, self.events = None, None, None
        self.protected_before = None

    @property
    def guest(self): return self.spec["kind"] == "guest_compare"

    def verify_baseline(self, site, auth):
        self.auth = auth
        self.reference = reference(site, self.contract, auth)
        if self.reference != self.expected: raise RuntimeError("Independent original native reference differs from both controls")
        if self.spec["kind"] == "reorder": self.before = read_saved_cart(site, auth["username"])
        if self.guest:
            from lab_generate_skill.site_database import select_rows
            self.before = select_rows(site, "SELECT * FROM catalog_compare_item ORDER BY catalog_compare_item_id")
        self.protected_before = protected_state(site, self.spec,
             cart_id=self.before["cart_id"] if self.spec["kind"] == "reorder" else None)

    def attach(self, context, site_origin):
        if self.spec["kind"] == "reorder": self.events = NativeReorderObserver(context, site_origin)

    def observe_initial(self, page):
        if self.events is not None: self.events.install_current(page)
        if urlsplit(page.url).path != urlsplit(self.contract["start_path"]).path:
            raise RuntimeError("Original first native document changed")
        if self.guest and page.evaluate(COMPARE_READ)["authenticated_marker"]:
            raise RuntimeError("Guest original start was silently authenticated")

    def terminal(self, site, page, auth):
        if self.spec["kind"] == "price_filter":
            from lab_generate_skill.shopping_collection_reference import public_collection
            value = {"public": public_collection(page), "prices": page.evaluate(PUBLIC_PRICE_READ),"toolbar":page.evaluate(PUBLIC_TOOLBAR_READ)}
            scope = price_scope(self.spec, page.url, site.url)
            if scope is not None and value["public"].get("products"):
                scope = observed_toolbar_scope(scope,value["toolbar"])
                current = native_page_reference(site, scope, auth["username"])
                if price_reference_identity(current) != price_reference_identity(self.reference):
                    raise RuntimeError("Native current page differs from original filter universe")
                value["private_current_reference"] = current
            value["private_baseline_reference"] = deepcopy(self.reference)
            return value
        if self.guest:
            from lab_generate_skill.site_database import select_rows
            saved = select_rows(site, "SELECT * FROM catalog_compare_item ORDER BY catalog_compare_item_id")
            return {"public": page.evaluate(COMPARE_READ), "saved": guest_saved(self.before, saved),
                    "private_baseline_reference": deepcopy(self.reference)}
        if self.events is None: raise RuntimeError("Passive native Reorder event observer was not attached")
        return {"saved": read_saved_cart(site, auth["username"]), "events": self.events.snapshot(),
                "private_baseline_reference": deepcopy(self.reference), "private_initial_saved": deepcopy(self.before)}

    def evaluate(self, site, page, state, *, runtime_error=None):
        ref = state.get("private_current_reference", self.reference) if isinstance(state, dict) else self.reference
        return evaluate(self.contract, page, state, ref, site_origin=site.url, before=self.before, runtime_error=runtime_error)

    def close(self):
        if self.events is not None: self.events.close()

    def protected_unchanged(self, site):
        actual = protected_state(site, self.spec,
             cart_id=self.before["cart_id"] if self.spec["kind"] == "reorder" else None)
        return (self.protected_before is not None and actual == self.protected_before
                and reference(site, self.contract, self.auth) == self.expected)
