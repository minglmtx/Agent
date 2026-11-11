"""Terminal persisted-cart conditions; no action sequence is exposed to the actor."""
from decimal import Decimal
from .site_database import select_rows
from .site_navigation_rules import valid_initial_page
from .site_query_rules import reference_fingerprint

VERSION='site-cart-v1'
ADMISSION_VERSION='site-cart-admission-v1'


def cart_state(site,username):
    if site.domain!='shopping':raise ValueError('Cart evaluator requires shopping site')
    accounts=select_rows(site,"SELECT entity_id FROM customer_entity WHERE email='"+username.replace("'","''")+"'")
    if len(accounts)!=1:raise ValueError('Missing or ambiguous cart account')
    uid=int(accounts[0]['entity_id']);quotes=select_rows(site,f'SELECT entity_id,coupon_code FROM quote WHERE customer_id={uid} AND is_active=1')
    if len(quotes)!=1:raise ValueError('Expected one active customer cart')
    qid=int(quotes[0]['entity_id']);items=select_rows(site,f'SELECT item_id,product_id,parent_item_id,sku,name,qty,price FROM quote_item WHERE quote_id={qid} ORDER BY item_id')
    if any(x['parent_item_id'] is not None for x in items):raise ValueError('Nested cart items require a separately validated rule')
    return {'user_id':uid,'cart_id':qid,'coupon_code':quotes[0]['coupon_code'],'items':items}


def task_cart_state(site,username,c):
    """Extend only the operations that need option/collection evidence."""
    state=cart_state(site,username)
    if c['cart']['operation']not in ('move_to_wishlist','change_quantities','change_options','edit_items'):return state
    state['item_options']=select_rows(site,'SELECT o.item_id,o.code,o.value FROM quote_item_option o JOIN quote_item i ON i.item_id=o.item_id '
        f'WHERE i.quote_id={state["cart_id"]} ORDER BY o.item_id,o.code')
    if c['cart']['operation']=='change_quantities':return state
    if c['cart']['operation']=='edit_items':
        from .cart_options import catalog
        state['option_catalogs']={str(pid):catalog(site,pid)for pid in c['cart']['initial_product_ids']}
        return state
    if c['cart']['operation']=='change_options':
        from .cart_options import catalog
        state['option_catalog']=catalog(site,c['cart']['product_id'])
        return state
    uid=state['user_id'];ident=int(c['cart']['product_id'])
    wishes=select_rows(site,f'SELECT wishlist_id FROM wishlist WHERE customer_id={uid} ORDER BY wishlist_id')
    if len(wishes)!=1:raise ValueError('Expected one customer wishlist for cart transfer')
    wid=int(wishes[0]['wishlist_id'])
    state['wishlist']={'wishlist_id':wid,'items':select_rows(site,
        f'SELECT wishlist_item_id,product_id,qty,description FROM wishlist_item WHERE wishlist_id={wid} ORDER BY wishlist_item_id')}
    state['compare']=select_rows(site,f'SELECT product_id FROM catalog_compare_item WHERE customer_id={uid} ORDER BY product_id')
    state['transfer_product']=select_rows(site,'SELECT p.entity_id,p.type_id,(SELECT COUNT(*) FROM catalog_product_option o '
        f'WHERE o.product_id=p.entity_id) AS custom_option_count FROM catalog_product_entity p WHERE p.entity_id={ident}')
    return state


def contract_fingerprint(c):
    return reference_fingerprint({k:c.get(k) for k in ('task_id','source_task_id','domain','goal','start_path','cart','heldout_quarantine','start_revision')})


def control_signature(c):
    """Only identical initialization, state predicates and negative controls share probes."""
    return reference_fingerprint({k:c.get(k)for k in ('domain','start_path','cart','wrong_product_control','start_revision')})


def validate_initial(c,state):
    spec=c['cart']
    if state.get('user_id')!=spec['customer_id'] or not state.get('items'):raise ValueError('Cart initial condition absent')
    if spec['operation'] in ('remove_product','move_to_wishlist'):
        rows=[x for x in state['items'] if x['product_id']==spec['product_id']]
        if len(rows)!=1 or rows[0]['name']!=spec['product_name']:raise ValueError('Cart target missing or ambiguous')
        if spec['operation']=='move_to_wishlist':
            expected=[{'entity_id':spec['product_id'],'type_id':'simple','custom_option_count':0}]
            if state.get('transfer_product')!=expected:raise ValueError('Transfer adapter requires a simple product without custom options')
            if not isinstance(state.get('wishlist'),dict) or not isinstance(state.get('item_options'),list):raise ValueError('Missing transfer baseline')
            if any(x['product_id']==spec['product_id'] for x in state['wishlist']['items']):raise ValueError('Preexisting wishlist target needs separate merge controls')
    elif spec['operation']=='edit_items':
        from .cart_edit import validate_initial as validate_edits
        validate_edits(state,spec)
    elif spec['operation']=='change_quantities':
        from .cart_quantity import validate_initial as validate_quantities
        validate_quantities(state)
    elif spec['operation']=='change_options':
        from .cart_options import validate_initial as validate_options
        validate_options(state,spec)
    elif spec['operation']=='add_products':
        products=spec.get('products',[])
        if not products or len({x['product_id'] for x in products})!=len(products):raise ValueError('Explicit distinct cart products required')
        for product in products:
            if Decimal(str(product['quantity']))<=0:raise ValueError('Positive requested quantity required')
            rows=[x for x in state['items'] if x['product_id']==product['product_id']]
            if len(rows)>1 or (rows and rows[0]['name']!=product['product_name']):raise ValueError('Ambiguous existing cart product')
    elif spec['operation']!='clear':raise ValueError('Unsupported cart operation')
    if spec.get('source_surface'):
        from .shopping_recent_cart import validate as validate_recent_source
        validate_recent_source(spec)


def evaluate_cart(c,page,initial,final,*,site_origin,runtime_error=None):
    def unknown(reason):return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':reason}
    if runtime_error:return unknown('Environment or inference error')
    if not initial or not final or initial.get('user_id')!=final.get('user_id') or initial.get('cart_id')!=final.get('cart_id'):return unknown('Missing or changed cart/account reference')
    if not isinstance(page,dict) or type(page.get('http_status')) is not int or page['http_status']<200 or page['http_status']>=500:return unknown('Missing terminal page or transport/server failure')
    spec=c['cart'];before=initial['items'];after=final['items']
    checks={'page_valid':valid_initial_page(page,site_origin=site_origin),'coupon_unchanged':initial.get('coupon_code')==final.get('coupon_code')}
    if spec['operation']=='remove_product':
        ident=spec['product_id']
        checks['requested_item_removed']=all(x['product_id']!=ident for x in after)
        checks['unrelated_items_unchanged']=[x for x in before if x['product_id']!=ident]==[x for x in after if x['product_id']!=ident]
    elif spec['operation']=='move_to_wishlist':
        ident=spec['product_id'];original=[x for x in before if x['product_id']==ident]
        if len(original)!=1:return unknown('Missing unique initial transfer item')
        if (not isinstance(initial.get('wishlist'),dict) or not isinstance(final.get('wishlist'),dict)
                or initial['wishlist'].get('wishlist_id')!=final['wishlist'].get('wishlist_id')
                or not isinstance(final.get('item_options'),list)):
            return unknown('Missing or changed wishlist/option evidence')
        saved=[x for x in final['wishlist']['items'] if x['product_id']==ident]
        checks.update(requested_item_removed=all(x['product_id']!=ident for x in after),
            requested_item_saved_to_wishlist=len(saved)==1 and Decimal(str(saved[0]['qty']))==Decimal(str(original[0]['qty'])),
            unrelated_items_unchanged=[x for x in before if x['product_id']!=ident]==[x for x in after if x['product_id']!=ident],
            unrelated_options_unchanged=[x for x in initial['item_options'] if x['item_id']!=original[0]['item_id']]==[x for x in final['item_options'] if x['item_id']!=original[0]['item_id']],
            other_wishlist_items_unchanged=initial['wishlist']['items']==[x for x in final['wishlist']['items'] if x['product_id']!=ident],
            other_collections_unchanged=initial.get('compare')==final.get('compare'),
            transfer_product_unchanged=initial.get('transfer_product')==final.get('transfer_product'))
    elif spec['operation']=='edit_items':
        from .cart_edit import checks as edit_checks
        try:checks.update(edit_checks(initial,final,spec))
        except (ValueError,TypeError,KeyError)as exc:return unknown('Cart edit state unavailable: '+str(exc))
    elif spec['operation']=='change_quantities':
        from .cart_quantity import checks as quantity_checks
        try:checks.update(quantity_checks(initial,final))
        except (ValueError,TypeError,KeyError)as exc:return unknown('Quantity state unavailable: '+str(exc))
    elif spec['operation']=='change_options':
        from .cart_options import checks as option_checks
        try:checks.update(option_checks(initial,final,spec))
        except (ValueError,TypeError,KeyError)as exc:return unknown('Option state unavailable: '+str(exc))
    elif spec['operation']=='add_products':
        products=spec['products'];ids={x['product_id'] for x in products}
        correct=True
        for product in products:
            prior=[x for x in before if x['product_id']==product['product_id']]
            saved=[x for x in after if x['product_id']==product['product_id']]
            expected=sum((Decimal(str(x['qty'])) for x in prior),Decimal(0))+Decimal(str(product['quantity']))
            correct=correct and len(saved)==1 and saved[0]['name']==product['product_name'] and Decimal(str(saved[0]['qty']))==expected
        checks['requested_products_added']=bool(correct)
        checks['unrelated_items_unchanged']=[x for x in before if x['product_id'] not in ids]==[x for x in after if x['product_id'] not in ids]
    elif spec['operation']=='clear':checks['cart_empty']=not after
    else:raise ValueError('Unsupported cart operation')
    if spec.get('source_surface'):
        from .shopping_recent_cart import checks as recent_source_checks
        try:checks.update(recent_source_checks(spec,page.get('recent_cart_submissions'),site_origin=site_origin))
        except (ValueError,TypeError,KeyError):return unknown('Native Recently Ordered submission evidence unavailable')
    success=all(checks.values());return {'version':VERSION,'status':'success' if success else 'failure','reward':float(success),'checks':checks,'reason':None}


def cart_feedback(judgment):
    meanings={'page_valid':'The final page is valid on the task website.','coupon_unchanged':'The existing coupon was not changed.',
              'requested_item_removed':'The requested product is absent from the saved cart.','unrelated_items_unchanged':'Other cart item quantities and attributes remain unchanged.','cart_empty':'The saved cart contains no items.','requested_products_added':'The requested products and quantities were added to the saved cart.'}
    meanings.update(requested_item_saved_to_wishlist='The requested product and its quantity are saved in the current account wishlist.',
        unrelated_options_unchanged='Other cart item options remain unchanged.',
        other_wishlist_items_unchanged='Other wishlist entries remain unchanged.',
        other_collections_unchanged='Other saved product collections remain unchanged.',
        transfer_product_unchanged='The referenced catalog product remains unchanged.')
    from .shopping_recent_cart import FEEDBACK as RECENT_FEEDBACK
    meanings.update(RECENT_FEEDBACK)
    from .cart_quantity import FEEDBACK as QUANTITY_FEEDBACK
    meanings.update(QUANTITY_FEEDBACK)
    from .cart_options import FEEDBACK as OPTION_FEEDBACK
    meanings.update(OPTION_FEEDBACK)
    from .cart_edit import FEEDBACK as EDIT_FEEDBACK
    meanings.update(EDIT_FEEDBACK)
    return {'status':judgment['status'],'reward':judgment['reward'],'reason':judgment.get('reason'),'checks':[{'name':k,'passed':v,'condition':meanings[k]} for k,v in judgment['checks'].items()],'action_sequence_provided':False}


def cart_control_results(c):
    expected={'no_op':'failure','wrong_object_or_partial':'failure','positive':'success','404':'failure','login':'failure'}
    if c['cart']['operation']=='move_to_wishlist':expected.update(removed_without_wishlist='failure',wishlisted_without_removal='failure')
    if c['cart']['operation']=='change_quantities':expected.update(unsaved='failure',alternative_quantity='success')
    if c['cart']['operation']=='edit_items':expected.update(unsaved='failure',alternative_quantity='success',remove_existing='success',alternative_option='success')
    if c['cart']['operation']=='change_options':
        expected.update(unsaved='failure')
        if c['cart'].get('requested_option'):expected['wrong_option']='failure'
        else:expected['alternative_option']='success'
    if c['cart']['operation']=='add_products':
        products=c['cart']['products']
        if any(Decimal(str(p['quantity']))!=1 for p in products):expected['wrong_quantity']='failure'
        if len(products)>1:expected['partial_products']='failure'
    if c['cart'].get('source_surface'):expected.update(unsaved='failure',wrong_surface='failure')
    return expected


def require_cart_admission(c,proof):
    if c.get('heldout_quarantine'):raise ValueError('Heldout source is quarantined')
    if proof.get('admission_version')!=ADMISSION_VERSION or proof.get('contract_fingerprint')!=contract_fingerprint(c):raise ValueError('Stale cart admission')
    cycles=proof.get('cycles',[]);expected=cart_control_results(c)
    if not proof.get('passed') or len(cycles)!=2:raise ValueError('Two independent cart control/reset cycles required')
    for cycle in cycles:
        if not cycle.get('passed') or cycle.get('checks')!=expected or cycle.get('initial_state')!=cycle.get('wrong_initial_state'):raise ValueError('Cart controls or reset failed')
        for name in ('wrong_quantity','partial_products','removed_without_wishlist','wishlisted_without_removal','alternative_quantity','wrong_option','alternative_option','remove_existing'):
            if name in expected and cycle.get('variant_initial_states',{}).get(name)!=cycle['initial_state']:
                raise ValueError('Extra quantity/product negative must start from the same baseline')
        validate_initial(c,cycle['initial_state'])
        if c['cart'].get('source_surface'):
            expected_reference={'customer_id':c['cart']['customer_id'],'order_item_ids':sorted(r['order_item_id']for r in c['cart']['source_surface']['items'])}
            if (cycle.get('recent_source_reference')!=expected_reference or cycle.get('recent_source_reference_after')!=expected_reference
                    or cycle.get('variant_initial_states',{}).get('wrong_surface')!=cycle['initial_state']
                    or cycle.get('restored')is not True or not cycle.get('initial_fingerprint')
                    or cycle.get('initial_fingerprint')!=cycle.get('final_fingerprint')):
                raise ValueError('Native source reference or independent wrong-source cart baseline changed')
    if cycles[0]['initial_state']!=cycles[1]['initial_state']:raise ValueError('Cart baseline changed across resets')
    if c['cart'].get('source_surface') and cycles[0]['initial_fingerprint']!=cycles[1]['initial_fingerprint']:
        raise ValueError('Native source protected-state baseline changed across independent resets')
    if proof.get('shared_control_source'):
        import hashlib,json
        from pathlib import Path
        ref=proof['shared_control_source'];raw=Path(ref['file']).read_bytes();original=json.loads(raw)
        if (hashlib.sha256(raw).hexdigest()!=ref['sha256'] or original.get('control_signature')!=control_signature(c)
                or proof.get('control_signature')!=control_signature(c) or original.get('cycles')!=cycles
                or original.get('passed')is not True or original.get('shared_control_source')):
            raise ValueError('Shared cart controls changed or do not cover this initialization and operation')
