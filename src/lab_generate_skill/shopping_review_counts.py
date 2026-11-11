"""Product-identified review counts, including native zero-review storefronts.

CPU controls visit all permitted variants. Actor scoring accepts a named
variant with its own count; counts cannot be transferred between products.
"""
import re
from urllib.parse import urlsplit
from .site_database import select_rows
from .shopping_product_details import product_reference,read_product_details


def validate(q):
    products=q.get('products')
    if (q.get('family')!='shopping_review_counts' or q.get('fields')!={'products':'record_subset'}
            or q.get('record_fields')!={'products':{'name':'string','review_count':'integer'}}
            or q.get('minimum_records')!={'products':1}):
        raise ValueError('Review count requires named product records')
    if not isinstance(products,list) or not products or any(type(p.get('entity_id'))is not int or p['entity_id']<=0 for p in products):
        raise ValueError('Explicit product identities required')
    for key in ('entity_id','name','sku','url_key'):
        if len({p[key]for p in products})!=len(products):raise ValueError('Ambiguous product identity')
    for p in products:
        if not re.fullmatch(r'[a-z0-9-]+',p['url_key']):raise ValueError('Unsafe product path')


def saved_count(site,ident):
    if type(ident)is not int or ident<=0:raise ValueError('Invalid product')
    counts=select_rows(site,f"SELECT count(DISTINCT r.review_id) AS count FROM review r JOIN review_store s ON s.review_id=r.review_id WHERE r.entity_pk_value={ident} AND r.status_id=1 AND s.store_id=1 AND r.entity_id=(SELECT entity_id FROM review_entity WHERE entity_code='product')")
    if len(counts)!=1:raise ValueError('Missing approved review count')
    count=int(counts[0]['count'])
    summaries=select_rows(site,f"SELECT reviews_count FROM review_entity_summary WHERE entity_pk_value={ident} AND store_id=1 AND entity_type=1")
    if count<0 or len(summaries)>1 or (summaries and int(summaries[0]['reviews_count'])!=count) or (not summaries and count!=0):
        raise ValueError('Approved reviews and native summary disagree')
    return count


def reference(site,q):
    validate(q);products=sorted(q['products'],key=lambda p:p['entity_id'])
    if product_reference(site,[p['entity_id']for p in products])!=products:
        raise ValueError('Review product identities changed')
    return {'object_id':'shopping-review-counts:'+','.join(str(p['entity_id'])for p in products),
        'values':{'products':[{'name':p['name'],'review_count':saved_count(site,p['entity_id'])}for p in products]}}


def visible_count(page):
    labels=page.locator('.product-info-main .reviews-actions a:visible').all_text_contents()
    labels=[' '.join(v.split()) for v in labels]
    counts=[int(m.group(1).replace(',',''))for v in labels if (m:=re.fullmatch(r'(\d[\d,]*) Reviews?',v))]
    zeros=[v for v in labels if v=='Be the first to review this product']
    if len(counts)==1 and not zeros:return counts[0]
    if len(zeros)==1 and not counts:return 0
    raise ValueError('Visible review count absent or contradictory')


def ui_values(page,q):
    """Private CPU observability check; never invoked to guide the actor."""
    validate(q);origin=urlsplit(page.url);values=[]
    for p in q['products']:
        response=page.goto(origin.scheme+'://'+origin.netloc+'/'+p['url_key']+'.html',wait_until='domcontentloaded',timeout=60000)
        if response is None or response.status!=200:raise ValueError('Product page unavailable')
        page.locator('.product-info-main').wait_for(state='visible',timeout=10000)
        identity=read_product_details(page)
        if not identity['summary_visible'] or identity['product_id']!=str(p['entity_id']) or identity['name']!=p['name'] or identity['sku']!=p['sku']:
            raise ValueError('Wrong visible review product')
        values.append({'name':identity['name'],'review_count':visible_count(page)})
    return {'products':values}
