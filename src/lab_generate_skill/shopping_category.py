"""Native category identity, independent of the URL or dynamic account sidebar."""
from urllib.parse import parse_qs, urlsplit
from .site_database import select_rows


def category_metadata(site, ids):
    if not ids or any(type(i) is not int or i <= 2 for i in ids):
        raise ValueError('Explicit category IDs required')
    values = ','.join(map(str, sorted(set(ids))))
    return select_rows(site, """SELECT e.entity_id,e.parent_id,n.value AS name,u.value AS url_key
      FROM catalog_category_entity e
      JOIN catalog_category_entity_varchar n ON n.entity_id=e.entity_id AND n.store_id=0
        AND n.attribute_id=(SELECT attribute_id FROM eav_attribute WHERE entity_type_id=3 AND attribute_code='name')
      LEFT JOIN catalog_category_entity_varchar u ON u.entity_id=e.entity_id AND u.store_id=0
        AND u.attribute_id=(SELECT attribute_id FROM eav_attribute WHERE entity_type_id=3 AND attribute_code='url_key')
      WHERE e.entity_id IN (""" + values + ') ORDER BY e.entity_id')


def category_products(site, ident):
    if type(ident) is not int or ident <= 2: raise ValueError('Invalid category ID')
    return select_rows(site, 'SELECT category_id,product_id,visibility FROM catalog_category_product_index_store1 '
                       f'WHERE category_id={ident} ORDER BY category_id,product_id')


def verify_category_reference(site, spec):
    metadata = sorted(spec['metadata'], key=lambda r: r['entity_id'])
    if category_metadata(site, [r['entity_id'] for r in metadata]) != metadata:
        raise ValueError('Pinned category hierarchy changed')
    if category_products(site, spec['category_id']) != spec['product_index']:
        raise ValueError('Pinned category product membership changed')


def stable_category_capture(state):
    """Only task-relevant native collection state; raw sidebar text stays on disk."""
    return {k: state[k] for k in ('url', 'title', 'heading', 'filters', 'products', 'empty_messages')} | {
        'classes': sorted(c for c in state['classes'].split()
                          if c.startswith(('categorypath-', 'category-')) or c == 'catalog-category-view')}


def read_category_page(page):
    return page.evaluate(r'''() => {
      const visible=e=>!!e && !!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
      const lists=[...document.querySelectorAll('.products.wrapper')].filter(visible);
      return {heading:document.querySelector('h1')?.innerText.trim() || '',
        classes:document.body.className,
        filters:[...document.querySelectorAll('.filter-current .item')].filter(visible).map(e=>({
          label:e.querySelector('.filter-label')?.innerText.trim() || '',
          value:e.querySelector('.filter-value')?.innerText.trim() || ''})),
        list_count:lists.length,
        products:lists.flatMap(list=>[...list.querySelectorAll('li.product-item')].filter(visible).map(e=>({
          id:e.querySelector('[data-product-id]')?.getAttribute('data-product-id') || '',
          name:e.querySelector('.product-item-link')?.innerText.trim() || ''})))
      };
    }''')


def category_checks(spec, state, url):
    if not isinstance(state, dict) or not {'heading','classes','filters','list_count','products'} <= state.keys():
        raise ValueError('Missing native category terminal capture')
    if not isinstance(state['classes'], str) or not isinstance(state['filters'], list) or not isinstance(state['products'], list):
        raise ValueError('Malformed native category terminal capture')
    parts = urlsplit(url); query = parse_qs(parts.query, keep_blank_values=True)
    params_valid = all(len(v) == 1 for v in query.values())
    native_filters = [r['value'] for r in state['filters'] if r['label'] == 'Category']
    alternatives = [r for r in spec['routes'] if r['path'].rstrip('/') == parts.path.rstrip('/')
                    and query.get('cat', []) == r['category_query']]
    classes = set(state['classes'].split())
    identity = any(state['heading'] == r['heading'] and native_filters == r['native_category_filters']
                   and r['category_class'] in classes for r in alternatives)
    allowed = {str(r['product_id']) for r in spec['product_index'] if r['visibility'] in (2, 4)}
    products = state['products']; ids = [r.get('id') for r in products]
    return {
        'category_parameters_unambiguous': params_valid,
        'category_native_identity': 'catalog-category-view' in classes and identity,
        'category_product_list_visible': state['list_count'] == 1 and bool(products),
        'category_product_membership': bool(products) and len(ids) == len(set(ids))
            and all(r.get('id') in allowed and bool(r.get('name')) for r in products),
    }


FEEDBACK = {
    'category_parameters_unambiguous': 'The active category and list parameters are unambiguous.',
    'category_native_identity': 'The native category page or applied category filter identifies the requested section.',
    'category_product_list_visible': 'The requested product collection is displayed.',
    'category_product_membership': 'The displayed product records belong to the requested category.',
}
