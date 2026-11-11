"""Terminal cart contents, independent of whether Magento uses a page or popup.

Explicit candidate capability for read-only cart-view goals. It is not an
automatic replacement for page-navigation, checkout or item-details goals.
Private cart identity is read before execution and never sent to the actor.
"""
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit
from .site_navigation_rules import valid_initial_page

VERSION = 'shopping-complete-cart-view-v1'


def read(page):
    return page.evaluate(r'''() => {
      const shown=e=>!!e && e.getClientRects().length>0 &&
        getComputedStyle(e).visibility!=='hidden' && getComputedStyle(e).display!=='none';
      const norm=s=>(s||'').replace(/\s+/g,' ').trim();
      const rows=(root, selector)=>[...(root?.querySelectorAll(selector)||[])].map(e=>{
        const qty=e.querySelector('input[data-cart-item],input[name^="cart["]');
        const edit=e.querySelector('a.edit,a.action-edit');
        return {visible:shown(e), name:norm(e.querySelector('.product-item-name')?.textContent),
          quantity:qty?.value??null, item_id:qty?.getAttribute('data-cart-item')||
            qty?.getAttribute('name')?.match(/^cart\[(\d+)\]\[qty\]$/)?.[1]||null,
          edit_url:edit?.href||''};
      });
      const mini=document.querySelector('[data-block="minicart"] [data-role="dropdownDialog"]');
      const cart=document.querySelector('#shopping-cart-table');
      return {version:'shopping-complete-cart-view-v1',url:location.href,
        surfaces:[{kind:'minicart',open:shown(mini),items:rows(mini,'.minicart-items .product-item')},
                  {kind:'cart_page',open:shown(cart),items:rows(cart,'tbody.cart.item')}]};
    }''')


def _items_match(items, reference, origin):
    if not isinstance(items, list) or len(items) != len(reference):
        return False
    refs = {str(r['item_id']): r for r in reference}
    if len(refs) != len(reference):
        raise ValueError('Duplicate private cart item identity')
    seen = set()
    for item in items:
        if not isinstance(item, dict) or item.get('visible') is not True:
            return False
        ident = item.get('item_id')
        if ident not in refs or ident in seen:
            return False
        seen.add(ident)
        ref = refs[ident]
        if item.get('name') != ' '.join(ref['name'].split()):
            return False
        try:
            qty = Decimal(str(item.get('quantity')))
            if not qty.is_finite() or qty != Decimal(str(ref['qty'])):
                return False
        except InvalidOperation:
            return False
        edit = urlsplit(item.get('edit_url', ''))
        expected = f'/checkout/cart/configure/id/{ident}/product_id/{ref["product_id"]}/'
        if ((edit.scheme, edit.netloc) != (origin.scheme, origin.netloc)
                or edit.path != expected or edit.query or edit.fragment):
            return False
    return True


def evaluate(page, view, initial, final, *, site_origin):
    try:
        if not initial or not final or not isinstance(initial.get('items'), list):
            raise ValueError('Actual before/after cart reference required')
        if not initial['items']:
            raise ValueError('Empty cart surface needs separate native controls')
        if not isinstance(page, dict) or not isinstance(page.get('http_status'), int):
            raise ValueError('Native terminal HTTP state required')
        if page['http_status'] < 200 or page['http_status'] >= 500:
            raise ValueError('Transport/server failure')
        valid = valid_initial_page(page, site_origin=site_origin)
        checks = {'page_valid': valid, 'cart_reference_unchanged': initial == final}
        if valid:
            if (not isinstance(view, dict) or view.get('version') != VERSION
                    or view.get('url') != page['url'] or not isinstance(view.get('surfaces'), list)):
                raise ValueError('Bound native cart-view capture required')
            origin = urlsplit(site_origin)
            checks['complete_cart_items_displayed'] = any(
                s.get('kind') in {'cart_page', 'minicart'} and s.get('open') is True
                and (s['kind'] != 'cart_page' or urlsplit(page['url']).path.rstrip('/') == '/checkout/cart')
                and _items_match(s.get('items'), initial['items'], origin)
                for s in view['surfaces'] if isinstance(s, dict))
        passed = all(checks.values())
        return {'version': VERSION, 'status': 'success' if passed else 'failure',
                'reward': float(passed), 'checks': checks}
    except (ValueError, KeyError, TypeError) as exc:
        return {'version': VERSION, 'status': 'unknown', 'reward': None,
                'checks': {}, 'reason': str(exc)}
