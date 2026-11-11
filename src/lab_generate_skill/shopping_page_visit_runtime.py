"""Candidate native outcomes for account-section and category browsing goals.

The common runner records real pages; it never navigates on behalf of an actor.
All comparisons and reference identities remain private until terminal judging.
"""
from copy import deepcopy
import hashlib
from pathlib import Path
from urllib.parse import urlsplit

from .io_utils import atomic_write_json
from .original_goal_binding import require_local_origin
from .source_revision_binding import binding, fingerprint, require_source_binding
from .site_database import select_rows
from .site_navigation_rules import valid_initial_page
from .shopping_category import category_checks, category_metadata, category_products, read_category_page

VERSION = 'shopping-page-visit-native-runtime-v1'
PROOF = 'shopping-page-visit-native-two-cold-v1'


def enabled(contract):
    if 'shopping_page_visit' not in contract:
        return False
    spec = contract['shopping_page_visit']
    if (contract.get('domain') != 'shopping' or spec.get('version') != VERSION
            or spec.get('kind') not in ('account_profile_history', 'category_products')
            or contract.get('eligible_for_training') is not False
            or any(contract.get(k) for k in ('completion', 'cart', 'query', 'search',
                                             'shopping_cart_view', 'offline_training'))):
        raise ValueError('One explicitly bound read-only page-visit family required')
    binding(contract)
    return True


def fields(contract):
    enabled(contract)
    return []


def public_goal(contract):
    enabled(contract)
    return contract['goal']


def require_original_binding(contract, original, inventory):
    enabled(contract)
    return require_source_binding(contract, original, inventory, domain='shopping')


def reference(site, contract, username):
    enabled(contract)
    spec = contract['shopping_page_visit']
    if spec['kind'] == 'category_products':
        name = "'" + spec['category_name'].replace("'", "''") + "'"
        rows = select_rows(site, "SELECT e.entity_id FROM catalog_category_entity e "
            "JOIN catalog_category_entity_varchar n ON n.entity_id=e.entity_id AND n.store_id=0 "
            "AND n.attribute_id=(SELECT attribute_id FROM eav_attribute WHERE entity_type_id=3 "
            "AND attribute_code='name') WHERE n.value=" + name)
        if len(rows) != 1:
            raise ValueError('Exactly one native requested category required')
        ident = int(rows[0]['entity_id'])
        return {'category_id': ident, 'metadata': category_metadata(site, [ident]),
                'product_index': category_products(site, ident), 'routes': deepcopy(spec['routes'])}
    quoted = "'" + username.replace("'", "''") + "'"
    rows = select_rows(site, 'SELECT entity_id,firstname,lastname,email FROM customer_entity WHERE email=' + quoted)
    if len(rows) != 1:
        raise ValueError('Exactly one native task-account identity required')
    return rows[0]


def read(page):
    from probe_content_sites import capture_current
    health = capture_current(page, 'shopping')
    native = page.evaluate(r'''() => {
      const shown=e=>!!e&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
      const profile=document.querySelector('.block-dashboard-info .box-information .box-content');
      const orders=document.querySelector('.orders-history,#my-orders-table');
      const empty=document.querySelector('main .message.info.empty');
      const product=document.querySelector('#product_addtocart_form input[name="product"]');
      const title=document.querySelector('h1 .base');
      return {profile_text:shown(profile)?profile.innerText.trim():null,
        orders_visible:shown(orders),orders_empty_text:shown(empty)?empty.innerText.trim():null,
        product_id:product?.value??null,product_title:shown(title)?title.innerText.trim():null,
        body_classes:document.body.className};
    }''')
    return {'page': health, 'native': native, 'category': read_category_page(page)}


def evaluate(contract, private, timeline, terminal, *, site_origin):
    enabled(contract)
    def unknown():
        return {'version': VERSION, 'status': 'unknown', 'reward': None, 'checks': {}}
    if not isinstance(terminal, dict) or not timeline or timeline[-1]['page'] != terminal:
        return unknown()
    if any(type(r['page'].get('http_status')) is not int or not 200 <= r['page']['http_status'] < 500 for r in timeline):
        return unknown()
    spec = contract['shopping_page_visit']
    checks = {'terminal_page_valid': valid_initial_page(terminal, site_origin=site_origin)}
    origin = urlsplit(site_origin)
    def valid(row):
        return valid_initial_page(row['page'], site_origin=site_origin)
    if spec['kind'] == 'account_profile_history':
        name = private['firstname'] + ' ' + private['lastname']
        def profile(row):
            text = row['native']['profile_text']
            return (valid(row) and urlsplit(row['page']['url']).path.rstrip('/') == '/customer/account'
                    and text is not None and name in text.splitlines() and private['email'] in text.splitlines())
        def history(row):
            return (valid(row) and urlsplit(row['page']['url']).path.rstrip('/') == '/sales/order/history'
                    and row['page']['title'] == 'My Orders'
                    and (row['native']['orders_visible'] is True
                         or row['native']['orders_empty_text'] == 'You have placed no orders.'))
        checks.update(profile_displayed=any(profile(r) for r in timeline),
                      order_history_displayed=any(history(r) for r in timeline),
                      terminal_in_requested_account_sections=profile(timeline[-1]) or history(timeline[-1]))
    else:
        def category(row):
            return valid(row) and all(category_checks(private, row['category'], row['page']['url']).values())
        last = timeline[-1]
        product = last['native']
        allowed = {str(r['product_id']) for r in private['product_index'] if r['visibility'] in (2, 4)}
        path = urlsplit(last['page']['url'])
        real_product = (valid(last) and 'catalog-product-view' in product['body_classes'].split()
                        and product['product_id'] in allowed and product['product_title']
                        and product['product_title'] == last['category']['heading']
                        and (path.scheme, path.netloc) == (origin.scheme, origin.netloc))
        checks.update(requested_category_displayed=any(category(r) for r in timeline),
                      terminal_requested_category_or_member=category(last) or bool(real_product))
    passed = all(checks.values())
    return {'version': VERSION, 'status': 'success' if passed else 'failure',
            'reward': float(passed), 'checks': checks}


def require_admission(contract, proof):
    enabled(contract)
    if (proof.get('version') != PROOF or proof.get('fingerprint') != fingerprint(contract)
            or proof.get('source_binding') != binding(contract)
            or proof.get('runtime_sha256') != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            or proof.get('actor_attempts') != 0 or proof.get('api_calls') != 0):
        raise ValueError('Source-bound actual common lifecycle proof required')
    cycles = proof.get('cycles', [])
    if len(cycles) != 2 or [r.get('cycle') for r in cycles] != [0, 1]:
        raise ValueError('Two distinct fresh source controls required')
    expected = {'no_op': 'failure', 'positive': 'success', 'wrong_target': 'failure',
                '404': 'failure', 'login': 'failure'}
    if contract['shopping_page_visit']['kind'] == 'category_products':
        expected['member_product'] = 'success'
    else:
        expected['profile_only'] = expected['history_only'] = 'failure'
    for cycle in cycles:
        require_local_origin(cycle['site_origin'])
        if (cycle['before'] != cycle['after'] or cycle.get('fresh_instance_id') is None
                or set(cycle['controls']) != set(expected)):
            raise ValueError('Complete unchanged normal source controls required')
        for name, status in expected.items():
            row = cycle['controls'][name]
            verdict = evaluate(contract, cycle['private_reference'], row['timeline'], row['terminal'],
                               site_origin=cycle['site_origin'])
            if (verdict != row['judgment'] or verdict['status'] != status
                    or row.get('integrity') is not True or row.get('original_start_preserved') is not True
                    or row.get('actual_common_lifecycle') is not True
                    or row['before'] != cycle['before'] or row['after'] != cycle['after']):
                raise ValueError('Native control or common lifecycle mismatch: ' + name)
            if name == 'login' and row['terminal'].get('login_page') is not True:
                raise ValueError('Real unauthenticated negative required')
    if (cycles[0]['before'] != cycles[1]['before']
            or cycles[0]['private_reference'] != cycles[1]['private_reference']
            or cycles[0]['fresh_instance_id'] == cycles[1]['fresh_instance_id']):
        raise ValueError('Cold native baseline/reference mismatch')
    return deepcopy(cycles[0]['private_reference'])


class PageVisitHooks:
    def __init__(self, contract, directory, *, proof=None):
        enabled(contract)
        self.contract, self.directory = deepcopy(contract), Path(directory)
        self.private = require_admission(contract, proof) if proof is not None else None
        self.expected_before = proof['cycles'][0]['before'] if proof is not None else None
        self.site = self.context = self.initial = None
        self.timeline = []
        self.scored = False

    def prepare(self, site, username):
        if self.site is not None:
            raise ValueError('One native episode required')
        actual = reference(site, self.contract, username)
        before = site.fingerprint()
        if self.private is not None and (actual != self.private or before != self.expected_before):
            raise ValueError('Actual task/reset differs from controls')
        self.site, self.username, self.private, self.before = site, username, actual, before

    def attach(self, context):
        if self.site is None or self.context is not None:
            raise ValueError('One prepared context required')
        self.context = context

    def observe_initial(self, page):
        if page.context is not self.context or self.initial is not None:
            raise ValueError('One actual initial document required')
        if page.url != self.site.url + self.contract['start_path']:
            raise ValueError('Original first start changed')
        self.initial = page

    def record(self, page):
        if page is not self.initial or self.scored:
            raise ValueError('Only actual episode page records required')
        self.timeline.append(read(page))

    def capture_terminal(self, page, terminal):
        self.record(page)
        # The shared runner captures a bounded terminal page text; retain its
        # exact health as the last page so no second read is trusted as terminal.
        self.timeline[-1]['page'] = deepcopy(terminal)

    def score_terminal(self, site, terminal, *, runtime_error=None):
        if self.scored or site is not self.site:
            raise ValueError('One terminal score required')
        self.scored = True
        after = site.fingerprint()
        integrity = self.before == after and reference(site, self.contract, self.username) == self.private
        verdict = evaluate(self.contract, self.private, self.timeline, terminal, site_origin=site.url)
        if runtime_error or not integrity:
            verdict = {'version': VERSION, 'status': 'unknown', 'reward': None, 'checks': {}}
        atomic_write_json(self.directory / 'private-page-visit-result.json', {
            'before': self.before, 'after': after, 'private_reference': self.private,
            'timeline': self.timeline, 'terminal': terminal, 'judgment': verdict, 'integrity': integrity})
        return verdict, integrity

    def close(self):
        pass


def feedback(judgment):
    return {'status': judgment['status'], 'checks': [
        {'condition': key.replace('_', ' ') + '.', 'passed': value}
        for key, value in judgment['checks'].items()]}
