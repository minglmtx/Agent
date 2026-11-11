"""Native forum directory ordering and contents, independently checked at finish."""
import re
from urllib.parse import urlsplit,parse_qs,unquote
from .site_database import select_rows

ORDERS={'name':'normalized_name ASC','title':'LOWER(title) ASC, normalized_name ASC',
        'creation_date':'created DESC, normalized_name ASC'}


BROWSE_ORDERS=tuple(ORDERS)+('submissions','subscribers')


def accepted_orders(spec):
    """Keep explicit sort goals exact; free-choice goals carry a fixed baseline."""
    if spec.get('mode')=='browse':
        if set(spec)!={'mode','reference'}:
            raise ValueError('Browse directory must not impose a sort goal')
        return list(BROWSE_ORDERS)
    if 'mode'in spec:raise ValueError('Unsupported forum directory completion mode')
    choices=spec.get('sort_choices')
    if choices is None:
        if spec.get('sort') not in ORDERS:raise ValueError('Unsupported forum ordering')
        return [spec['sort']]
    if ('sort' in spec or spec.get('initial_sort')!='submissions'
            or not isinstance(choices,list) or len(choices)!=len(ORDERS)
            or set(choices)!=set(ORDERS)):
        raise ValueError('Free forum ordering requires all supported alternatives to the original submissions default')
    return choices

def forum_reference(site, *, include_default_views=False):
    if site.domain!='reddit':raise ValueError('Forum reference requires Reddit')
    rows=select_rows(site,'SELECT id,name,normalized_name,title,created,description FROM forums ORDER BY id')
    orders={k:[r['name'] for r in select_rows(site,'SELECT name FROM forums ORDER BY '+v)] for k,v in ORDERS.items()}
    if include_default_views:
        # Match native ForumRepository::findForumsByPage exactly, including ties.
        for mode,table in [('submissions','submissions'),('subscribers','forum_subscriptions')]:
            sql=('SELECT f.name FROM forums f LEFT JOIN '+table+' s ON s.forum_id=f.id '
                 'GROUP BY f.id ORDER BY COUNT(s.id) DESC, f.normalized_name ASC')
            orders[mode]=[r['name']for r in select_rows(site,sql)]
    return {'rows':rows,'orders':orders}

def verify_forum_reference(site,spec):
    if forum_reference(site,include_default_views=spec.get('mode')=='browse')!=spec['reference']:raise RuntimeError('Forum directory differs from pinned reference')

def read_forum_list(page):
    return page.evaluate(r'''() => {
      const visible=e=>!!e.getClientRects().length;
      const root=document.querySelector('#main');
      const links=root?[...root.querySelectorAll('a[href^="/f/"]')].filter(e=>visible(e) && /^\/f\/[^/]+$/.test(new URL(e.href).pathname)):[];
      return {
        entries:links.map(e=>({path:new URL(e.href).pathname,label:e.innerText.trim().replace(/\s+/g,' '),
          group:e.closest('.text-flow')?.querySelector('h2')?.innerText.trim()||null})),
        active_tabs:root?[...root.querySelectorAll('a.tab--active')].filter(visible).map(e=>e.innerText.trim()):[],
        sort_labels:root?[...root.querySelectorAll('button.tab.dropdown__toggle')].filter(visible).map(e=>e.innerText.trim()):[]
      };
    }''')

def forum_list_checks(spec,state,url):
    if not isinstance(state,dict) or any(not isinstance(state.get(k),list) for k in ('entries','active_tabs','sort_labels')):
        raise ValueError('Missing native forum directory capture')
    choices=accepted_orders(spec)
    ref=spec['reference'];known={r['name']:r for r in ref['rows']}
    if len(known)!=len(ref['rows']) or set(ref['orders'])!=set(BROWSE_ORDERS if spec.get('mode')=='browse'else ORDERS):raise ValueError('Invalid forum reference')
    parts=urlsplit(url);path=unquote(parts.path).rstrip('/');alphabetical=path=='/forums/all'
    match=re.fullmatch(r'/forums/by_(name|title|creation_date)(?:/([1-9][0-9]*))?',path)
    if spec.get('mode')=='browse':
        match=re.fullmatch(r'/forums/by_(name|title|creation_date|submissions|subscribers)(?:/([1-9][0-9]*))?',path)
        default=re.fullmatch(r'/forums(?:/([1-9][0-9]*))?',path)
    else:default=None
    mode='name' if alphabetical else (match[1] if match else 'submissions'if default else None)
    if mode not in choices:return {'forum_sort_selected':False}
    requested=mode
    number=int(match[2] or 1) if match else int(default[1]or 1)if default else 1
    expected=ref['orders'][requested]
    if set(expected)!=set(known) or len(expected)!=len(known):raise ValueError('Incomplete forum ordering reference')
    checks={'forum_sort_selected':mode==requested and not any(parse_qs(parts.query,keep_blank_values=True).values()),
            'forum_directory_controls':state['active_tabs']==(['Alphabetical'] if alphabetical else ['Forums']) and
                (state['sort_labels']==[] if alphabetical else state['sort_labels']==[{'name':'Name','title':'Title','creation_date':'Creation date','submissions':'Submissions','subscribers':'Subscribers'}[requested]])}
    if alphabetical:
        # The native alphabetical template groups 0..9, A..Z and underscore;
        # reference order within each group is PostgreSQL normalized_name.
        expected=[name for symbol in '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_' for name in expected if name.upper().startswith(symbol)]
    else:expected=expected[(number-1)*25:number*25]
    entries=state['entries'];names=[unquote(x['path']).removeprefix('/f/') for x in entries]
    checks['forum_list_contents']=bool(expected) and names==expected and len(names)==len(set(names))
    checks['forum_visible_labels']=all(name in known and entry['label']==(name if alphabetical else '/f/'+name+' '+known[name]['title']) for name,entry in zip(names,entries))
    if alphabetical:checks['forum_alphabetical_groups']=all(entry['group']==name[0].upper() for name,entry in zip(names,entries))
    return checks

FEEDBACK={
 'forum_sort_selected':'The requested forum ordering is selected.',
 'forum_directory_controls':'The native directory controls show the requested view and sort mode.',
 'forum_list_contents':'The visible forum entries match the requested ordering and page.',
 'forum_visible_labels':'The displayed names and titles identify the actual forum records.',
 'forum_alphabetical_groups':'Forum names appear in their correct alphabetical sections.'}
