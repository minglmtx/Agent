"""Checkout terminal-state checks. Private database values never enter prompts.

Native shipping/payment navigation may update quote addresses and totals. It
must not change cart products, saved customer addresses, coupons, or orders.
The evaluator reads the final form; a hash or a claimed completion is insufficient.
"""
from urllib.parse import urlsplit

from .site_cart_rules import cart_state
from .site_database import select_rows
from .site_navigation_rules import valid_initial_page
from .site_query_rules import reference_fingerprint

VERSION = 'shopping-checkout-v1'
ADMISSION_VERSION = 'shopping-checkout-admission-v1'
MODES = {'checkout', 'payment', 'discount_checkout', 'discount_any', 'cart_or_checkout'}


def checkout_state(site, username, *, expected_cart_id=None):
    if expected_cart_id is None:
        cart = cart_state(site, username)
    else:
        # An actor can place an unintended order and deactivate the original
        # quote. Still capture that quote and the new order; lack of an active
        # cart is then a scored side effect, not an evaluator exception.
        accounts = select_rows(site, "SELECT entity_id FROM customer_entity WHERE email='"+username.replace("'", "''")+"'")
        if len(accounts) != 1: raise ValueError('Checkout account missing or ambiguous')
        uid = int(accounts[0]['entity_id']); qid = int(expected_cart_id)
        quotes = select_rows(site, f'SELECT entity_id,coupon_code FROM quote WHERE customer_id={uid} AND entity_id={qid}')
        if len(quotes) != 1: raise ValueError('Original checkout quote missing')
        items = select_rows(site, f'SELECT item_id,product_id,parent_item_id,sku,name,qty,price FROM quote_item WHERE quote_id={qid} ORDER BY item_id')
        cart = {'user_id': uid, 'cart_id': qid, 'coupon_code': quotes[0]['coupon_code'], 'items': items}
    uid, qid = int(cart['user_id']), int(cart['cart_id'])
    return {
        'cart': cart,
        'account': select_rows(site, f'SELECT entity_id,default_shipping,default_billing FROM customer_entity WHERE entity_id={uid}'),
        'saved_addresses': select_rows(site, f'SELECT entity_id,parent_id,firstname,lastname,street,city,country_id,region_id,region,postcode,telephone FROM customer_address_entity WHERE parent_id={uid} ORDER BY entity_id'),
        'orders': select_rows(site, f'SELECT entity_id,increment_id,status,grand_total FROM sales_order WHERE customer_id={uid} ORDER BY entity_id'),
        'quote_addresses': select_rows(site, f'SELECT address_id,address_type,customer_address_id,firstname,lastname,street,city,country_id,region_id,region,postcode,telephone,shipping_method,shipping_amount FROM quote_address WHERE quote_id={qid} ORDER BY address_id'),
    }


def read_checkout_page(page):
    return page.evaluate(r'''() => {
      const visible=e=>!!e && !!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
      const all=s=>[...document.querySelectorAll(s)].filter(visible);
      const c=window.checkoutConfig||{};
      const coupon=all('#discount-code,#discount-coupon-form input[name="coupon_code"]');
      return {
        logged_in:c.isCustomerLoggedIn===true,customer_id:c.customerData?.id??null,quote_id:c.quoteData?.entity_id??null,
        shipping_visible:all('#checkout-step-shipping').length>0 && all('#co-shipping-method-form input[type=radio]').length>0,
        payment_visible:all('#payment .payment-method-title').length>0 && all('#payment .action.checkout').length>0,
        addresses:all('.shipping-address-item').map(e=>({text:e.innerText,selected:e.classList.contains('selected-item')})),
        shipping_methods:all('#co-shipping-method-form input[type=radio]').map(e=>({value:e.value,checked:e.checked})),
        coupon_inputs:coupon.map(e=>({id:e.id,enabled:!e.disabled,value:e.value})),
        cart_item_ids:all('#shopping-cart-table input[name]').map(e=>e.name.match(/^cart\[(\d+)\]\[qty\]$/)?.[1]).filter(Boolean),
        cart_visible:all('#shopping-cart-table').length>0,
        loaders:all('.loading-mask').length
      };
    }''')


def validate_initial(c, state):
    spec = c['checkout']
    if spec['mode'] not in MODES: raise ValueError('Unsupported checkout mode')
    cart = state['cart']
    if cart['user_id'] != spec['customer_id'] or cart['cart_id'] != spec['cart_id'] or not cart['items']:
        raise ValueError('Checkout account/cart baseline absent')
    if len(state['account']) != 1 or not state['saved_addresses']:
        raise ValueError('Missing deterministic checkout address baseline')


def evaluate_checkout(c, page, initial, final, *, site_origin, runtime_error=None):
    def unknown(reason, checks=None):
        return {'version': VERSION, 'status': 'unknown', 'reward': None, 'checks': checks or {}, 'reason': reason}
    def result(checks):
        ok = all(checks.values())
        return {'version': VERSION, 'status': 'success' if ok else 'failure', 'reward': float(ok), 'checks': checks, 'reason': None}
    if runtime_error: return unknown('Runtime error prevents terminal checkout evaluation')
    if not isinstance(page, dict) or type(page.get('http_status')) is not int or page['http_status'] < 200 or page['http_status'] >= 500:
        return unknown('Missing terminal page or transport/server failure')
    checks = {'page_valid': valid_initial_page(page, site_origin=site_origin)}
    mode = c['checkout']['mode']
    if mode not in MODES: raise ValueError('Unsupported checkout mode')
    path = urlsplit(page.get('url', '')).path.rstrip('/')
    accepts_cart = mode in ('cart_or_checkout', 'discount_any')
    checks['checkout_location'] = path == '/checkout' or (accepts_cart and path == '/checkout/cart')
    location_valid = all(checks.values())
    state_complete = all(isinstance(s, dict) and {'cart','account','saved_addresses','orders'} <= s.keys()
                         and isinstance(s['cart'],dict) and 'user_id' in s['cart'] for s in (initial,final))
    # Final-page failure must not hide independently captured side effects.
    # Teacher feedback describes observed failed conditions, never a click plan.
    if state_complete:
        before, after = initial['cart'], final['cart']
        checks['checkout_account_unchanged'] = before['user_id'] == after['user_id'] == c['checkout']['customer_id']
        checks['checkout_cart_unchanged'] = before == after
        checks['checkout_saved_addresses_unchanged'] = initial['account'] == final['account'] and initial['saved_addresses'] == final['saved_addresses']
        checks['checkout_orders_unchanged'] = initial['orders'] == final['orders']
    if not location_valid: return result(checks)
    if not state_complete: return unknown('Checkout state capture missing', checks)
    ui = page.get('checkout')
    required = {'logged_in', 'customer_id', 'quote_id', 'shipping_visible', 'payment_visible', 'addresses', 'shipping_methods', 'coupon_inputs', 'cart_item_ids', 'cart_visible', 'loaders'}
    if not isinstance(ui, dict) or not required <= ui.keys(): return unknown('Native checkout form capture incomplete', checks)
    if ui['loaders']: return unknown('Checkout still loading at terminal capture', checks)
    if path == '/checkout/cart':
        checks['native_cart_identity'] = ui['cart_visible'] and sorted(map(str, ui['cart_item_ids'])) == sorted(str(r['item_id']) for r in after['items'])
        checks['requested_checkout_stage'] = accepts_cart
    else:
        checks['native_cart_identity'] = ui['logged_in'] and str(ui['customer_id']) == str(after['user_id']) and str(ui['quote_id']) == str(after['cart_id'])
        shipping_ready = ui['shipping_visible'] and any(x['selected'] for x in ui['addresses']) and bool(ui['shipping_methods'])
        checks['requested_checkout_stage'] = bool(ui['payment_visible'] if mode in ('payment', 'discount_checkout', 'discount_any') else shipping_ready or ui['payment_visible'])
        if ui['payment_visible']:
            addresses = [r for r in final['quote_addresses'] if r['address_type'] == 'shipping']
            checks['shipping_information_saved'] = len(addresses) == 1 and all(addresses[0].get(k) for k in ('shipping_method', 'firstname', 'lastname', 'street', 'city', 'country_id', 'postcode'))
    if mode.startswith('discount_'):
        checks['discount_field_open'] = len(ui['coupon_inputs']) == 1 and ui['coupon_inputs'][0]['enabled']
    return result(checks)


def checkout_feedback(judgment):
    meanings = {
        'page_valid': 'The final page is valid on the task website.',
        'checkout_location': 'The final page is in the requested cart or checkout area.',
        'checkout_account_unchanged': 'The original customer account is still in use.',
        'checkout_cart_unchanged': 'The original cart products, quantities and coupon remain unchanged.',
        'checkout_saved_addresses_unchanged': 'Existing customer profile addresses remain unchanged.',
        'checkout_orders_unchanged': 'No order was placed by this navigation-only task.',
        'native_cart_identity': 'The displayed native form belongs to the current customer and cart.',
        'requested_checkout_stage': 'The requested checkout stage is displayed and ready.',
        'shipping_information_saved': 'The shipping information required for payment has been saved.',
        'discount_field_open': 'The promotional-code field is expanded and available for entry.',
    }
    return {'status': judgment['status'], 'reward': judgment['reward'], 'reason': judgment.get('reason'),
            'checks': [{'name': k, 'passed': v, 'condition': meanings[k]} for k, v in judgment['checks'].items()],
            'action_sequence_provided': False}


def contract_fingerprint(c):
    return reference_fingerprint({k: c.get(k) for k in ('task_id', 'source_task_id', 'domain', 'goal', 'start_path', 'checkout', 'heldout_quarantine', 'start_revision', 'goal_revision')})


def control_results(c):
    result = {k: 'failure' for k in ('no_op', 'wrong_target', 'url_only', 'wrong_cart', '404', 'login')}
    result['positive'] = 'success'
    if c['checkout']['mode'] == 'checkout': result['payment_alternative'] = 'success'
    if c['checkout']['mode'] == 'payment': result['unsaved_shipping'] = 'failure'
    if c['checkout']['mode'].startswith('discount_'): result['closed_panel'] = 'failure'
    if c['checkout']['mode'] in ('cart_or_checkout', 'discount_any'): result['cart_alternative'] = 'success'
    return result


def require_checkout_admission(c, proof):
    if c.get('heldout_quarantine'): raise ValueError('Heldout source is quarantined')
    if proof.get('admission_version') != ADMISSION_VERSION or proof.get('contract_fingerprint') != contract_fingerprint(c):
        raise ValueError('Stale checkout admission')
    cycles = proof.get('cycles', [])
    if not proof.get('passed') or len(cycles) != 2: raise ValueError('Two independent checkout control/reset cycles required')
    for row in cycles:
        if not row.get('passed') or row.get('checks') != control_results(c) or not row.get('selected_records_unchanged'):
            raise ValueError('Checkout controls failed')
        validate_initial(c, row['initial_state'])
    if cycles[0]['initial_state'] != cycles[1]['initial_state'] or cycles[0]['initial_fingerprint'] != cycles[1]['initial_fingerprint']:
        raise ValueError('Checkout baseline changed across independent resets')
