"""Native product identity for detail-page navigation, including valid alternatives."""
from .site_database import select_rows


def product_reference(site, ids):
    if not ids or any(type(i) is not int or i <= 0 for i in ids): raise ValueError('Explicit product IDs required')
    values = ','.join(map(str, sorted(set(ids))))
    return select_rows(site, f"""SELECT p.entity_id,p.sku,n.value AS name,u.value AS url_key
      FROM catalog_product_entity p
      JOIN catalog_product_entity_varchar n ON n.entity_id=p.entity_id AND n.store_id=0
        AND n.attribute_id=(SELECT attribute_id FROM eav_attribute WHERE entity_type_id=4 AND attribute_code='name')
      JOIN catalog_product_entity_varchar u ON u.entity_id=p.entity_id AND u.store_id=0
        AND u.attribute_id=(SELECT attribute_id FROM eav_attribute WHERE entity_type_id=4 AND attribute_code='url_key')
      WHERE p.entity_id IN ({values}) ORDER BY p.entity_id""")


def verify_details_reference(site, spec):
    expected = sorted(spec['products'], key=lambda r: r['entity_id'])
    if product_reference(site, [r['entity_id'] for r in expected]) != expected:
        raise ValueError('Product identity reference changed')
    if spec.get('cart_reference'):
        from .site_cart_rules import cart_state
        from .site_auth import credentials
        if cart_state(site, credentials(site.root, 'shopping')['username']) != spec['cart_reference']:
            raise ValueError('Source cart differs from the pinned task objects')


def read_product_details(page):
    from .shopping_cart_details import read_cart_details
    result = page.evaluate(r'''() => {
      const visible=e=>!!e && !!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
      const main=document.querySelector('.product-info-main');
      return {product_id:document.querySelector('#product_addtocart_form input[name="product"]')?.value
          || main?.querySelector('.price-box[data-product-id]')?.getAttribute('data-product-id') || null,
        name:document.querySelector('h1.page-title')?.innerText.trim() || '',
        sku:main?.querySelector('.product.attribute.sku .value')?.innerText.trim() || '',
        summary_visible:visible(main)};
    }''')
    result['cart_details'] = read_cart_details(page)
    return result


def details_checks(spec, state):
    if not isinstance(state, dict) or not {'product_id','name','sku','summary_visible'} <= state.keys():
        raise ValueError('Missing native product detail capture')
    products = spec['products']
    if not products: raise ValueError('Product alternatives missing')
    matching = [r for r in products if str(r['entity_id']) == state['product_id']]
    return {'detail_product_identity': len(matching) == 1 and matching[0]['name'] == state['name'] and matching[0]['sku'] == state['sku'],
            'product_summary_displayed': state['summary_visible'] is True}


FEEDBACK = {'detail_product_identity': 'The native detail page identifies a product allowed by the task.',
            'product_summary_displayed': 'The native product information section is displayed.'}
