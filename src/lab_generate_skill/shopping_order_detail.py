"""Private native order references and public rendered order-detail checks."""
from collections import Counter
from .site_database import select_rows

FEEDBACK = {
    'order_details_visible': 'The requested order has a visible item-details table.',
    'order_items_match': 'The displayed items belong to the requested order.',
    'order_status_visible': 'The requested order status is actually displayed.',
}


def validate(spec):
    if (type(spec.get('order_id')) is not int or spec['order_id'] <= 0
        or type(spec.get('customer_id')) is not int or spec['customer_id'] <= 0
        or not isinstance(spec.get('increment_id'), str) or not spec['increment_id'].isdigit()
        or not isinstance(spec.get('status_label'), str) or not spec['status_label']
        or not isinstance(spec.get('skus'), list) or not spec['skus']
        or any(not isinstance(s,str) or not s for s in spec['skus'])):
        raise ValueError('Invalid native order-detail reference')


def verify_reference(site, spec):
    validate(spec)
    rows=select_rows(site, 'SELECT o.entity_id,o.customer_id,o.increment_id,s.label AS status_label '
        'FROM sales_order o JOIN sales_order_status s ON s.status=o.status WHERE o.entity_id='+str(spec['order_id']))
    if len(rows)!=1 or any(rows[0][key]!=spec[key] for key in ('customer_id','increment_id','status_label')):
        raise ValueError('Requested order identity/status changed')
    items=select_rows(site,'SELECT sku FROM sales_order_item WHERE order_id='+str(spec['order_id'])+' AND parent_item_id IS NULL ORDER BY item_id')
    if Counter(r['sku'] for r in items)!=Counter(spec['skus']):
        raise ValueError('Requested order items changed')


def read_order_detail(page):
    return page.evaluate('''() => {
      const visible=e=>!!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
      const root=document.querySelector('main')||document.body;
      return {statuses:[...root.querySelectorAll('.order-status')].filter(visible).map(e=>e.innerText.trim()),
        tables:[...root.querySelectorAll('table')].filter(visible).map(t=>({
          headers:[...t.querySelectorAll('thead th')].map(e=>e.innerText.trim()),
          skus:[...t.querySelectorAll('tbody .col.sku')].filter(visible).map(e=>e.innerText.trim())}))};
    }''')


def detail_checks(spec, state):
    validate(spec)
    if (not isinstance(state,dict) or not isinstance(state.get('tables'),list)
            or not isinstance(state.get('statuses'),list)):
        raise ValueError('Missing order-detail capture')
    tables=[]
    for row in state['tables']:
        if not isinstance(row,dict) or not isinstance(row.get('headers'),list) or not isinstance(row.get('skus'),list):
            raise ValueError('Malformed order-detail table')
        if row['headers']==['Product Name','SKU','Price','Qty','Subtotal']:
            tables.append(row)
    return {'order_details_visible':len(tables)==1,
            'order_items_match':len(tables)==1 and Counter(tables[0]['skus'])==Counter(spec['skus']),
            'order_status_visible':state['statuses']==[spec['status_label']]}
