"""Read-only completion checks for explicitly versioned local community tasks."""
import re
from urllib.parse import urlsplit,urljoin,unquote
from .map_community_fixture import VERSION,records
from .document_sections import digest
from .document_observation import request_exposure


def validate(spec):
    rows=spec.get('entries')
    if type(spec.get('allow_entry_page',False))is not bool:
        raise ValueError('Diary detail-page policy must be explicit boolean')
    if spec.get('fixture_version')!=VERSION or not isinstance(rows,list)or not rows:
        raise ValueError('Explicit populated diary reference required')
    if any(not isinstance(r,dict) or type(r.get('id'))is not int or r['id']<=0
           or any(not isinstance(r.get(k),str)or not r[k].strip()for k in ('title','author','body_sha256'))
           or not re.fullmatch(r'[0-9a-f]{64}',r['body_sha256'])for r in rows):
        raise ValueError('Incomplete diary identity/content reference')
    if len({r['id']for r in rows})!=len(rows):raise ValueError('Duplicate diary reference')
    return rows


def verify_reference(site,spec):
    expected=validate(spec)
    if getattr(site,'community_fixture',None)!=VERSION:raise ValueError('Wrong community environment profile')
    rows=records(site)['entries']or []
    actual=[{'id':r['id'],'title':r['title'],'author':r['display_name'],'body_sha256':digest(r['body'])}for r in rows if r['visible']]
    if sorted(actual,key=lambda r:r['id'])!=sorted(expected,key=lambda r:r['id']):
        raise ValueError('Native diary records differ from fixed initialization')


READ=r'''() => {
 const visible=e=>!!e&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 const inView=e=>{if(!visible(e))return false;const r=e.getBoundingClientRect();return r.top>=0&&r.bottom<=innerHeight&&r.left>=0&&r.right<=innerWidth;};
 return {url:location.href,headings:[...document.querySelectorAll('h1,h2')].filter(visible).map(e=>e.innerText.trim()),
   entries:[...document.querySelectorAll('.diary_post')].filter(visible).map(e=>{
     const h=e.querySelector('h2'),a=h?.querySelector('a[href]'),b=e.querySelector('.richtext');
     return {title:visible(h)?h.innerText.trim():'',href:a?.getAttribute('href')||'',
       body:visible(b)?b.innerText.trim():'',body_in_view:inView(b)};
   })};
}'''


def read_diary_page(page):return page.evaluate(READ)


def diary_checks(spec,state):
    expected=validate(spec)
    if not isinstance(state,dict)or not isinstance(state.get('entries'),list)or not isinstance(state.get('url'),str):
        raise ValueError('Missing native diary capture')
    current=unquote(urlsplit(state['url']).path).rstrip('/')
    list_page=current=='/diary' and "Users' Diaries"in state.get('headings',[])
    detail=[r for r in expected if current=='/user/'+r['author']+'/diary/'+str(r['id'])]
    detail_page=spec.get('allow_entry_page',False)and len(detail)==1 and detail[0]['title']in state.get('headings',[])
    if detail_page:expected=detail
    out={'populated_diary_identity':bool(list_page or detail_page),
         'requested_diary_content':True,'requested_diary_observed':True}
    if len(state['entries'])!=len(expected):out['requested_diary_content']=False
    for ref in expected:
        path='/user/'+ref['author']+'/diary/'+str(ref['id'])
        def matches_identity(row):
            if not isinstance(row,dict)or not isinstance(row.get('href'),str):
                raise ValueError('Malformed diary entry link')
            link=urlsplit(urljoin(state['url'],row['href']));origin=urlsplit(state['url'])
            return (link.scheme,link.netloc)==(origin.scheme,origin.netloc)and unquote(link.path)==path and not link.query and not link.fragment
        matches=[r for r in state['entries']if matches_identity(r)]
        if len(matches)!=1:
            out['requested_diary_content']=False;out['requested_diary_observed']=False;continue
        r=matches[0]
        if not isinstance(r.get('body'),str)or type(r.get('body_in_view'))is not bool:raise ValueError('Malformed diary capture')
        out['requested_diary_content'] &= r.get('title')==ref['title']and bool(r['body'])and digest(r['body'])==ref['body_sha256']
        exposed=r['body_in_view']
        if state.get('issued_section_request'):
            exposed|=request_exposure(state['issued_section_request'],terminal_url=state['url'],section={'heading':r['title'],'text':r['body']})['observed']
        out['requested_diary_observed'] &= exposed
    return out


FEEDBACK={'populated_diary_identity':'The requested native diary list or an admitted complete diary entry is open.',
          'requested_diary_content':'The requested diary entries contain their complete original initialized content.',
          'requested_diary_observed':'The diary bodies are visible or present in the actual selected observation.'}
