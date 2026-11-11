"""Task-independent typed questions over fixed, native Shopping collections."""
import re
from urllib.parse import urlsplit, parse_qs
from .shopping_collection_reference import (validate_scope, native_collection, public_collection,
    normalized_label, public_facet, total_from_toolbar)
from .site_auth import credentials

SCHEMAS = {'categories':{'categories':'record_set'}, 'price_ranges':{'ranges':'record_set'},
           'count':{'count':'integer'}, 'highest_rated_first_page':{'product':'string_choice'}}


def validate(q):
    kind=q.get('kind')
    if q.get('family')!='shopping_collection' or kind not in SCHEMAS or q.get('fields')!=SCHEMAS[kind]:
        raise ValueError('Unsupported collection question')
    validate_scope(q['scope'])
    if q.get('reference_path')!=q['scope']['path']:
        raise ValueError('Conflicting collection scope')
    if kind in ('categories','price_ranges'):
        field='categories' if kind=='categories' else 'ranges'
        if q['scope']['kind']!='category' or q.get('record_fields')!={field:{'name':'string'}}:
            raise ValueError('Category/facet record shape required')
    if kind=='highest_rated_first_page':
        members=q.get('first_page_members')
        if not members or any(type(i)is not int or i<=0 for i in members) or len(set(members))!=len(members):
            raise ValueError('Original first-page membership required')


def native_values(q, native):
    kind=q['kind']
    if kind=='count':return {'count':native['total']}
    if kind in ('categories','price_ranges'):
        parameter='cat' if kind=='categories' else 'price'
        found=[r for r in native['facets'] if r['parameter']==parameter]
        if len(found)!=1 or not found[0]['items']:raise ValueError('Missing native facet')
        names=[normalized_label(i['label']) for i in found[0]['items']]
        if any(not n for n in names) or len(set(names))!=len(names):raise ValueError('Ambiguous facet labels')
        return {next(iter(q['fields'])):[{'name':n} for n in names]}
    if [r['id'] for r in native['products']]!=q['first_page_members']:
        raise ValueError('Original first page changed')
    ratings={r['product_id']:int(r['rating_summary']) for r in native['ratings'] if int(r['reviews_count'])>0 and int(r['rating_summary'])>0}
    rated=[(r['name'],ratings[r['id']]) for r in native['products'] if r['id'] in ratings]
    if not rated:raise ValueError('No reviewed products on original first page')
    maximum=max(v for _,v in rated)
    return {'product':sorted({n for n,v in rated if v==maximum})}


def reference(site,q):
    validate(q)
    native=native_collection(site,q['scope'],credentials(site.root,'shopping')['username'])
    return {'object_id':'shopping_collection:'+q['reference_path'], 'values':native_values(q,native), 'native_collection':native}


def public_values(q,public):
    validate(q)
    parts=urlsplit(public['url']);expected=urlsplit(q['reference_path'])
    if (parts.path,parse_qs(parts.query,keep_blank_values=True))!=(expected.path,parse_qs(expected.query,keep_blank_values=True)):
        raise ValueError('Public page scope mismatch')
    if q['scope']['kind']=='category':
        if 'catalog-category-view' not in public['classes'].split() or public['heading']!=q['heading']:
            raise ValueError('Wrong public category identity')
    elif public['heading']!='Catalog Advanced Search' or 'catalogsearch-advanced-result' not in public['classes'].split():
        raise ValueError('Wrong advanced-search page')
    if not public['products']:raise ValueError('Collection not rendered')
    kind=q['kind']
    if kind=='count':return {'count':total_from_toolbar(public['amount'])}
    if kind in ('categories','price_ranges'):
        rows=public_facet(public,'Category' if kind=='categories' else 'Price','cat' if kind=='categories' else 'price')
        return {next(iter(q['fields'])):[{'name':r['label']} for r in rows]}
    if [int(r['id']) for r in public['products']]!=q['first_page_members']:
        raise ValueError('Wrong first-page collection')
    rated=[]
    for product in public['products']:
        if product['rating'] is None:continue
        match=re.fullmatch(r'(\d+)%',product['rating'])
        if not match or not 0<int(match[1])<=100:raise ValueError('Invalid public rating')
        rated.append((product['name'],int(match[1])))
    if not rated:raise ValueError('No visible product ratings')
    maximum=max(v for _,v in rated)
    return {'product':sorted(n for n,v in rated if v==maximum)[0]}


def ui_values(page,q):
    return public_values(q,public_collection(page))
