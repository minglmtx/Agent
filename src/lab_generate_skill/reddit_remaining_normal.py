"""Independent native Reddit completion families, with private references.

This reader only observes the pages actually visited. It never navigates, fills
forms, injects Wiki content or changes an actor decision. Completed controls do
not themselves admit training tasks; original and explicit derived goals remain
separate. References and expected answers must never enter actor/teacher input.
"""
from collections import Counter
from datetime import datetime
import json,re
from urllib.parse import parse_qs,quote,unquote,urlsplit
from zoneinfo import ZoneInfo
from .reddit_search import search_checks,read_search_page
from .reddit_forum_list import read_forum_list,forum_list_checks
from .site_navigation_rules import valid_initial_page

VERSION='reddit-remaining-native-normal-v1'
READ=r'''() => {
 const visible=e=>{if(!e||!e.getClientRects().length)return false;for(let n=e;n;n=n.parentElement){const s=getComputedStyle(n);if(s.display==='none'||s.visibility==='hidden'||s.visibility==='collapse'||Number(s.opacity)===0)return false;}return true;};
 const own=(e,s)=>[...e.querySelectorAll(s)].filter(n=>n.closest('article')===e);
 const root=document.getElementById('main');
 const sidebars=[...document.querySelectorAll('.sidebar__section')].filter(visible).map(e=>({headings:[...e.querySelectorAll('h1,h2')].filter(visible).map(h=>h.innerText.trim()),paragraphs:[...e.querySelectorAll('p')].filter(visible).map(p=>p.innerText.trim())}));
 const submissions=root?[...root.querySelectorAll('article.submission')].map(e=>({ids:own(e,'[data-vote-route-value="submission_vote"]').map(f=>f.getAttribute('data-vote-id-value')),title:e.querySelector('.submission__title')?.innerText.trim()||'',author:e.querySelector('.submission__submitter')?.innerText.trim()||'',author_href:e.querySelector('.submission__submitter')?.href||'',time:e.querySelector('time.submission__timestamp')?.dateTime||'',time_title:e.querySelector('time.submission__timestamp')?.title||'',visible:visible(e)})):[];
 const comments=root?[...root.querySelectorAll('article.comment')].map(e=>{const body=own(e,'.comment__body')[0],author=own(e,'.comment__info a[href*="/user/"]')[0],time=own(e,'.comment__header time')[0];return {dom_id:e.id,ids:own(e,'[data-vote-route-value="comment_vote"]').map(f=>f.getAttribute('data-vote-id-value')),author:author?.innerText.trim()||'',author_href:author?.href||'',body:body?.innerText||'',body_visible:visible(body),time:time?.dateTime||'',time_title:time?.title||'',visible:visible(e),permalink:own(e,'a.comment__permalink').map(a=>a.href)};}):[];
 const scoped=root?[...root.querySelectorAll('article.submission,article.comment')].filter(visible).map(e=>({kind:e.classList.contains('submission')?'submission':'comment',id:e.classList.contains('submission')?e.querySelector('[data-vote-route-value="submission_vote"]')?.getAttribute('data-vote-id-value'):e.id.replace(/^comment_/,''),forum_paths:[...new Set(own(e,'a[href]').map(a=>new URL(a.href).pathname).filter(p=>/^\/f\/[^/]+(?:\/|$)/.test(p)))],links:own(e,'a[href]').filter(visible).map(a=>({href:a.href,text:a.innerText.trim()}))})):[];
 const fields=[...document.forms].filter(visible).map(f=>({action:new URL(f.action).pathname,fields:[...f.querySelectorAll('input,select,textarea')].filter(e=>visible(e)&&e.type!=='hidden'&&e.type!=='password'&&!/token|csrf|password|secret|session/i.test(e.name||'')).map(e=>({name:e.name,type:e.type,value:e.value}))}));
 return {version:'reddit-remaining-native-normal-v1',url:location.href,title:document.title,sidebars,submissions,comments,scoped,forms:fields,main_headings:root?[...root.querySelectorAll('h1,h2')].filter(e=>visible(e)&&!e.closest('article')).map(e=>e.innerText.trim()):[],more:root?[...root.querySelectorAll('a[href]')].filter(a=>visible(a)&&a.innerText.trim()==='More').map(a=>a.href):[],empty_notice:root?(/There's nothing here|There are no entries to display/.test(root.innerText)):false};
}'''
CLICK=r'''(()=>{if(window.__labRedditUsernameVisitInstalled)return;window.__labRedditUsernameVisitInstalled=true;document.addEventListener('click',e=>{if(!e.isTrusted)return;const b=e.target instanceof Element?e.target.closest('[aria-haspopup]'):null;if(!b||!(b.tagName==='BUTTON'||b.getAttribute('role')==='button')||!['true','menu'].includes(b.getAttribute('aria-haspopup')))return;void window.__labRedditUsernameVisit({url:location.href,name:b.innerText.trim(),tag:b.tagName,popup:b.getAttribute('aria-haspopup'),trusted:true});},true);})();'''


class UsernameVisits:
    """Trusted public control activation, including the native BUTTON username."""
    def __init__(self,context):
        self.events=[];self.overflow=False
        context.expose_binding('__labRedditUsernameVisit',self.record);context.add_init_script(CLICK)
    def record(self,source,event):
        if source['frame']!=source['page'].main_frame:return
        if len(self.events)>=256:self.overflow=True
        else:self.events.append(event)
    def reset(self):self.events=[];self.overflow=False
    def snapshot(self):return {'version':VERSION,'events':list(self.events),'overflow':self.overflow}


def read_page(page,health):
    native=page.evaluate(READ)
    if native['url']!=health['url']:raise ValueError('Public native and health captures differ')
    result={'page':health,'native':native}
    path=urlsplit(page.url).path
    if path=='/search':
        state=read_search_page(page);state['empty_notice']=native['empty_notice'];result['search']=state
    if path=='/forums/all':result['forum_list']=read_forum_list(page)
    return result


def norm(value):
    if not isinstance(value,str):raise ValueError('Native text required')
    return ' '.join(value.split())


def _path(url,origin):
    u=urlsplit(url);base=urlsplit(origin)
    if(u.scheme,u.netloc)!=(base.scheme,base.netloc):raise ValueError('Observed URL leaves the local site')
    return unquote(u.path)+('?' +u.query if u.query else'')


def _profile(native,username):return [r for r in native['sidebars']if r['headings']==[username]]


def _datetime(value):
    if not isinstance(value,str):raise ValueError('Native timestamp string required')
    dt=datetime.fromisoformat(value.replace('Z','+00:00'))
    if dt.tzinfo is None:raise ValueError('Aware native timestamp required')
    return dt


def _id(value):
    if not isinstance(value,str)or not re.fullmatch('[1-9][0-9]*',value):raise ValueError('Exact native decimal identifier required')
    return int(value)


def _time(row,public,zone):
    if _datetime(row['timestamp'])!=_datetime(public['time']):return False
    m=re.fullmatch(r'([A-Za-z]+ \d{1,2}, \d{4}) at (\d{1,2}:\d{2}:\d{2} [AP]M) (\S+)',public['time_title'])
    if not m:return False
    local=_datetime(row['timestamp']).astimezone(ZoneInfo(zone))
    return datetime.strptime(m[1]+' '+m[2],'%B %d, %Y %I:%M:%S %p')==local.replace(tzinfo=None)and m[3]==local.tzname()


def _collection(observations,origin,path,kind,username):
    """Only genuine visited pagination can establish a complete user listing."""
    matching=[]
    for obs in observations:
        if not valid_initial_page(obs['page'],site_origin=origin):continue
        p=urlsplit(obs['page']['url'])
        if unquote(p.path)!=path:continue
        native=obs['native']
        if native['url']!=obs['page']['url']or len(_profile(native,username))!=1:raise ValueError('Native collection identity/capture differs')
        matching.append(obs)
    # Consecutive duplicate observations of the same page are harmless; a later
    # revisit is not another set of records and cannot manufacture completeness.
    pages=[];seen={}
    for obs in matching:
        key=_path(obs['page']['url'],origin)
        if key in seen:
            if seen[key]['native']!=obs['native']:raise ValueError('Same native listing page changed during read-only visit')
            continue
        seen[key]=obs;pages.append(obs)
    if not pages:return [],False
    if _path(pages[0]['page']['url'],origin)!=path:return [],False
    entries=[];ids=set()
    for number,obs in enumerate(pages):
        native=obs['native'];more=native['more']
        if not isinstance(more,list)or len(more)>1:raise ValueError('Native next page is missing or ambiguous')
        for row in native[kind]:
            if len(row['ids'])!=1:raise ValueError('Native listing entry identifier is ambiguous')
            ident=_id(row['ids'][0])
            if ident in ids:raise ValueError('Native pagination repeats an entry')
            ids.add(ident);entries.append(row)
        if number+1<len(pages):
            if len(more)!=1 or _path(more[0],origin)!=_path(pages[number+1]['page']['url'],origin):return entries,False
        elif more:return entries,False
    return entries,True


def _answer(answer):
    if isinstance(answer,str):
        try:return json.loads(answer)
        except ValueError:return answer
    return answer


def _search(spec,terminal,origin):
    if 'search'not in terminal:raise ValueError('Native search capture missing')
    private=spec['reference'];checks=search_checks({'query':spec['query'],'reference':private['search_rows'],'require_submission':spec.get('require_submission',False)},terminal['search'],terminal['page']['url'])
    if not all(checks.values()):return checks,[]
    scoped=terminal['native']['scoped'];keys=[(r['kind'],_id(r['id']))for r in scoped]
    expected=[(r['kind'],_id(r['id']))for r in terminal['search']['entries']]
    if keys!=expected:raise ValueError('Native scope and search collection differ')
    metadata={(r['kind'],r['id']):r for r in private['scope_rows']}
    proven=[]
    for public,key in zip(scoped,keys):
        if key not in metadata:raise ValueError('Independent native result scope missing')
        row=metadata[key];prefix='/f/'+quote(row['forum'],safe='')
        paths=public['forum_paths']
        if not paths or any(not(p==prefix or p.startswith(prefix+'/'))for p in paths):
            checks['search_public_scope_identity']=False;return checks,[]
        proven.append((public,row))
    checks['search_public_scope_identity']=True
    return checks,proven


def checks(spec,observations,*,site_origin,answer=None,username_visits=None):
    if not isinstance(observations,list)or not observations:raise ValueError('Actual visited page sequence required')
    for obs in observations:
        if not isinstance(obs,dict)or not isinstance(obs.get('page'),dict)or not isinstance(obs.get('native'),dict)or obs['native'].get('version')!=VERSION or obs['native'].get('url')!=obs['page'].get('url'):raise ValueError('Native visit capture missing or mismatched')
    terminal=observations[-1];health=terminal['page'];native=terminal['native'];kind=spec['kind'];ref=spec['reference']
    result={'terminal_page_valid':valid_initial_page(health,site_origin=site_origin)}
    if not result['terminal_page_valid']:return result
    path=urlsplit(health['url']).path;username=ref.get('username');prefix='/user/'+quote(username,safe='')if username else None
    if kind in('user_submissions','dated_comments'):
        field='submissions'if kind=='user_submissions'else'comments';route=prefix+'/'+field
        rows,complete=_collection(observations,site_origin,route,field,username)
        result['complete_native_listing_visited']=complete
        result['terminal_requested_user']=path==route and len(_profile(native,username))==1
        expected=[r for r in ref['rows']if r['visibility']=='visible'and(kind!='dated_comments'or r['submission_visibility']=='visible')]
        if kind=='dated_comments':
            expected=[r for r in expected if _datetime(r['timestamp']).astimezone(ZoneInfo(ref['timezone'])).date().isoformat()==spec['day']]
            rows=[r for r in rows if _datetime(r['time']).astimezone(ZoneInfo(ref['timezone'])).date().isoformat()==spec['day']]
        actual=[_id(r['ids'][0])for r in rows];by_id={r['id']:r for r in expected}
        result['complete_requested_record_set']=len(actual)==len(set(actual))==len(by_id)and set(actual)==set(by_id)
        values=True
        for ident,row in zip(actual,rows):
            if ident not in by_id:values=False;continue
            expected_row=by_id[ident];values=values and row['visible']is True and row['author']==username and _path(row['author_href'],site_origin)==prefix and _time(expected_row,row,ref['timezone'])
            if kind=='user_submissions':values=values and norm(row['title'])==norm(expected_row['title'])
            else:
                permalink='/f/'+quote(expected_row['forum'],safe='')+'/'+str(expected_row['submission_id'])+'/-/comment/'+str(ident)
                values=values and row['body_visible']is True and row['dom_id']=='comment_'+str(ident)and norm(row['body'])==norm(expected_row['body'])and len(row['permalink'])==1 and _path(row['permalink'][0],site_origin).split('#')[0]==permalink
        result['independent_native_fields']=bool(values)
        if kind=='user_submissions':result['native_content_or_empty_state']=bool(rows)if expected else native.get('empty_notice')is True
        if kind=='dated_comments':
            answer=_answer(answer);wanted=Counter((norm(r['body']),_datetime(r['timestamp']))for r in expected)
            result['complete_extracted_details']=isinstance(answer,list)and len(answer)==len(expected)and all(isinstance(r,dict)and set(r)=={'body','timestamp'}for r in answer)
            if result['complete_extracted_details']:
                try:result['complete_extracted_details']=Counter((norm(r['body']),_datetime(r['timestamp']))for r in answer)==wanted
                except(ValueError,TypeError,KeyError):result['complete_extracted_details']=False
    elif kind in('profile_settings','username_settings'):
        surfaces=set();forms_by_surface={}
        for obs in observations:
            if not valid_initial_page(obs['page'],site_origin=site_origin):continue
            p=urlsplit(obs['page']['url']).path;n=obs['native']
            if p==prefix and len(_profile(n,username))==1:
                card=_profile(n,username)[0];bio=ref.get('biography')
                if not bio or norm(bio)in[norm(x)for x in card['paragraphs']]:surfaces.add('profile')
            for suffix,label,heading in [('account','account','Editing user '+username),('preferences','preferences','Editing user settings for '+username)]:
                if p==prefix+'/'+suffix and n['main_headings']==[heading]:
                    fs=[f for f in n['forms']if f['action']==p];fields=[f for form in fs for f in form['fields']]
                    if label=='account':valid=any(f['name']=='user[username]'and f['value']==username for f in fields)
                    else:valid=any(f['name']=='user_settings[timezone]'and f['value']==ref['timezone']for f in fields)and any(f['name']=='user_settings[locale]'for f in fields)
                    if valid:surfaces.add(label);forms_by_surface[label]=fields
        result['requested_native_settings_visited']=bool({'account','preferences'}&surfaces)
        result['terminal_requested_account_surface']=path in(prefix,prefix+'/account',prefix+'/preferences')
        if kind=='profile_settings':result['requested_profile_visited']='profile'in surfaces
        else:
            if not isinstance(username_visits,dict)or username_visits.get('version')!=VERSION or username_visits.get('overflow')is not False or not isinstance(username_visits.get('events'),list):raise ValueError('Trusted username activation capture missing')
            result['native_username_control_clicked']=any(e.get('trusted')is True and e.get('name')==username and e.get('tag')in('BUTTON','A')and e.get('popup')in('true','menu')and _path(e['url'],site_origin).startswith('/')for e in username_visits['events'])
    elif kind=='wiki_directory':
        result['native_wiki_directory']=path=='/wiki/_all'and native['main_headings']==['All pages']and health['title']=='All pages'
        # An empty native Wiki directory satisfies only a navigation goal.
    elif kind=='public_imported_identifier':
        cards=_profile(native,username);public=[norm(p)for card in cards for p in card['paragraphs']if re.fullmatch(r't2_[a-z0-9]+',norm(p))]
        result['requested_native_profile']=path==prefix and len(cards)==1
        result['one_public_imported_identifier']=len(public)==1 and public==[ref['public_identifier']]
        result['exact_identifier_answer']=_answer(answer)==ref['public_identifier']
    elif kind=='forum_name_search':
        if 'forum_list'not in terminal:return result|{'complete_native_forum_directory':False}
        result.update(forum_list_checks({'sort':'name','reference':ref['forum_reference']},terminal['forum_list'],health['url']))
        matched=[r['name']for r in ref['forum_reference']['rows']if spec['term'].casefold()in r['name'].casefold()];reply=_answer(answer)
        result['matching_forum_names']=bool(matched)and isinstance(reply,list)and all(isinstance(x,str)for x in reply)and len(reply)==len(set(reply))and(set(reply)==set(matched)if spec['all_matches']else len(reply)==1 and reply[0]in matched)
    elif kind in('native_search','search_scope_count','search_scope_posts','search_scope_all_posts'):
        if path!='/search':return result|{'native_search_page':False}
        search,proven=_search(spec,terminal,site_origin);result.update(search)
        if not all(search.values()):return result
        if kind=='search_scope_count':
            # Both native result types count; comments are not silently dropped.
            wanted=sum(row['forum']==spec['forum']for _,row in proven);reply=_answer(answer)
            result['exact_native_result_count']=type(reply)is int and reply==wanted
        elif kind in('search_scope_posts','search_scope_all_posts'):
            matches=[(p,row)for p,row in proven if row['kind']=='submission'and row['forum']==spec['forum']]
            reply=_answer(answer);allowed={row['id']for _,row in matches}
            valid_reply=isinstance(reply,list)and all(type(i)is int and i>0 for i in reply)and len(reply)==len(set(reply))
            result['requested_forum_posts_identified']=bool(allowed)and valid_reply and bool(reply)and set(reply)<=allowed
            if kind=='search_scope_all_posts':
                # The repository hard limit is 50. Never assert a truncated top
                # list is the full requested set; a complete native reference
                # and public result list must both be at most this limit.
                result['native_search_not_truncated']=len(ref['search_rows'])<=50
                result['all_requested_forum_posts']=valid_reply and set(reply)==allowed
    else:raise ValueError('Unsupported native remaining task family')
    return result


def evaluate(spec,observations,*,site_origin,answer=None,username_visits=None):
    try:found=checks(spec,observations,site_origin=site_origin,answer=answer,username_visits=username_visits)
    except(ValueError,TypeError,KeyError,AttributeError)as exc:return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':'Native capture/reference incomplete: '+str(exc)}
    ok=all(found.values());return {'version':VERSION,'status':'success'if ok else'failure','reward':1. if ok else 0.,'checks':found}


FEEDBACK={
 'complete_native_listing_visited':'The requested account listing was visited through its native final page.',
 'complete_requested_record_set':'All records requested by the task are present.',
 'independent_native_fields':'The displayed record fields agree with their actual native objects.',
 'complete_extracted_details':'The answer contains the requested complete details.',
 'requested_profile_visited':'The requested profile was visited.',
 'requested_native_settings_visited':'The requested account settings were visited.',
 'native_username_control_clicked':'The native username control was activated.',
 'exact_native_result_count':'The answer matches the requested native result count.',
 'requested_forum_posts_identified':'The identified posts belong to the requested forum and search.',
 'native_search_not_truncated':'The native search result set is complete for this task.',
 'all_requested_forum_posts':'All requested matching forum posts are identified.',
}


def public_feedback(judgment):
    """Enum/boolean posterior facts only; no private reference or answer value."""
    if not isinstance(judgment,dict)or judgment.get('status')not in('success','failure','unknown')or not isinstance(judgment.get('checks'),dict):raise ValueError('Recorded native judgment required')
    from .reddit_search import FEEDBACK as search_feedback
    messages=search_feedback|FEEDBACK
    facts=[]
    for name,value in judgment['checks'].items():
        if not isinstance(name,str)or type(value)is not bool:raise ValueError('Boolean native completion fact required')
        facts.append({'check':name,'passed':value,'criterion':messages.get(name,'The recorded native state satisfies this required completion condition.')})
    return {'version':VERSION,'status':judgment['status'],'reward':judgment['reward'],'checks':facts}
