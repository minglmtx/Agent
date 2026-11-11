"""Persisted mock-order completion; no hidden order IDs or actions enter prompts."""
from decimal import Decimal
from .shopping_checkout import checkout_state
from .site_database import select_rows
from .site_navigation_rules import valid_initial_page
from .site_query_rules import reference_fingerprint

VERSION='shopping-order-v1'
ADMISSION_VERSION='shopping-order-admission-v1'


def order_state(site,username,*,expected_cart_id=None):
    state=checkout_state(site,username,expected_cart_id=expected_cart_id)
    uid=int(state['cart']['user_id'])
    state['orders']=select_rows(site,f'SELECT entity_id,customer_id,quote_id,increment_id,status,subtotal,grand_total,shipping_amount,tax_amount,discount_amount FROM sales_order WHERE customer_id={uid} ORDER BY entity_id')
    state['order_items']=select_rows(site,f'SELECT i.order_id,i.product_id,i.parent_item_id,i.sku,i.name,i.qty_ordered,i.price FROM sales_order_item i JOIN sales_order o ON o.entity_id=i.order_id WHERE o.customer_id={uid} ORDER BY i.item_id')
    state['payments']=select_rows(site,f'SELECT p.parent_id,p.method,p.amount_ordered FROM sales_order_payment p JOIN sales_order o ON o.entity_id=p.parent_id WHERE o.customer_id={uid} ORDER BY p.entity_id')
    return state


def validate_initial(c,state):
    spec=c['order']; cart=state['cart']
    if cart['user_id']!=spec['customer_id'] or cart['cart_id']!=spec['cart_id'] or not cart['items']:
        raise ValueError('Expected nonempty source cart missing')
    if any(r['parent_item_id'] is not None for r in cart['items']):raise ValueError('Nested source order items require separate accounting')
    if spec.get('required_product_id') not in {r['product_id'] for r in cart['items']}:raise ValueError('Requested named product absent from initial cart')
    if any(r['quote_id']==cart['cart_id'] for r in state['orders']):raise ValueError('Source cart has already produced an order')


def evaluate_order(c,page,initial,final,*,site_origin,runtime_error=None):
    def unknown(reason):return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':reason}
    if runtime_error:return unknown('Runtime error prevents reliable order evaluation')
    if not isinstance(page,dict) or type(page.get('http_status')) is not int or page['http_status']<200 or page['http_status']>=500:
        return unknown('Missing page or transport/server failure')
    if not initial or not final:return unknown('Missing persisted order state')
    cart=initial['cart']; old={r['entity_id'] for r in initial['orders']}
    created=[r for r in final['orders'] if r['entity_id'] not in old]
    checks={'page_valid':valid_initial_page(page,site_origin=site_origin),
            'order_account_unchanged':initial['account']==final['account'] and initial['saved_addresses']==final['saved_addresses'],
            'previous_orders_unchanged':[r for r in final['orders'] if r['entity_id'] in old]==initial['orders']
                and [r for r in final['order_items'] if r['order_id'] in old]==initial['order_items']
                and [r for r in final['payments'] if r['parent_id'] in old]==initial['payments'],
            'one_new_order':len(created)==1}
    if len(created)==1:
        order=created[0]; oid=order['entity_id']
        items=[r for r in final['order_items'] if r['order_id']==oid]
        payments=[r for r in final['payments'] if r['parent_id']==oid]
        expected=sorted((r['product_id'],r['sku'],Decimal(str(r['qty'])),Decimal(str(r['price']))) for r in cart['items'])
        actual=sorted((r['product_id'],r['sku'],Decimal(str(r['qty_ordered'])),Decimal(str(r['price']))) for r in items if r['parent_item_id'] is None)
        subtotal=sum(Decimal(str(r['qty']))*Decimal(str(r['price'])) for r in cart['items'])
        total=Decimal(str(order['grand_total']))
        checks.update(order_source_identity=order['customer_id']==cart['user_id'] and order['quote_id']==cart['cart_id'],
            ordered_products_and_quantities=expected==actual and len(items)==len(actual),
            order_amounts_consistent=Decimal(str(order['subtotal']))==subtotal
                and Decimal(str(order['discount_amount']))==0
                and total==subtotal+Decimal(str(order['shipping_amount']))+Decimal(str(order['tax_amount']))
                and total>0,
            offline_order_payment=len(payments)==1 and payments[0]['method']=='checkmo' and Decimal(str(payments[0]['amount_ordered']))==total)
    success=all(checks.values())
    return {'version':VERSION,'status':'success' if success else 'failure','reward':float(success),'checks':checks,'reason':None}


def order_feedback(judgment):
    meanings={'page_valid':'The terminal page is valid on the task website.',
        'order_account_unchanged':'The customer account and saved profile addresses remain unchanged.',
        'previous_orders_unchanged':'Previous orders have not been altered.',
        'one_new_order':'Exactly one new order has been saved.',
        'order_source_identity':'The order belongs to the current customer and original cart.',
        'ordered_products_and_quantities':'The saved order contains the requested cart products and quantities.',
        'order_amounts_consistent':'The saved order amounts agree with the original cart and checkout charges.',
        'offline_order_payment':'The order records the available offline payment method and matching amount.'}
    return {'status':judgment['status'],'reward':judgment['reward'],'reason':judgment.get('reason'),
            'checks':[{'name':k,'passed':v,'condition':meanings[k]} for k,v in judgment['checks'].items()],
            'action_sequence_provided':False,'reference_values_provided':False}


def contract_fingerprint(c):
    return reference_fingerprint({k:c.get(k) for k in ('task_id','source_task_id','domain','goal','start_path','order','heldout_quarantine','goal_revision','start_revision')})


def require_order_admission(c,proof):
    if c.get('heldout_quarantine'):raise ValueError('Heldout task is quarantined')
    if proof.get('admission_version')!=ADMISSION_VERSION or proof.get('contract_fingerprint')!=contract_fingerprint(c):raise ValueError('Stale order admission')
    cycles=proof.get('cycles',[])
    expected={'no_op':'failure','unsubmitted':'failure','positive':'success','wrong_cart':'failure','404':'failure','login':'failure'}
    if not proof.get('passed') or len(cycles)!=2:raise ValueError('Two independent order control cycles required')
    for cycle in cycles:
        if not cycle.get('passed') or cycle.get('checks')!=expected or not cycle.get('protected_nonorder_records_unchanged'):
            raise ValueError('Order controls incomplete')
        if cycle['initial_state']!=cycle['wrong_initial_state']:raise ValueError('Wrong-cart control started with a different baseline')
        validate_initial(c,cycle['initial_state'])
    if cycles[0]['initial_state']!=cycles[1]['initial_state'] or cycles[0]['initial_fingerprint']!=cycles[1]['initial_fingerprint']:
        raise ValueError('Order reset baseline changed')
