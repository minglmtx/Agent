"""Private native Shopping scope and persisted-state checks; no actor policy.

These helpers have no training/admission side effects. All object identities come
from the source plan and native references, never an actor-selected object.
"""
from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

from .site_database import select_rows

VERSION = 'shopping-seven-native-capability-v1'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def positive_int(value):
    if type(value) is not int or value <= 0:
        raise ValueError('Positive native integer identity required')
    return value


def decimal(value):
    if isinstance(value, bool): raise ValueError('Boolean is not a price or quantity')
    try: result = Decimal(str(value))
    except (InvalidOperation, ValueError): raise ValueError('Invalid native decimal') from None
    if not result.is_finite(): raise ValueError('Finite native decimal required')
    return result


def read_saved_cart(site, username):
    from .site_cart_rules import cart_state
    state = cart_state(site, username)
    q = positive_int(state['cart_id'])
    state['saved_items'] = select_rows(site, f'SELECT * FROM quote_item WHERE quote_id={q} ORDER BY item_id')
    state['item_options'] = select_rows(site, f'SELECT o.* FROM quote_item_option o JOIN quote_item i ON i.item_id=o.item_id WHERE i.quote_id={q} ORDER BY o.option_id')
    return state


def option_map(state, item_id):
    rows = [r for r in state['item_options'] if r['item_id'] == item_id]
    if len({r['code'] for r in rows}) != len(rows): raise ValueError('Duplicate saved option code')
    selections = {r['code'][7:]: str(r['value']) for r in rows if r['code'].startswith('option_') and r['code'] != 'option_ids'}
    index = [r for r in rows if r['code'] == 'option_ids']
    if selections:
        if len(index) != 1 or set(str(index[0]['value']).split(',')) != set(selections):
            raise ValueError('Saved native custom-option index differs from its values')
    elif index and str(index[0]['value'] or ''):
        raise ValueError('Saved custom-option index has no values')
    return selections


def validate_reorder_reference(reference):
    account = positive_int(reference['account']['entity_id'])
    if len(reference.get('orders', [])) != 1: raise ValueError('Unique original completed order required')
    order = reference['orders'][0]
    positive_int(order['entity_id'])
    if order['customer_id'] != account or order['status'] != 'complete':
        raise ValueError('Original completed order must belong to the account')
    items = reference.get('items')
    if not isinstance(items, list) or not items: raise ValueError('Complete original order items required')
    if len({r['item_id'] for r in items}) != len(items): raise ValueError('Duplicate original order item')
    expected = {}
    for item in items:
        product = positive_int(item['product_id'])
        if item['order_id'] != order['entity_id'] or item['parent_item_id'] is not None or item['product_type'] != 'simple':
            raise ValueError('Unverified nested or non-simple reorder item')
        if product in expected or decimal(item['qty_ordered']) <= 0: raise ValueError('Ambiguous native reorder product')
        options = json.loads(item['product_options']) if isinstance(item['product_options'], str) else item['product_options']
        request = options.get('info_buyRequest', {})
        selected = request.get('options', {})
        if isinstance(selected, list) and not selected: selected = {}
        if not isinstance(selected, dict): raise ValueError('Native order custom options must be an object')
        expected[product] = {'name': item['name'], 'sku': item['sku'], 'qty': decimal(item['qty_ordered']),
                             'options': {str(k): str(v) for k, v in selected.items()}}
    return expected


def reorder_checks(before, after, reference, event, page, *, site_origin):
    expected = validate_reorder_reference(reference)
    if before['user_id'] != reference['account']['entity_id'] or after['user_id'] != before['user_id'] or after['cart_id'] != before['cart_id']:
        raise ValueError('Reorder cart/account baseline changed')
    old = {r['item_id']: r for r in before['saved_items']}
    new = {r['item_id']: r for r in after['saved_items']}
    if len(old) != len(before['saved_items']) or len(new) != len(after['saved_items']): raise ValueError('Duplicate saved cart item')
    if any(r['product_id'] in expected for r in before['items']):
        raise ValueError('This native reorder control requires original ordered products absent from the cart')
    added = [r for r in after['items'] if r['item_id'] not in old]
    actual = {}
    for row in added:
        if row['product_id'] in actual: raise ValueError('Duplicate newly reordered product')
        actual[row['product_id']] = {'name': row['name'], 'sku': row['sku'], 'qty': decimal(row['qty']), 'options': option_map(after, row['item_id'])}
    old_options = [r for r in after['item_options'] if r['item_id'] in old]
    origin = urlsplit(site_origin); end = urlsplit(page.get('url', ''))
    target = reference['orders'][0]['entity_id']
    events = event.get('posts', []) if isinstance(event, dict) else []
    trusted = event.get('trusted_activations', []) if isinstance(event, dict) else []
    matched = any(r.get('method') == 'POST' and r.get('path', '').rstrip('/') == '/sales/order/reorder/order_id/'+str(target) for r in events)
    activated = any(r.get('trusted') is True and r.get('path', '').rstrip('/') == '/sales/order/reorder/order_id/'+str(target) for r in trusted)
    return {'completed_owned_order_used': matched and activated,
            'complete_native_products_quantities_options_saved': actual == expected,
            'original_cart_items_all_columns_unchanged': all(new.get(k) == v for k, v in old.items()),
            'original_cart_options_all_columns_unchanged': old_options == before['item_options'],
            'coupon_unchanged': after['coupon_code'] == before['coupon_code'],
            'terminal_page_valid': (end.scheme, end.netloc) == (origin.scheme, origin.netloc) and not page.get('login_page') and not page.get('error_page') and page.get('http_status') != 404}


def price_filter_checks(reference, public, prices, *, site_origin, lower='0', upper='100'):
    if reference['category']['id'] != 11 or reference['category']['active'] is not True:
        raise ValueError('Exact native Electronics category required')
    if not reference.get('active_filters') or not reference.get('source_hashes'):
        raise ValueError('Native applied price filter and source hashes required')
    if reference['scope'] != '/electronics.html?price='+lower+'-'+upper: raise ValueError('Native requested price range changed')
    url = urlsplit(public.get('url', '')); origin = urlsplit(site_origin)
    expected = reference['products']; observed = public.get('products', [])
    lo, hi = decimal(lower), decimal(upper)
    # Magento's native upper price interval is exclusive. Do not widen it to the
    # published coarse 0-10000 facet or invent an inclusive UI range.
    native_bound = all(lo <= decimal(r['price']) < hi for r in expected)
    amounts = {str(r['product_id']): [decimal(a['amount']) for a in r['amounts'] if a['type'] == 'finalPrice'] for r in prices}
    visible = all(amounts.get(str(r['id'])) == [decimal(r['price'])] for r in expected)
    from .shopping_collection_reference import total_from_toolbar, normalized_label
    try: total_matches = total_from_toolbar(public.get('amount', [])) == reference['total']
    except ValueError: total_matches = False
    def public_id(value):
        if not isinstance(value,str) or not value.isdecimal() or int(value)<=0: raise ValueError('Malformed public product identity')
        return int(value)
    return {'exact_local_electronics_price_range': (url.scheme, url.netloc) == (origin.scheme, origin.netloc) and url.path == '/electronics.html' and parse_qs(url.query) == {'price': [lower+'-'+upper]} and not url.fragment,
            'complete_native_first_page_identity': [(public_id(r['id']), r['name']) for r in observed] == [(r['id'], r['name']) for r in expected],
            'native_total_matches_public_toolbar': total_matches,
            'native_interval_and_visible_final_prices': bool(expected) and native_bound and visible,
            'active_native_range_is_public': public.get('active_filters') == [{'label':r['label'],'value':normalized_label(r['value'])}for r in reference['active_filters']]}


COMPARE_READ = r'''() => {
 const visible=e=>!!e&&e.getClientRects().length>0&&![...function*(n){while(n){yield n;n=n.parentElement}}(e)].some(n=>{const s=getComputedStyle(n);return s.display==='none'||s.visibility==='hidden'||n.hidden||n.getAttribute('aria-hidden')==='true'});
 const table=document.querySelector('#product-comparison');
 const cells=table?[...table.querySelectorAll('td.cell.product.info')].filter(visible):[];
 const safe=e=>{try{const u=new URL(e.href,location.href);return u.origin+u.pathname}catch{return null}};
 const products=cells.filter(e=>e.querySelector('[data-product-id]')).map(e=>{
   const box=e.querySelector('[data-product-id]'), name=e.querySelector('.product-item-name a');
   return {id:Number(box.dataset.productId),name:name?.innerText.trim()||null,path:name?safe(name):null,
           prices:[...box.querySelectorAll('[data-price-type][data-price-amount]')].filter(visible).map(p=>({type:p.dataset.priceType,amount:p.dataset.priceAmount})),visible:visible(e)};
 });
 return {url:location.href,table_visible:visible(table),products,
   rows:table?[...table.querySelectorAll('tr')].filter(visible).map(r=>({attribute_row:!!r.querySelector('td.cell.product.attribute'),heading:r.querySelector('th')?.innerText.trim()||null,values:[...r.querySelectorAll('td')].filter(visible).map(e=>e.innerText.trim())})):[],
   authenticated_marker:[...document.querySelectorAll('a')].some(a=>visible(a)&&new URL(a.href,location.href).pathname.includes('/customer/account/logout/'))};
}'''


def compare_checks(reference, state, persisted, *, site_origin):
    ids = [positive_int(r['entity_id']) for r in reference]
    if len(ids) != 2 or len(set(ids)) != 2: raise ValueError('Two distinct exact comparison products required')
    if not isinstance(state.get('products'), list) or not isinstance(state.get('rows'), list): raise ValueError('Missing native comparison table')
    products = state['products']; found = {r['id']: r for r in products}
    if len(found) != len(products): raise ValueError('Duplicate native comparison product')
    for row in products:
        positive_int(row['id'])
        if type(row.get('visible')) is not bool: raise ValueError('Malformed comparison visibility')
    origin = urlsplit(site_origin); page = urlsplit(state.get('url', ''))
    names = all(found.get(r['entity_id'], {}).get('name') == r['name'] and found.get(r['entity_id'], {}).get('visible') is True and urlsplit(found.get(r['entity_id'], {}).get('path', '')).path == '/'+r['url_key']+'.html' and (urlsplit(found[r['entity_id']]['path']).scheme,urlsplit(found[r['entity_id']]['path']).netloc)==(origin.scheme,origin.netloc) for r in reference if r['entity_id'] in found) and set(found) == set(ids)
    identity = persisted.get('products') if isinstance(persisted, dict) else None
    return {'native_guest_comparison_page': (page.scheme,page.netloc)==(origin.scheme,origin.netloc) and page.path.rstrip('/') in ('/catalog/product_compare','/catalog/product_compare/index') and not page.query and not page.fragment,
            'guest_not_authenticated': state.get('authenticated_marker') is False and persisted.get('customer_id') is None and type(persisted.get('visitor_id')) is int and persisted['visitor_id'] > 0,
            'complete_correct_visible_comparison_products': state.get('table_visible') is True and names,
            'native_guest_saved_collection_exact': isinstance(identity,list) and sorted(identity)==sorted(ids),
            'comparison_attributes_rendered': any(r.get('attribute_row') is True and r.get('heading') and len(r.get('values',[]))==2 and any(v.strip() for v in r['values']) for r in state['rows'])}


def catalogue_reference(site, group_id, *, terms=()):
    if type(group_id) is not int or group_id < 0: raise ValueError('Exact native customer group required')
    php = Path(__file__).with_name('shopping_seven_catalogue.php')
    import time
    started=time.monotonic();process=None;failure=None
    try:
        process=site.command(['php','-d','memory_limit=1024M','-r',php.read_text().removeprefix('<?php'),json.dumps({'host':urlsplit(site.url).netloc,'group_id':group_id,'terms':list(terms)})],capture_output=True,text=True,timeout=900)
        raw=process.stdout
    except Exception as error:
        process=error;failure=type(error).__name__
        raise
    finally:
        if hasattr(site,'logs'):
            stderr=getattr(process,'stderr','')or''
            if isinstance(stderr,bytes):stderr=stderr.decode(errors='replace')
            progress=[]
            for line in stderr.splitlines():
                if line.startswith('LAB_NATIVE_CATALOG_PROGRESS '):
                    try:
                        row=json.loads(line.split(' ',1)[1])
                        if set(row)=={'after_id','last_id','rows'}and all(type(row[k])is int for k in row):progress.append(row)
                    except(ValueError,TypeError,AttributeError):pass
            from .io_utils import atomic_write_json
            atomic_write_json(Path(site.logs)/'native-catalogue-reader-diagnostic.json',{'stage':'complete_native_catalogue_reference','seconds':time.monotonic()-started,'returncode':getattr(process,'returncode',None),'exception_type':failure,'native_keyset_progress':progress,'stderr_bytes':len(stderr.encode()),'stderr_sha256':hashlib.sha256(stderr.encode()).hexdigest(),'raw_sql_commands_stderr_credentials_not_saved':True})
    result = json.loads(raw)
    if result.get('complete') is not True or result.get('observed') != result.get('total') or result.get('distinct_ids') != result.get('total') or not result.get('source_hashes'):
        raise ValueError('Native catalog scope did not completely cover its exact universe')
    if result.get('group_id') != group_id or result.get('terms') != list(terms): raise ValueError('Native catalogue scope changed')
    for key in ('total','observed','distinct_ids','on_sale_count','salable_on_sale_count'):
        if type(result.get(key)) is not int or result[key] < 0: raise ValueError('Malformed complete native catalog count')
    if not 0 <= result['salable_on_sale_count'] <= result['on_sale_count'] <= result['total']:
        raise ValueError('Native sale counts are inconsistent')
    pages=result.get('keyset_pages');previous=0;covered=0
    if not isinstance(pages,list) or not pages:raise ValueError('Complete native keyset evidence missing')
    for index,page in enumerate(pages):
        if not isinstance(page,dict) or set(page)!={'after_id','last_id','rows'} or any(type(page[k])is not int for k in page):raise ValueError('Malformed native keyset evidence')
        if page['after_id']!=previous or not 0<=page['rows']<=256 or (page['rows']>0 and page['last_id']<=previous) or (page['rows']==0 and page['last_id']!=previous):raise ValueError('Native keyset coverage has a gap or repeated boundary')
        if index<len(pages)-1 and page['rows']!=256:raise ValueError('Prematurely partial native keyset batch')
        previous=page['last_id'];covered+=page['rows']
    if covered!=result['total'] or pages[-1]['rows']==256:raise ValueError('Native keyset end-of-universe not proven')
    matches=result.get('matches')
    if not isinstance(matches,list) or len({r['id']for r in matches})!=len(matches):raise ValueError('Native candidate collection incomplete or repeated')
    for row in matches:
        positive_int(row['id'])
        if type(row.get('on_sale')) is not bool or type(row.get('salable')) is not bool or not isinstance(row.get('name'),str):raise ValueError('Malformed native candidate evidence')
        regular,final=decimal(row['regular_price']),decimal(row['final_price'])
        if min(regular,final)<0 or row['on_sale']!=(final<regular) or not all(t.casefold()in row['name'].casefold()for t in terms):raise ValueError('Native candidate sale predicate/terms differ from its final and regular prices')
    return result
