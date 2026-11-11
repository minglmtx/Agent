"""Read-only completion evidence for the native Recently Ordered component.

The expected items belong to a private, independently verified order reference.
Neither an order-history table nor a matching page title establishes that these
products are displayed. This module never loads AMD modules, reloads sections,
changes the page, or supplies an action plan.
"""
import re
from urllib.parse import unquote, urlsplit

VERSION = 'native-recent-items-v1'

READ = r'''() => {
 const visible=e=>{
   if(!e || !e.getClientRects().length)return false;
   for(let n=e;n;n=n.parentElement){
     const s=getComputedStyle(n);
     if(s.display==='none'||s.visibility==='hidden'||s.visibility==='collapse'||Number(s.opacity)===0)return false;
   }
   return true;
 };
 const moduleName='Magento_Customer/js/customer-data';
 const defined=typeof window.require==='function' && typeof window.require.defined==='function' && window.require.defined(moduleName);
 let initialization=null,nativeItems=null;
 if(defined){
   const data=window.require(moduleName);
   initialization=data.getInitCustomerData().state();
   const section=data.get('last-ordered-items')();
   // Keep malformed values as they are: the checker must report a broken
   // capture rather than silently turn them into an empty successful list.
   nativeItems=section.items===undefined?null:section.items;
   if(Array.isArray(nativeItems))nativeItems=nativeItems.map(x=>x && typeof x==='object'?{id:x.id,product_id:x.product_id,name:x.name,url:x.url}:x);
 }
 const blocks=[...document.querySelectorAll('.block-reorder')].map(block=>{
   const heading=block.querySelector('#block-reorder-heading');
   const content=block.querySelector('.block-content');
   return {scope:block.getAttribute('data-bind')||'',visible:visible(block),
     heading:{text:heading?.innerText.trim()||'',visible:visible(heading)},
     content_visible:visible(content),
     items:[...block.querySelectorAll('#cart-sidebar-reorder > li')].map(item=>({
       visible:visible(item),
       order_item_ids:[...item.querySelectorAll('input[type=checkbox][name="order_items[]"]')].map(input=>input.value),
       links:[...item.querySelectorAll('a.product-item-link[href]')].map(link=>({name:link.innerText.trim(),url:link.href,visible:visible(link)}))
     }))};
 });
 return {capture_version:'native-recent-items-v1',url:location.href,
   module_defined:!!defined,initialization_state:initialization,native_items:nativeItems,blocks};
}'''


def read_recent_items(page):
    """Capture public native values without waiting, navigating, or preloading."""
    return page.evaluate(READ)


def _positive_id(value):
    # Native PHP JSON values may be integers or decimal strings; checkbox
    # values are always strings. Never accept bools, floats, or loose coercion.
    if type(value) is int and value > 0:
        return value
    if isinstance(value, str) and re.fullmatch(r'[1-9][0-9]*', value):
        return int(value)
    raise ValueError('Invalid native positive item identifier')


def _text(value):
    if not isinstance(value, str):
        raise ValueError('Malformed recent-item text')
    return ' '.join(value.split())


def _path(value):
    if not isinstance(value, str) or not value.startswith('/'):
        raise ValueError('Expected an absolute local product path')
    parsed = urlsplit(value)
    decoded = unquote(parsed.path)
    if (parsed.scheme or parsed.netloc or parsed.query or parsed.fragment
            or any(part in ('.', '..') for part in decoded.split('/'))
            or decoded.startswith('//') or '\\' in decoded):
        raise ValueError('Product reference must be a local path without query or fragment')
    return decoded


def validate(spec):
    if not isinstance(spec, dict) or set(spec) != {'items'}:
        raise ValueError('Explicit private recent-item reference required')
    items = spec['items']
    if not isinstance(items, list) or not items:
        raise ValueError('Nonempty recent-item reference required')
    seen = set()
    for item in items:
        if not isinstance(item, dict) or set(item) != {'order_item_id', 'product_id', 'name', 'product_path'}:
            raise ValueError('Malformed recent-item reference')
        for key in ('order_item_id', 'product_id'):
            if type(item[key]) is not int or item[key] <= 0:
                raise ValueError('Reference identifiers must be positive integers')
        if not _text(item['name']) or item['order_item_id'] in seen:
            raise ValueError('Recent-item reference is empty or ambiguous')
        seen.add(item['order_item_id'])
        _path(item['product_path'])


def _local_product_path(value, origin):
    if not isinstance(value, str):
        raise ValueError('Malformed native product URL')
    parsed = urlsplit(value)
    if ((parsed.scheme, parsed.netloc) != (origin.scheme, origin.netloc)
            or parsed.query or parsed.fragment):
        return None
    try:
        return _path(parsed.path)
    except ValueError:
        return None


def _native_items(items, origin):
    if not isinstance(items, list):
        raise ValueError('Malformed native recent-item list')
    result = []
    for item in items:
        if not isinstance(item, dict) or any(key not in item for key in ('id', 'product_id', 'name', 'url')):
            raise ValueError('Incomplete native recent-item identity')
        result.append((_positive_id(item['id']), _positive_id(item['product_id']),
                       _text(item['name']), _local_product_path(item['url'], origin)))
    return result


def _displayed_items(block, expected, origin):
    result = []
    complete = True
    for item in block['items']:
        if (not isinstance(item, dict) or type(item.get('visible')) is not bool
                or not isinstance(item.get('order_item_ids'), list)
                or not isinstance(item.get('links'), list)):
            raise ValueError('Malformed native widget item')
        ids = [_positive_id(value) for value in item['order_item_ids']]
        links = []
        for link in item['links']:
            if not isinstance(link, dict) or type(link.get('visible')) is not bool:
                raise ValueError('Malformed native widget product link')
            links.append((_text(link.get('name')), _local_product_path(link.get('url'), origin), link['visible']))
        if not item['visible'] or len(ids) != 1 or len(links) != 1 or not links[0][2]:
            complete = False
        else:
            result.append((ids[0], links[0][0], links[0][1]))
    wanted = [(row[0], row[2], row[3]) for row in expected]
    return complete and len(result) == len(wanted) and set(result) == set(wanted)


def checks(spec, state, *, site_origin):
    validate(spec)
    if (not isinstance(state, dict) or state.get('capture_version') != VERSION
            or not isinstance(state.get('url'), str)
            or type(state.get('module_defined')) is not bool
            or state.get('initialization_state') not in (None, 'pending', 'resolved', 'rejected')
            or not isinstance(state.get('blocks'), list)
            or 'native_items' not in state):
        raise ValueError('Missing or malformed native recent-item capture')
    origin = urlsplit(site_origin)
    if origin.scheme not in ('http', 'https') or not origin.netloc or origin.path not in ('', '/') or origin.query or origin.fragment:
        raise ValueError('Explicit local website origin required')
    current = urlsplit(state['url'])
    account = ((current.scheme, current.netloc) == (origin.scheme, origin.netloc)
               and current.path in ('/customer/account', '/customer/account/')
               and not current.query and current.fragment in ('', 'my-orders-table'))
    expected = [(item['order_item_id'], item['product_id'], _text(item['name']), _path(item['product_path']))
                for item in spec['items']]
    ready = state['module_defined'] and state['initialization_state'] == 'resolved' and state['native_items'] is not None
    native = _native_items(state['native_items'], origin) if state['native_items'] is not None else None
    reference_matches = bool(ready and len(native) == len(expected) and set(native) == set(expected))
    components = []
    for block in state['blocks']:
        if (not isinstance(block, dict) or not isinstance(block.get('scope'), str)
                or type(block.get('visible')) is not bool
                or type(block.get('content_visible')) is not bool
                or not isinstance(block.get('heading'), dict)
                or type(block['heading'].get('visible')) is not bool
                or not isinstance(block['heading'].get('text'), str)
                or not isinstance(block.get('items'), list)):
            raise ValueError('Malformed native Recently Ordered component')
        # Validate nested types even when a shell is currently hidden.
        displayed = _displayed_items(block, expected, origin)
        scoped = bool(re.fullmatch(r"\s*scope\s*:\s*(['\"])lastOrderedItems\1\s*", block['scope']))
        if (scoped and block['visible'] and block['content_visible']
                and block['heading']['visible'] and _text(block['heading']['text']) == 'Recently Ordered'):
            components.append(displayed)
    visible = len(components) == 1
    return {'recent_items_account_page': account,
            'recent_items_native_initialized': bool(ready),
            'recent_items_native_reference': reference_matches,
            'recent_items_component_visible': visible,
            'recent_items_displayed_complete': bool(visible and components[0])}


FEEDBACK = {
    'recent_items_account_page': 'The current account page is displayed on the task website.',
    'recent_items_native_initialized': 'The native recently ordered data has finished initializing.',
    'recent_items_native_reference': 'The displayed data belongs to the complete referenced recent order.',
    'recent_items_component_visible': 'The native Recently Ordered component is visible.',
    'recent_items_displayed_complete': 'All referenced recently ordered products are displayed with their correct identities.',
}


def verify_reference(site, spec, username):
    """Verify private expected order items belong to the authenticated baseline."""
    validate(spec)
    from .site_cart_rules import cart_state
    from .site_database import select_rows
    customer_id=cart_state(site, username)['user_id']
    ids=','.join(str(item['order_item_id']) for item in spec['items'])
    rows=select_rows(site,'SELECT i.item_id,i.product_id,i.name,o.customer_id FROM sales_order_item i '
        'JOIN sales_order o ON o.entity_id=i.order_id WHERE i.item_id IN ('+ids+') ORDER BY i.item_id')
    expected=sorted((item['order_item_id'],item['product_id'],_text(item['name']),customer_id)for item in spec['items'])
    actual=sorted((row['item_id'],row['product_id'],_text(row['name']),row['customer_id'])for row in rows)
    if actual!=expected:raise ValueError('Recent-item private order reference or account changed')
    return {'customer_id':customer_id,'order_item_ids':sorted(item['order_item_id']for item in spec['items'])}
