"""Account-scoped query references, independently checked against native GitLab UI."""
import re
from .site_database import select_rows


def one(rows):
    if len(rows)!=1:raise ValueError('GitLab reference absent or ambiguous')
    return rows[0]


def reference(site,q):
    ident=q['object_id'];username=q['username'];fields=q['fields']
    if type(ident) is not int or ident<=0 or not isinstance(username,str):raise ValueError('Invalid account identity')
    user=one(select_rows(site,f'SELECT id,username FROM users WHERE id={ident}'))
    if user['username']!=username:raise ValueError('GitLab account identity changed')
    if q['family']=='gitlab_starred_projects':
        if fields!={'items':'record_set'} or q.get('record_fields')!={'items':{'name':'string'}}:
            raise ValueError('Unsupported starred-project answer schema')
        rows=select_rows(site,f"SELECT p.id,p.name,r.path FROM users_star_projects s JOIN projects p ON p.id=s.project_id JOIN routes r ON r.source_id=p.id AND r.source_type='Project' WHERE s.user_id={ident} ORDER BY p.id")
        if any(not isinstance(r['name'],str) or not r['name'].strip() or '/' in r['name'] for r in rows):
            raise ValueError('Native project name requires a different unambiguous display adapter')
        return {'object_id':'gitlab_starred_projects:'+str(ident),
                'values':{'items':[{'name':r['name']} for r in rows]},'source_state':rows}
    if q['family']=='gitlab_todo':
        from .gitlab_todo_rules import todo_state,display_text
        initial=todo_state(site,username)
        pool=[r for r in initial['items'] if r['state']==q['state']]
        if q.get('project_path'):pool=[r for r in pool if r['project_path']==q['project_path']]
        if q.get('target_title'):pool=[r for r in pool if display_text(r['title'])==display_text(q['target_title'])]
        values={}
        for key,kind in fields.items():
            if key=='todo_count':values[key]=len(pool)
            elif key=='oldest_todo_title':
                if not pool:raise ValueError('No to-dos in requested collection')
                earliest=min(r['created_at'] for r in pool)
                values[key]=sorted({display_text(r['title']) for r in pool if r['created_at']==earliest})
            elif key=='assigned_by':
                authors={r['author_name'] for r in pool if r['action']==1}
                if len(authors)!=1:raise ValueError('Requested to-do author missing or ambiguous')
                values[key]=next(iter(authors))
            else:raise ValueError('Unsupported to-do query')
        return {'object_id':'gitlab_todo:'+str(ident),'values':values,'source_state':initial}
    state={};values={}
    for key in fields:
        if key=='starred_project_count':
            rows=select_rows(site,f'SELECT project_id FROM users_star_projects WHERE user_id={ident} ORDER BY project_id')
        elif key in ('pending_todo_count','completed_todo_count'):
            status='pending' if key=='pending_todo_count' else 'done'
            rows=select_rows(site,f"SELECT id,project_id,target_type,target_id FROM todos WHERE user_id={ident} AND state='{status}' ORDER BY id")
        else:raise ValueError('Unsupported account query')
        values[key]=len(rows);state[key]=rows
    return {'object_id':'gitlab_account:'+str(ident),'values':values,'source_state':state}


def tab_count(page,label):
    pattern=r'^'+re.escape(label)+r'\s+([\d,]+)$'
    # Native counts load asynchronously; wait for this field, not a fixed sleep.
    page.wait_for_function("pattern => Array.from(document.querySelectorAll('.nav-link')).some(e=>new RegExp(pattern).test(e.innerText.trim()))",arg=pattern,timeout=15000)
    matches=[re.fullmatch(pattern,text.strip()) for text in page.locator('.nav-link').all_inner_texts()]
    values=[int(m.group(1).replace(',','')) for m in matches if m]
    if len(values)!=1:raise ValueError('GitLab count tab missing or ambiguous')
    return values[0]


def ui_values(page,q):
    actual=page.evaluate('() => window.gon && window.gon.current_user_id')
    if actual!=q['object_id']:raise ValueError('Rendered GitLab account identity mismatch')
    if q['family']=='gitlab_starred_projects':
        from urllib.parse import urlsplit,parse_qs
        u=urlsplit(page.url);params=parse_qs(u.query)
        if u.path.rstrip('/')!='/dashboard/projects/starred' or any(k not in ('page','sort') for k in params):
            raise ValueError('Wrong or filtered starred-project collection')
        count=tab_count(page,'Starred')
        seen=set();rows=[];visited=set()
        while True:
            if page.url in visited:raise ValueError('Starred-project pagination cycle')
            visited.add(page.url)
            # a.project is the avatar link in the pinned GitLab snapshot. Its
            # visible text can be just an initial. Read the corresponding
            # visible heading link, with the avatar URL as an identity check.
            native=page.locator('.project-row').evaluate_all(r'''es=>es.filter(e=>!!e.getClientRects().length).map(e=>{
                const avatar=e.querySelector('a.project[href]');
                const path=avatar?new URL(avatar.href,location.href).pathname:null;
                const headings=[...e.querySelectorAll('h1 a[href],h2 a[href],h3 a[href],h4 a[href],h5 a[href],h6 a[href],[role=heading] a[href]')]
                  .filter(a=>!!a.getClientRects().length&&getComputedStyle(a).visibility!=='hidden'&&new URL(a.href,location.href).pathname===path);
                return {path,text:headings.length===1?headings[0].innerText.trim().replace(/\s+/g,' '):null};
            })''')
            for row in native:
                if not row['path'] or not isinstance(row['text'],str):raise ValueError('Missing or ambiguous visible project heading')
                if row['path'] in seen:raise ValueError('Duplicate native project row')
                seen.add(row['path']);name=row['text'].rsplit('/',1)[-1].strip()
                if not name:raise ValueError('Missing rendered project name')
                rows.append({'name':name})
            next_link=page.locator('a[rel=next]')
            if not next_link.count():break
            if next_link.count()!=1 or len(visited)>100:raise ValueError('Ambiguous pagination')
            target=next_link.get_attribute('href');next_url=urlsplit(target)
            if next_url.path.rstrip('/')!='/dashboard/projects/starred':raise ValueError('Pagination changed collection')
            next_link.click();page.wait_for_load_state('domcontentloaded')
        if len(rows)!=count:raise ValueError('Incomplete starred-project directory')
        return {'items':rows}
    if q['family']=='gitlab_todo':
        from urllib.parse import urlsplit,parse_qs
        from .gitlab_todo_rules import display_text
        parsed=urlsplit(page.url)
        if parsed.path!='/dashboard/todos' or parse_qs(parsed.query).get('state',['pending'])!=[q['state']]:raise ValueError('Wrong to-do collection page')
        rows=page.locator('li.todo').evaluate_all("es=>es.filter(e=>e.getClientRects().length).map(e=>({title:e.querySelector('.todo-target-title')?.innerText.trim().replace(/\\s*·\\s*$/,''),time:e.querySelector('time')?.getAttribute('datetime'),author:e.querySelector('.author-name a')?.getAttribute('title'),path:e.querySelector('a.todo-target-link')?.getAttribute('href')}))")
        # CPU proof uses the native full collection (seven stored rows here),
        # independently verifies its visible titles/identities against the DB.
        values={}
        if q.get('project_path'):rows=[r for r in rows if (r['path'] or '').startswith('/'+q['project_path']+'/-/')]
        if q.get('target_title'):rows=[r for r in rows if display_text(r['title'])==display_text(q['target_title'])]
        for key in q['fields']:
            if key=='todo_count':values[key]=len(rows)
            elif key=='oldest_todo_title':
                if not rows or any(not r['time'] for r in rows):raise ValueError('Missing to-do timestamp')
                oldest=min(r['time'] for r in rows);values[key]=sorted({display_text(r['title']) for r in rows if r['time']==oldest})[0]
            elif key=='assigned_by':
                # q specifies a pending assignment, never the duplicate Done entry.
                if len(rows)!=1:raise ValueError('Rendered assignment missing or ambiguous')
                author=rows[0]['author']
                if author=='You':raise ValueError('Self-author display requires an independently verified visible account name')
                values[key]=author
        return values
    labels={'starred_project_count':'Starred','pending_todo_count':'To Do','completed_todo_count':'Done'}
    return {key:tab_count(page,labels[key]) for key in q['fields']}
