"""Read-only populated GPX lists/details under an explicit synthetic profile.

This family covers browsing existing traces, not uploads, map overlays,
subscriptions, or claims that all paginated observations were read.
"""
import re
from urllib.parse import urlsplit,urljoin,unquote,parse_qs
from .map_community_fixture import GPS_PROFILE
from .map_gps_fixture import records


def validate(spec):
    if spec.get('scope','browse') not in ('browse','all_public'):
        raise ValueError('Unsupported GPS browsing scope')
    rows=spec.get('traces')
    if spec.get('fixture_version')!=GPS_PROFILE or not isinstance(rows,list)or not rows:
        raise ValueError('Explicit populated GPS reference required')
    for r in rows:
        if (not isinstance(r,dict)or type(r.get('id'))is not int or r['id']<=0
            or type(r.get('points'))is not int or r['points']<=0
            or any(not isinstance(r.get(k),str)or not r[k].strip()for k in ('author','name','description','visibility'))):
            raise ValueError('Incomplete public GPS identity/content')
    if len({r['id']for r in rows})!=len(rows):raise ValueError('Duplicate GPS reference')
    return rows


def public_records(state):
    return [{'id':r['id'],'author':r['display_name'],'name':r['name'],'description':r['description'],
        'points':r['points'],'visibility':r['visibility']}for r in state['traces']or []if r['visible']and r['inserted']]


def verify_reference(site,spec):
    expected=validate(spec)
    if getattr(site,'community_fixture',None)!=GPS_PROFILE:raise ValueError('Wrong populated GPS profile')
    if sorted(public_records(records(site)),key=lambda r:r['id'])!=sorted(expected,key=lambda r:r['id']):
        raise ValueError('GPS records differ from fixed initialization')


READ=r'''() => {
 const visible=e=>!!e&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 const links=e=>[...e.querySelectorAll('a[href]')].filter(visible).map(a=>({text:a.innerText.trim(),href:a.getAttribute('href')}));
 const root=document.querySelector('#content');
 return {url:location.href,headings:[...document.querySelectorAll('#content h1,#content h2')].filter(visible).map(e=>e.innerText.trim()),
   rows:[...document.querySelectorAll('#trace_list tbody tr')].filter(visible).map(e=>({text:e.innerText.trim(),links:links(e)})),
   detail_fields:root?[...root.querySelectorAll('table:not(#trace_list) tr')].filter(visible).map(r=>({
       cells:[...r.querySelectorAll('th,td')].filter(visible).map(e=>e.innerText.trim()),links:links(r)})):[]};
}'''


def read_gps_page(page):return page.evaluate(READ)


def checks(spec,state):
    expected=validate(spec)
    if (not isinstance(state,dict)or not isinstance(state.get('url'),str)
        or any(not isinstance(state.get(k),list)for k in ('headings','rows','detail_fields'))):
        raise ValueError('Missing native GPS capture')
    u=urlsplit(state['url']);path=unquote(u.path).rstrip('/');params=parse_qs(u.query,keep_blank_values=True)
    def has_link(links,target,text=None):
        for link in links:
            if not isinstance(link,dict)or not isinstance(link.get('href'),str):raise ValueError('Malformed GPS link')
            actual=urlsplit(urljoin(state['url'],link['href']))
            if ((actual.scheme,actual.netloc)==(u.scheme,u.netloc)and unquote(actual.path)==target
                and not actual.query and not actual.fragment and (text is None or link.get('text')==text)):
                return True
        return False
    authors={r['author']for r in expected}
    list_page=(path=='/traces'and 'Public GPS Traces'in state['headings'])or any(
        path=='/user/'+author+'/traces'and 'Public GPS Traces from '+author in state['headings']for author in authors)
    if list_page:
        scope_ok=not params or params=={'page':['1']}
        if spec.get('scope')=='all_public':scope_ok &= path=='/traces'
        references=expected if path=='/traces'else [r for r in expected if path=='/user/'+r['author']+'/traces']
        matched=[]
        for ref in references:
            candidates=[]
            for row in state['rows']:
                if not isinstance(row,dict)or not isinstance(row.get('text'),str)or not isinstance(row.get('links'),list):raise ValueError('Malformed trace list row')
                if has_link(row['links'],'/user/'+ref['author']+'/traces/'+str(ref['id']),ref['name']):candidates.append(row)
            matched.append(len(candidates)==1 and ref['description']in candidates[0]['text']
                and re.search(r'(?<![\d.,])'+str(ref['points'])+r'\s+point'+(''if ref['points']==1 else 's')+r'\b',candidates[0]['text'])is not None
                and re.search(r'\b'+re.escape(ref['visibility'].upper())+r'\b',candidates[0]['text'])is not None
                and has_link(candidates[0]['links'],'/user/'+ref['author'],ref['author']))
        return {'populated_gps_identity':scope_ok,'populated_gps_content':len(state['rows'])==len(references)and all(matched)}
    detail=[r for r in expected if path=='/user/'+r['author']+'/traces/'+str(r['id'])]
    out={'populated_gps_identity':len(detail)==1 and not params and spec.get('scope')!='all_public','populated_gps_content':False}
    if len(detail)!=1:return out
    ref=detail[0];fields={};links=[]
    for row in state['detail_fields']:
        if not isinstance(row,dict)or not isinstance(row.get('cells'),list)or not isinstance(row.get('links'),list):raise ValueError('Malformed trace detail')
        if len(row['cells'])!=2 or any(not isinstance(x,str)for x in row['cells']):continue
        key=row['cells'][0].rstrip(':').strip()
        if key in fields:return out
        fields[key]=row['cells'][1];links+=row['links']
    out['populated_gps_identity'] &= 'Viewing Trace '+ref['name']in state['headings']
    out['populated_gps_content']=(fields.get('Filename')==ref['name']+' (download)'
        and fields.get('Description')==ref['description']and fields.get('Points')==str(ref['points'])
        and fields.get('Owner')==ref['author']and fields.get('Visibility','').split(' (')[0].casefold()==ref['visibility']
        and has_link(links,'/trace/'+str(ref['id'])+'/data','download')
        and has_link(links,'/user/'+ref['author'],ref['author']))
    return out


FEEDBACK={'populated_gps_identity':'The displayed native GPS page matches the requested collection scope or trace identity.',
          'populated_gps_content':'The native trace names, owners and recorded details match the initialized public records.'}
