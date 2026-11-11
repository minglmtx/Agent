"""Native collection scope and separate public-page evidence for Shopping.

The Magento reader executes native collection code on a worker-local snapshot.
No totals are inferred from a pagination bar or from sampled product pages.
"""
import html
import json
import re
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from .site_database import select_rows


def validate_scope(spec):
    path = spec.get('path', '')
    parts = urlsplit(path)
    if parts.netloc or parts.scheme or not parts.path.startswith('/') or parts.fragment:
        raise ValueError('Local collection path required')
    params = parse_qs(parts.query, keep_blank_values=True)
    if any(len(v) != 1 for v in params.values()):
        raise ValueError('Ambiguous collection parameters')
    if spec.get('kind') == 'category':
        if type(spec.get('category_id')) is not int or spec['category_id'] <= 2:
            raise ValueError('Explicit native category identity required')
        if set(params) - {'cat', 'price', 'product_list_order', 'product_list_dir'}:
            raise ValueError('Unsupported category scope parameters')
        if 'product_list_order' in params and params['product_list_order'][0] not in ('price','name','position'):
            raise ValueError('Unsupported native toolbar order')
        if 'product_list_dir' in params and params['product_list_dir'][0] not in ('asc','desc'):
            raise ValueError('Unsupported native toolbar direction')
        if 'cat' in params and not re.fullmatch(r'[1-9]\d*', params['cat'][0]):
            raise ValueError('Invalid native category filter')
        if 'price' in params and not re.fullmatch(r'\d+(?:\.\d+)?-\d+(?:\.\d+)?', params['price'][0]):
            raise ValueError('Invalid native price filter')
    elif spec.get('kind') == 'advanced':
        if parts.path != '/catalogsearch/advanced/result/' or set(params) - {
            'name', 'sku', 'description', 'short_description', 'price[from]', 'price[to]', 'price[currency]'
        }:
            raise ValueError('Unsupported advanced-search scope')
        if not any(params.get(k, [''])[0].strip() for k in ('name', 'sku', 'description', 'short_description')):
            raise ValueError('Explicit search criterion required')
    else:
        raise ValueError('Unsupported collection kind')
    return spec


def native_collection(site, spec, username):
    validate_scope(spec)
    account = select_rows(site, "SELECT entity_id,group_id FROM customer_entity WHERE email='"+username.replace("'", "''")+"'")
    if len(account) != 1:
        raise ValueError('Missing or ambiguous collection account')
    args = dict(spec, host=urlsplit(site.url).netloc, customer_group_id=int(account[0]['group_id']))
    code = Path(__file__).with_name('shopping_native_collection.php').read_text().removeprefix('<?php')
    # Same memory allowance as the native web PHP process. No HTTP or model call.
    result = site.command(['php', '-d', 'memory_limit=1024M', '-r', code, json.dumps(args)],
                          capture_output=True, text=True, timeout=60)
    data = json.loads(result.stdout)
    ids = [r['id'] for r in data['products']]
    if not ids or len(ids) != len(set(ids)) or data['page'] != 1 or data['total'] < len(ids) or len(ids)>data['limit']:
        raise ValueError('Missing or inconsistent native collection')
    if spec['kind'] == 'category' and (data['category']['id'] != spec['category_id'] or not data['category']['active']):
        raise ValueError('Wrong or inactive native category')
    clause = ','.join(map(str, ids))
    data['ratings'] = select_rows(site, 'SELECT entity_pk_value AS product_id,rating_summary,reviews_count '
        f'FROM review_entity_summary WHERE store_id=1 AND entity_type=1 AND entity_pk_value IN ({clause}) ORDER BY entity_pk_value')
    data['account_group'] = int(account[0]['group_id'])
    return data


def public_collection(page):
    return page.evaluate(r'''() => {
      const visible=e=>!!e && !!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
      const all=s=>[...document.querySelectorAll(s)].filter(visible);
      return {url:location.href,heading:document.querySelector('h1')?.innerText.trim()||'',
        classes:document.body.className,
        amount:all('.toolbar-amount').map(e=>e.innerText.trim()),
        facets:all('#narrow-by-list dt').map(e=>({name:e.innerText.trim(),items:
          [...(e.nextElementSibling?.querySelectorAll('a[href]')||[])].filter(visible).map(a=>({
            text:a.innerText.trim(),href:a.href,count:a.querySelector('.count')?.innerText.trim()||null}))})),
        active_filters:all('.filter-current .item').map(e=>({label:e.querySelector('.filter-label')?.innerText.trim()||'',value:e.querySelector('.filter-value')?.innerText.trim()||''})),
        current:all('.pages .item.current').map(e=>e.innerText.trim()),
        products:all('.products.wrapper li.product-item').map(e=>({
          id:e.querySelector('[data-product-id]')?.getAttribute('data-product-id')||'',
          name:e.querySelector('.product-item-link')?.innerText.trim()||'',
          rating:e.querySelector('.rating-result')?.getAttribute('title')||null}))};
    }''')


def total_from_toolbar(amounts):
    totals = []
    for value in amounts:
        match = re.fullmatch(r'Items\s+[\d,]+\s*-\s*[\d,]+\s+of\s+([\d,]+)', value.strip())
        if not match:
            match = re.fullmatch(r'([\d,]+)\s+Items?', value.strip())
        if not match:
            raise ValueError('Unrecognized native total display')
        totals.append(int(match[1].replace(',', '')))
    if not totals or len(set(totals)) != 1:
        raise ValueError('Missing or conflicting native totals')
    return totals[0]


def normalized_label(value):
    # Decode the native price renderer's span markup, preserving its text.
    from bs4 import BeautifulSoup
    return ' '.join(BeautifulSoup(html.unescape(value), 'html.parser').get_text(' ', strip=True).split())


def public_facet(public, name, parameter):
    groups = [r for r in public['facets'] if r['name'] == name]
    if len(groups) != 1 or not groups[0]['items']:
        raise ValueError('Missing or ambiguous visible facet')
    result = []
    for item in groups[0]['items']:
        label = ' '.join(item['text'].split())
        count = item['count']
        if count:
            label = label.removesuffix(' '.join(count.split())).strip()
        values = parse_qs(urlsplit(item['href']).query).get(parameter, [])
        if len(values) != 1 or not label:
            raise ValueError('Invalid visible facet option')
        result.append({'value':values[0], 'label':label})
    if len({r['value'] for r in result}) != len(result):
        raise ValueError('Duplicate facet values')
    return result


def compare_native_public(native, public, spec):
    parts = urlsplit(public['url']); expected = urlsplit(spec['path'])
    checks = {'scope_url': parts.path == expected.path and parse_qs(parts.query, keep_blank_values=True) == parse_qs(expected.query, keep_blank_values=True),
              'total': total_from_toolbar(public['amount']) == native['total'],
              'first_page_members_and_order': [(r['id'], r['name']) for r in native['products']] == [(int(r['id']), r['name']) for r in public['products']]}
    if spec['kind'] == 'category':
        checks['category_identity'] = public['heading'] == native['category']['name'] and 'catalog-category-view' in public['classes'].split()
        for facet in native['facets']:
            if facet['parameter'] not in ('cat', 'price') or not facet['items']:
                continue
            try:
                rendered = [(r['value'],r['label']) for r in public_facet(public,facet['name'],facet['parameter'])]
            except ValueError:
                rendered = []
            expected_items = [(str(i['value']), normalized_label(i['label'])) for i in facet['items']]
            checks['facet_'+facet['parameter']] = rendered == expected_items
    else:
        # Native layout h1 differs from its document title in this snapshot.
        checks['search_identity'] = public['heading'] == 'Catalog Advanced Search' and 'catalogsearch-advanced-result' in public['classes'].split()
    if 'ratings' in native:
        ratings={r['product_id']:r for r in native['ratings']}
        expected_ratings=[(p['id'],str(ratings[p['id']]['rating_summary'])+'%' if p['id'] in ratings and int(ratings[p['id']]['reviews_count'])>0 and int(ratings[p['id']]['rating_summary'])>0 else None) for p in native['products']]
        checks['ratings'] = expected_ratings == [(int(p['id']),p['rating']) for p in public['products']]
    return checks
