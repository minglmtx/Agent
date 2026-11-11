"""Independent native scopes for remaining Shopping tasks; never an actor policy.

Kept private until two fresh normal controls and common-runtime integration pass.
Multiple members are a collection/alternative set, not automatic ambiguity.
"""
from collections import Counter
from decimal import Decimal, InvalidOperation
import re
from urllib.parse import urlsplit

from .product_description_fields import clean_table_text
from .site_navigation_rules import valid_initial_page
from .site_query_rules import same_value, reference_fingerprint

VERSION='shopping-remaining-native-controls-v1'


def decimal(value):
    if isinstance(value,bool) or not isinstance(value,(str,int,Decimal)) or not re.fullmatch(r'\d+(?:\.\d+)?',str(value)):
        raise ValueError('Explicit nonnegative native numeric amount required')
    try:amount=Decimal(str(value))
    except InvalidOperation as exc:raise ValueError('Malformed native amount') from exc
    if not amount.is_finite() or amount<0:raise ValueError('Invalid native amount')
    return format(amount.normalize(),'f')


def exact_named_products(group, name):
    """A full named prefix must occur contiguously, with a word boundary."""
    if not isinstance(name,str) or not name.strip():raise ValueError('Explicit named product required')
    target=' '.join(name.casefold().split());matches=[]
    for row in group:
        text=' '.join(row['name'].casefold().split())
        if text==target or text.startswith(target) and not text[len(target):len(target)+1].isalnum():matches.append(row)
    if not matches:raise ValueError('Requested named product absent')
    if len(matches)!=1:raise ValueError('Full named product remains ambiguous')
    return matches[0]


def native_price_records(products, prices, *, terms=(), upper=None):
    """Join by public product identity, never position or an unrelated cart price."""
    if not isinstance(products,list) or not isinstance(prices,list):raise ValueError('Native products/prices missing')
    seen=set();result=[]
    for row in products:
        ident=row.get('id',row.get('product_id'));name=row.get('name')
        if not isinstance(ident,(str,int)) or isinstance(ident,bool) or not str(ident).isdigit() or int(ident)<=0 or str(ident)in seen:
            raise ValueError('Missing or duplicate native product identity')
        if not isinstance(name,str) or not name.strip():raise ValueError('Native product name missing')
        seen.add(str(ident))
        if any(t.casefold() not in name.casefold() for t in terms):continue
        matches=[p for p in prices if str(p.get('product_id'))==str(ident)]
        if len(matches)!=1:raise ValueError('Exactly one current price box per matching product required')
        amounts=[a.get('amount')for a in matches[0].get('amounts',[])if a.get('type')=='finalPrice']
        if len(amounts)!=1:raise ValueError('One current final-price amount required')
        amount=decimal(amounts[0])
        if upper is not None and not Decimal(amount)<Decimal(decimal(upper)):continue
        result.append({'name':name,'price':amount})
    return result


def original_page_membership(initial, native):
    """Bind 'on this page' to the first native page, not the whole catalog."""
    actual=[(int(r['id']),r['name'])for r in initial['collection']['products']]
    expected=[(int(r['id']),r['name'])for r in native['products']]
    if not actual or actual!=expected or native.get('page')!=1:
        raise ValueError('Independent native first-page membership/order differs')
    return actual


def category_subset_ui_matches(contract, capture, complete, first_page):
    """Verify a public subset against an independently complete native scope.

    Public first-page membership, category, total and prices are checked
    separately. A valid task answer need not enumerate the whole category.
    """
    from .shopping_collection_reference import compare_native_public
    q=contract['query']
    if q.get('family')!='shopping_native_category_price_subset':
        raise ValueError('Explicit native category subset contract required')
    full=complete['source_state']
    ids=[r['id']for r in full['products']]
    if (len(ids)!=len(set(ids)) or len(ids)!=full['total'] or full['total']!=first_page['total']
        or full['category']!=first_page['category'] or full['scope']!=first_page['scope']):
        raise ValueError('Complete reference and first-page native scopes differ')
    checks=compare_native_public(first_page,capture['collection'],q['scope'])
    if not checks or not all(checks.values()):
        raise ValueError('Actual public category scope differs from native first page')
    public_all=native_price_records(capture['collection']['products'],capture['public']['prices'])
    expected_all=[{'name':r['name'],'price':decimal(str(r['price']))}for r in first_page['products']]
    shape=q['record_fields']['products']
    if not same_value('record_set',public_all,expected_all,record_fields=shape):
        raise ValueError('Public current prices differ from independent first-page prices')
    subset=native_price_records(capture['collection']['products'],capture['public']['prices'],upper='100')
    return {'products':subset},same_value('record_subset',subset,complete['values']['products'],
        record_fields=shape,minimum_records=q['minimum_records']['products'])


def allowed_review_products(group):
    result=[r for r in group if re.search(r'\bv8\b',r['name'],re.I) and re.search(r'\benergy\b',r['name'],re.I)]
    if not result or len({r['entity_id']for r in result})!=len(result):raise ValueError('Native review alternatives missing or duplicated')
    return result


def reviews_checks(spec, state):
    """A genuine review page of any allowed product; unrelated variants fail."""
    from .shopping_product_panel import panel_checks
    if not isinstance(state,dict):raise ValueError('Native review capture missing')
    candidates=[p for p in spec['alternatives']if str(p['product_id'])==state.get('product_id')]
    if len(candidates)!=1:
        return {'allowed_review_product':False,'product_reviews_displayed':False,'approved_review_content':False}
    candidate=candidates[0];approved=[r for r in candidate['reviews']if int(r['status_id'])==1]
    if approved:return {'allowed_review_product':True,**panel_checks(candidate,state)}
    if not isinstance(state.get('rows'),list):raise ValueError('Empty-review rows were not captured')
    return {'allowed_review_product':True,
            'panel_product_identity':state.get('product_name')==candidate['product_name'],
            'product_reviews_displayed':state.get('reviews_visible')is True,
            'approved_review_content':state['rows']==[] and state.get('native_first_review_link')is True and state.get('form_visible')is True}


def fingerprint(contract):
    return reference_fingerprint({k:contract.get(k)for k in ('task_id','source_task_id','domain','goal','start_path','query','native_reviews','heldout_quarantine')})


def evaluate_review(contract,page,state,*,site_origin,runtime_error=None):
    if runtime_error or not isinstance(page,dict) or type(page.get('http_status'))is not int or page['http_status']<200 or page['http_status']>=500:
        return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':'Native final page/runtime evidence unavailable'}
    try:checks={'page_valid':valid_initial_page(page,site_origin=site_origin),**reviews_checks(contract['native_reviews'],state)}
    except (ValueError,TypeError,KeyError):return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':'Native review reference/capture unavailable'}
    success=all(checks.values());return {'version':VERSION,'status':'success'if success else'failure','reward':float(success),'checks':checks,'reason':None}


def read_reviews(page):
    from .shopping_product_panel import read_product_panel
    state=read_product_panel(page)
    state['native_first_review_link']=page.locator('.product-info-main .reviews-actions a').evaluate_all("es=>es.some(e=>e.getClientRects().length && e.innerText.trim()==='Be the first to review this product')")
    return state


def require_normal_admission(contract,proof):
    """Private versioned proof only; does not register in the shared actor runner."""
    if contract.get('heldout_quarantine') or contract.get('eligible_for_training'):raise ValueError('Development original scope only')
    if proof.get('admission_version')!=VERSION or proof.get('contract_fingerprint')!=fingerprint(contract):raise ValueError('Wrong/stale private normal proof')
    cycles=proof.get('cycles',[])
    if proof.get('passed')is not True or len(cycles)!=2:raise ValueError('Two fresh normal cycles required')
    if any(c.get('passed')is not True or c.get('initial_valid')is not True or c.get('protected_unchanged')is not True
           or c.get('before_reference')!=c.get('after_reference') or c.get('initial_fingerprint')!=c.get('final_fingerprint')
           or not c.get('initial_fingerprint')or c.get('normal_controls_real_native')is not True
           or c.get('contract_fingerprint')!=fingerprint(contract)
           or not c.get('before_protected') or c.get('before_protected')!=c.get('after_protected') for c in cycles):
        raise ValueError('Original start/reference/protected reset checks failed')
    if (cycles[0]['before_reference']!=cycles[1]['before_reference'] or cycles[0]['initial_fingerprint']!=cycles[1]['initial_fingerprint']
        or cycles[0]['before_protected']!=cycles[1]['before_protected']):
        raise ValueError('Independent fresh reference/baseline differs')
    required={'positive':'success','no_op':'failure','wrong_object':'failure','404':'failure','login':'failure'}
    if contract.get('query'):required.update(no_answer='failure',wrong_value='failure',missing_field='failure')
    else:required.update(hidden_panel='failure',heading_only='failure')
    if any(any(c.get('checks',{}).get(k)!=v for k,v in required.items())for c in cycles):raise ValueError('Normal positive/negative controls missing')
