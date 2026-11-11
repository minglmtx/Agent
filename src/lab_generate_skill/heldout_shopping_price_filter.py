"""Private, source-bound native preparation for one literal heldout find task.

No training admission and no Actor adapter. The future Actor adapter must bind
observed cards/answers to actual dispatched requests before using this predicate.
"""
from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit
import hashlib
import json
import re

SID = '3750b80a86a046089c0f'
GOAL = 'Find electronics products under $50'
START = '/privacy-policy-cookie-restriction-mode'

def require(value, message):
    if not value:
        raise ValueError(message)

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def amount(value):
    require(type(value) in (str,int), 'Explicit finite decimal required')
    try: result = Decimal(str(value))
    except InvalidOperation: raise ValueError('Malformed price') from None
    require(result.is_finite() and result >= 0, 'Finite nonnegative price required')
    return result

def bind_source(contract):
    require(contract.get('source_task_id') == contract.get('task_id') == SID
            and contract.get('goal') == GOAL and contract.get('start_path') == START
            and contract.get('domain') == 'shopping' and contract.get('split') == 'test'
            and contract.get('heldout_quarantine') is True and contract.get('eligible_for_training') is False,
            'Exact original quarantined source required')
    auth=contract['source_authentication']
    require(auth['mode']=='authenticated' and auth['welcome_names']==['Emma Lopez']
            and auth['cart_labels']==['\ue611 My Cart 3 3items']
            and auth['database_account_identity_verified'] is False and auth['cart_contents_verified'] is False,
            'Preserve original visible account/cart scope without inventing historical IDs')
    return dict(version='heldout-shopping-price-find-derived-v1',source_task_id=SID,
        original_contract=contract,initialization_kind='explicit_native_derivative',
        original_instance_equivalence=False,original_account_id_verified=False,original_cart_contents_verified=False,
        expected_public_name='Emma Lopez',expected_cart_quantity='3',category_label='Electronics',
        currency='USD',operator='strict_less_than',price='50',heldout_quarantine=True,eligible_for_training=False)

def public_task(binding):
    bind_source(binding['original_contract'])
    return dict(task_id=SID,domain='shopping',goal=GOAL,start_path=START)

def validate_full31(value):
    from .shopping_search_protection import TABLES
    expected=set(TABLES)|{'quote','quote_address','quote_payment','sales_order_status_history','review',
                         'review_detail','review_store','review_entity_summary','rating_option_vote'}
    require(value.get('version')=='shopping-complete-native-query-full-rows-v1'
            and value.get('statement_budget_seconds')==20 and set(value.get('tables',{}))==expected,
            'Original exact complete31 required')
    for row in value['tables'].values():
        require(row.get('ignored_columns')==[] and type(row.get('rows')) is int and row['rows']>=0
                and row.get('primary_key') and set(row['primary_key'])<=set(row.get('columns',[]))
                and re.fullmatch('[0-9a-f]{64}',row.get('sha256','')), 'Every full row/column digest required')
    return value

def full31_equal(before,after):
    require(validate_full31(before)==validate_full31(after),'Full31 changed; no field/timestamp exception')

def account_state(site,username):
    from .site_database import select_rows
    from .site_cart_rules import cart_state
    from .shopping_catalog_facts import only
    name=username.replace("'","''")
    customer=only(select_rows(site,"SELECT entity_id,firstname,lastname,group_id,website_id,store_id FROM customer_entity WHERE email='"+name+"'"))
    cart=cart_state(site,username)
    require(int(customer['entity_id'])==cart['user_id'],'Fresh cart/customer identity disagreement')
    compare=select_rows(site,f"SELECT product_id FROM catalog_compare_item WHERE customer_id={cart['user_id']} ORDER BY product_id")
    return dict(customer=customer,cart=cart,compare=compare,
                cart_quantity=str(sum((amount(x['qty']) for x in cart['items']),Decimal(0))))

def validate_initial(binding,page,account,origin):
    require(binding==bind_source(binding['original_contract']),'Changed binding')
    parts=urlsplit(page['url']); base=urlsplit(origin)
    require((parts.scheme,parts.netloc)==(base.scheme,base.netloc) and parts.path==START
            and page.get('http_status')==200,'Exact public start and healthy page required')
    require(page['native_header_before_capture']==page['native_header_text']
            and 'Welcome, Emma Lopez!' in page['native_header_text'],'Original visible welcome state differs')
    customer=account['customer']; widgets=page['native_business_state']
    require(customer['firstname']=='Emma' and customer['lastname']=='Lopez'
            and amount(account['cart_quantity'])==Decimal(3) and amount(widgets['cart_summary'])==Decimal(3),
            'Original visible name/cart quantity must hold; native IDs are derived facts')
    require(widgets['customer_fullname']=='Emma Lopez' and account['compare']==[]
            and widgets['compare_count']==0,'Current native/customer-data account or compare state differs')
    require(page['source_authentication_check']['source_welcome_text_present'] is True,
            'Original public header check required')
    return dict(passed=True,source_task_id=SID,original_instance_equivalence=False,
                original_account_id_verified=False,original_cart_contents_verified=False,
                fresh_business_state=account,public_name='Emma Lopez',public_cart_quantity=3,
                raw_source_ax_differences_retained=True)

def indexed_price_coverage(ids,rows,group,website):
    """Keep every requested member; absent native prices remain explicitly unknown."""
    expected=sorted(set(ids));actual=[int(r['entity_id'])for r in rows]
    require(len(actual)==len(set(actual)) and set(actual)<=set(expected),'Duplicate or foreign native price index rows')
    require(all(int(r['customer_group_id'])==group and int(r['website_id'])==website for r in rows),
            'Native price account/website scope differs')
    for r in rows:
        amount(r['final_price']);amount(r['min_price']);amount(r['max_price'])
    missing=sorted(set(expected)-set(actual))
    return dict(requested_count=len(expected),priced_count=len(actual),unknown_price_ids=missing,complete=not missing)

def price_rows(site,ids,group,website,*,require_complete=True):
    from .site_database import select_rows
    require(ids and all(type(x) is int and x>0 for x in ids) and type(group) is int and group>=0
            and type(website) is int and website>0,'Bounded native price scope')
    values=','.join(map(str,sorted(set(ids))))
    rows=select_rows(site,f'SELECT entity_id,customer_group_id,website_id,price,final_price,min_price,max_price FROM catalog_product_index_price WHERE entity_id IN ({values}) AND customer_group_id={group} AND website_id={website} ORDER BY entity_id')
    coverage=indexed_price_coverage(ids,rows,group,website)
    if require_complete:require(coverage['complete'],'Complete unique native price index required')
    return rows

def make_reference(site,account):
    from .site_database import select_rows
    from .shopping_category import category_metadata,category_products
    from .shopping_product_details import product_reference
    from .shopping_catalog_facts import only
    category=only(select_rows(site,"SELECT e.entity_id FROM catalog_category_entity e JOIN catalog_category_entity_varchar n ON n.entity_id=e.entity_id AND n.store_id=0 AND n.attribute_id=(SELECT attribute_id FROM eav_attribute WHERE entity_type_id=3 AND attribute_code='name') WHERE n.value='Electronics' ORDER BY e.entity_id"))
    ident=int(category['entity_id']);metadata=category_metadata(site,[ident]);members=category_products(site,ident)
    require(metadata and metadata[0]['name']=='Electronics','Literal native category required')
    # Catalog-only=2, search-only=3 and both=4 are all legitimate find routes.
    # Preserve every raw membership row; do not borrow a category-view-only gate.
    ids=sorted({int(r['product_id']) for r in members if int(r['visibility']) in (2,3,4)})
    require(len(ids)<=20000,'Reference collection exceeds bounded native preparation')
    group=int(account['customer']['group_id']);website=int(account['customer']['website_id'])
    currencies=select_rows(site,"SELECT scope,scope_id,path,value FROM core_config_data WHERE path IN ('currency/options/base','currency/options/default') ORDER BY scope,scope_id,path")
    require(currencies and {r['value'] for r in currencies}=={'USD'},'Unambiguous native default/base USD required')
    products=product_reference(site,ids) if ids else []
    require([int(r['entity_id']) for r in products]==ids,'Complete category product identities required')
    prices=price_rows(site,ids,group,website,require_complete=False) if ids else []
    coverage=indexed_price_coverage(ids,prices,group,website)
    routes=select_rows(site,f"SELECT request_path,target_path FROM url_rewrite WHERE entity_type='category' AND entity_id={ident} AND store_id=1 AND redirect_type=0 ORDER BY request_path")
    require(routes and all(not r['request_path'].startswith('/') for r in routes),'Native category routes missing')
    visibility={str(v):sum(int(r['visibility'])==v for r in members) for v in sorted({int(r['visibility'])for r in members})}
    return dict(version='heldout-shopping-price-reference-v2',source_task_id=SID,complete=coverage['complete'],
        membership_complete=True,price_coverage=coverage,currency='USD',
        category_id=ident,category_metadata=metadata,product_index=members,products=products,prices=prices,
        customer_group_id=group,website_id=website,currency_config=currencies,routes=routes,
        actual_visibility_distribution=visibility,public_visibility_values=[2,3,4],
        matching_ids=[int(r['entity_id']) for r in prices if amount(r['final_price'])<Decimal(50)])

CARD_JS = r'''() => {
 const visible=e=>!!e && !!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
 return [...document.querySelectorAll('.products.wrapper')].filter(visible).flatMap(list=>
  [...list.querySelectorAll('li.product-item')].filter(visible).map(e=>{
   const link=e.querySelector('.product-item-link'), box=e.querySelector('[data-price-type="finalPrice"]');
   return {id:e.querySelector('[data-product-id]')?.getAttribute('data-product-id')||'',
    name:link?.innerText.trim()||'',url:link?.href||'',name_visible:visible(link),
    price_attribute:box?.getAttribute('data-price-amount'),price_visible:visible(box),
    price_text:box?.innerText.trim()||''};
  }));
}'''

def capture_results(page,site,reference,*,http_status):
    from .shopping_search import read_search_state
    from .shopping_category import read_category_page
    from .shopping_product_details import product_reference
    from .site_database import select_rows
    from .shopping_customer_sections import wait_initialized
    readiness=wait_initialized(page)
    page.wait_for_function("() => document.readyState==='complete' && !(window.jQuery && jQuery.active)",timeout=30000)
    search=read_search_state(page);category=read_category_page(page);cards=page.evaluate(CARD_JS)
    require(len(cards)==len(category['products']),'All currently displayed cards required')
    result=dict(source_task_id=SID,url=page.url,http_status=http_status,document_complete=True,readiness=readiness,
                search=search,category=category,cards=cards,reference_sha256=digest(reference),currency='USD')
    if not cards:
        result['native_products']=[];result['native_prices']=[];result['native_paths']=[];return result
    require(all(re.fullmatch('[1-9][0-9]*',c['id']) for c in cards),'Actual card product identity missing')
    ids=[int(c['id']) for c in cards];require(len(ids)==len(set(ids)),'Duplicate displayed native identity')
    result['native_products']=product_reference(site,ids)
    result['native_prices']=price_rows(site,ids,reference['customer_group_id'],reference['website_id'],require_complete=False)
    values=','.join(map(str,sorted(ids)))
    result['native_paths']=select_rows(site,f"SELECT entity_id,request_path FROM url_rewrite WHERE entity_type='product' AND entity_id IN ({values}) AND store_id=1 AND redirect_type=0 ORDER BY entity_id,request_path")
    return result

def judge(binding,state,reference,*,branch='view',identified_ids=None):
    """Native predicate only; this does not authenticate an Actor observation/answer."""
    def answer(status,reason,checks=None):
        return dict(status=status,reward=None if status=='unknown' else float(status=='success'),
                    reason=reason,checks=checks or {},source_task_id=SID,actor_admission=False,eligible_for_training=False)
    try:
        require(binding==bind_source(binding['original_contract']) and reference['source_task_id']==state['source_task_id']==SID,
                'Source binding mismatch')
        require(reference['membership_complete'] is True and state['reference_sha256']==digest(reference)
                and reference['version']=='heldout-shopping-price-reference-v2'
                and reference['category_metadata'][0]['name']=='Electronics'
                and reference['currency']==state['currency']=='USD' and state['document_complete'] is True
                and state['http_status']==200,
                'Complete stable native reference/normal public load missing')
        products={int(r['entity_id']):r for r in reference['products']}
        prices={int(r['entity_id']):r for r in reference['prices']}
        members={int(r['product_id']) for r in reference['product_index'] if int(r['visibility']) in (2,3,4)}
        require(set(products)==members and len(products)==len(reference['products']), 'Incomplete native category membership')
        coverage=indexed_price_coverage(sorted(members),reference['prices'],reference['customer_group_id'],reference['website_id'])
        require(coverage==reference['price_coverage'] and type(reference['complete'])is bool
                and reference['complete']==coverage['complete'],'Explicit native price coverage differs')
        matching={i for i in prices if amount(prices[i]['final_price'])<Decimal(50)}
        require(set(reference['matching_ids'])==matching,'Native matching set differs')
        require(branch in ('view','answer'),'Unknown completion branch')
        cards=state['cards']
        if not cards:
            require(state['search']['empty_result'] is True and state['category']['products']==[]
                    and state['native_products']==state['native_prices']==state['native_paths']==[],
                    'Missing cards are not a normal consistent empty result')
            require(branch=='view' or identified_ids==[], 'Empty result cannot identify products')
            if not matching and not coverage['complete']:
                return answer('unknown','No known matches, but native prices remain unknown for category members')
            return answer('failure' if matching else 'success','Native matches exist but none found' if matching else 'Normal empty result and complete native reference has no matches')
        ids=[int(c['id']) for c in cards]
        require(len(ids)==len(set(ids)) and len(cards)==len(state['category']['products'])
                and [int(r['id']) for r in state['category']['products']]==ids,'All displayed cards required')
        if branch=='answer':
            require(isinstance(identified_ids,list) and identified_ids and all(type(i)is int for i in identified_ids)
                    and len(identified_ids)==len(set(identified_ids)) and set(identified_ids)<=set(ids),
                    'Answer subset must be explicitly identified in the actual observed cards')
            selected=set(identified_ids)
        else:selected=set(ids)
        native={int(r['entity_id']):r for r in state['native_products']};actual_prices={int(r['entity_id']):r for r in state['native_prices']}
        require(set(native)==set(ids) and len(native)==len(state['native_products']),'Complete actual object identity missing')
        indexed_price_coverage(ids,state['native_prices'],reference['customer_group_id'],reference['website_id'])
        require(selected<=set(actual_prices),'A selected observed object has no verified native price')
        valid=[]
        for card in cards:
            ident=int(card['id']);product=native[ident]
            allowed_paths={'/'+r['request_path'] for r in state['native_paths'] if int(r['entity_id'])==ident}
            require(card['name_visible'] is True and card['price_visible'] is True and card['name']==product['name']
                    and urlsplit(card['url']).path in allowed_paths and urlsplit(card['url']).netloc==urlsplit(state['url']).netloc,
                    'Visible product name/path/identity mismatch')
            if ident not in selected:continue
            price=actual_prices[ident]
            text=card['price_text'];require(re.fullmatch(r'\$\s*[\d,]+(?:\.\d{2})?',text),'Unambiguous displayed USD price required')
            visible=amount(text.replace('$','').replace(',','').strip())
            require(visible==amount(card['price_attribute'])==amount(price['final_price']),'Visible/native final price differs')
            if ident in members:
                require(ident in prices and product==products[ident] and price==prices[ident],'Category/reference object changed or price is unknown')
            if ident in selected:valid.append(ident in members and visible<Decimal(50))
        return answer('success' if all(valid) else 'failure',None,
                      dict(nonempty_identified_set=True,all_identified_products_match=all(valid),
                           all_current_cards_considered=branch=='view',no_total_or_pagination_requirement=True))
    except (ValueError,KeyError,TypeError,InvalidOperation) as exc:
        return answer('unknown',str(exc))
