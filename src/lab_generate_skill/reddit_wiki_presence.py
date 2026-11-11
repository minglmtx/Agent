"""Wiki existence from stored resources and independently rendered native pages."""
from urllib.parse import urlsplit
from .site_database import select_rows
from .site_start_state import valid_task_start,local_link_paths
from .browser_http_status import native_document_status,is_error_document


def validate(q):
    if (q.get('family')!='reddit_wiki_presence' or q.get('kind')not in ('main','any')
            or q.get('fields')!={'exists':'string'} or q.get('answer_labels')!={'exists':['yes','no']}
            or q.get('reference_path')!=('/wiki'if q['kind']=='main'else '/wiki/_all')):
        raise ValueError('Unsupported wiki existence query')


def reference(site,q):
    validate(q)
    rows=select_rows(site,'SELECT id,path,normalized_path FROM wiki_pages ORDER BY id')
    if len({r['normalized_path']for r in rows})!=len(rows):raise ValueError('Ambiguous normalized wiki identities')
    exists=bool(rows)if q['kind']=='any'else any(r['normalized_path']=='index'for r in rows)
    return {'object_id':'reddit-wiki-presence:'+q['kind'],'values':{'exists':'yes'if exists else 'no'},'source_state':rows}


def ui_values(page,q):
    validate(q);u=urlsplit(page.url)
    if u.path!=q['reference_path']or u.query:raise ValueError('Wrong wiki query page')
    status=native_document_status(page,None)
    if q['kind']=='main' and status==404:
        policy={'kind':'native_missing_resource','path':'/wiki','required_link_path':'/wiki/_create/index'}
        health={'url':page.url,'http_status':status,'login_page':False,
            'error_page':is_error_document(page.url,status,page.title()),'local_link_paths':local_link_paths(page,u.scheme+'://'+u.netloc)}
        if not valid_task_start({'initial_page_policy':policy},health,site_origin=u.scheme+'://'+u.netloc):
            raise ValueError('Missing wiki has no native creation entry')
        return {'exists':'no'}
    if status!=200 or is_error_document(page.url,status,page.title()):raise ValueError('Wiki document unavailable')
    main=page.locator('#main');main.wait_for(state='visible',timeout=10000)
    if q['kind']=='main':
        # A native resource response at the canonical index URI, not a redirect
        # to a login, creation form, or directory page.
        if not page.locator('h1:visible').count():raise ValueError('Missing wiki resource heading')
        return {'exists':'yes'}
    if not any(h.strip()=='All pages'for h in main.locator('h1').all_text_contents()):
        raise ValueError('Wrong native wiki directory')
    links=main.locator('a[href]:visible').evaluate_all('es=>es.map(e=>e.href)')
    resources=[v for v in links if urlsplit(v).netloc==u.netloc and urlsplit(v).path.startswith('/wiki/')
               and not urlsplit(v).path.startswith('/wiki/_')]
    empty='There are no entries to display.'in main.inner_text()
    if bool(resources)==empty:raise ValueError('Wiki entries and empty-state notice are missing or contradictory')
    return {'exists':'yes'if resources else 'no'}
