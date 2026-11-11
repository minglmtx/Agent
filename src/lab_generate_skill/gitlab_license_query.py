"""Scoped license queries: native repository reference and visible UI labels."""
import hashlib
import json
import re
from urllib.parse import urlsplit,urljoin,parse_qs
from .gitlab_collection_query import database_rows, page_key, public_project_paths

SOURCE='/opt/gitlab/embedded/service/gitlab-rails/app/models/repository.rb'
PREFIX='DIRECTORY_LICENSE_JSON='
ALL_START='/explore/projects?non_archived=true&sort=name_asc&page=1'


def validate(q):
    if (q.get('family')!='gitlab_directory_license'
            or q.get('fields')!={'projects':'record_set'}
            or q.get('record_fields')!={'projects':{'path':'string'}}):
        raise ValueError('Unsupported license answer schema')
    members=q.get('members')
    if not isinstance(members,list) or not members or any(not isinstance(p,str)or '/'not in p for p in members) or len(members)!=len(set(members)):
        raise ValueError('Fixed original project identities required')
    if not isinstance(q.get('reference_path'),str) or page_key(q['reference_path'])[0]!='/explore/projects':
        raise ValueError('Native Explore project directory required for visible licenses')
    if q.get('license_key') not in ('mit','apache-2.0') or q.get('license_name')!={'mit':'MIT License','apache-2.0':'Apache License 2.0'}[q['license_key']]:
        raise ValueError('Unsupported explicit license')
    if not re.fullmatch('[0-9a-f]{64}',q.get('repository_source_sha256','')):
        raise ValueError('Pinned native repository license implementation required')
    scope=q.get('scope','fixed_page')
    if scope not in ('fixed_page','all_accessible_non_archived'):
        raise ValueError('Unsupported license collection scope')
    if scope=='all_accessible_non_archived':
        if (q['reference_path']!=ALL_START or not isinstance(q.get('username'),str)or not q['username']
                or type(q.get('account_user_id'))is not int or q['account_user_id']<=0):
            raise ValueError('All-project license queries require a pinned account and unfiltered native directory')


def native_licenses(site, q):
    validate(q)
    if q.get('scope')=='all_accessible_non_archived':
        from .gitlab_directory import directory_access_reference,project_reference
        access=directory_access_reference(site,q['username'])
        allowed=set(access['project_ids'])
        expected={r['path']for r in project_reference(site)if not r['archived']and r['id']in allowed}
        if access['user']['id']!=q['account_user_id']or set(q['members'])!=expected:
            raise ValueError('All-project license scope does not match the complete accessible directory')
    source=site.command(['cat',SOURCE],capture_output=True,text=True,timeout=30).stdout
    if hashlib.sha256(source.encode()).hexdigest()!=q['repository_source_sha256']:
        raise ValueError('Native repository implementation changed')
    db={r['path']:r['id']for r in database_rows(site)}
    if not set(q['members'])<=db.keys():raise ValueError('Native project missing')
    ids=[int(db[p])for p in q['members']]
    ruby="""require 'json'
rows = Project.where(id: IDS).order(:id).map do |p|
  l = p.repository.license
  {id: p.id, path: p.full_path, license: l ? {key: l.key, name: l.name} : nil}
end
puts 'DIRECTORY_LICENSE_JSON=' + JSON.generate(rows)
""".replace('IDS',json.dumps(ids))
    # Explicit environment load works in the pinned Omnibus installation;
    # the earlier `rails runner` probe did not return a structured result.
    output=site.command(['bash','/state/service.sh','gitlab-rails','/usr/bin/env','RAILS_ENV=production',
        '/opt/gitlab/embedded/bin/bundle','exec','ruby',
        '-r','/opt/gitlab/embedded/service/gitlab-rails/config/environment','-e',ruby],
        capture_output=True,text=True,timeout=240).stdout
    lines=[s[len(PREFIX):]for s in output.splitlines()if s.startswith(PREFIX)]
    if len(lines)!=1:raise ValueError('Native license reference unavailable')
    rows=json.loads(lines[0])
    if len(rows)!=len(ids) or {r['id']for r in rows}!=set(ids) or {r['path']for r in rows}!=set(q['members']):
        raise ValueError('Native license project identities changed')
    for r in rows:
        if db[r['path']]!=r['id'] or (r['license'] is not None and (set(r['license'])!={'key','name'} or not all(isinstance(v,str)and v for v in r['license'].values()))):
            raise ValueError('Malformed native license reference')
    return rows


def reference(site,q):
    rows=native_licenses(site,q)
    return {'object_id':'gitlab-license:'+q['reference_path'],
        'values':{'projects':[{'path':r['path']}for r in rows if (r['license']or{}).get('key')==q['license_key']]},
        'source_rows':rows}


def ui_values(page,q):
    validate(q)
    if q.get('scope')=='all_accessible_non_archived':
        return complete_ui_values(page,q)
    if page_key(page.url)!=page_key(q['reference_path']) or public_project_paths(page)!=q['members']:
        raise ValueError('Original license page membership changed')
    return license_labels(page,q['members'],q['license_name'])


def license_labels(page,members,license_name):
    labels=page.locator('.project-row').evaluate_all('''es=>es.map(e=>{
      const icons=[...e.querySelectorAll('[data-testid="scale-icon"]')];
      return icons.map(n=>({text:n.parentElement.innerText.trim(),visible:!!n.parentElement.getClientRects().length}));
    })''')
    if len(labels)!=len(members) or any(len(ls)>1 or (ls and (not ls[0]['visible']or not ls[0]['text']))for ls in labels):
        raise ValueError('Ambiguous or hidden native license label')
    return {'projects':[{'path':p}for p,ls in zip(members,labels)if ls and ls[0]['text']==license_name]}


def complete_ui_values(page,q):
    """Evaluator-private observability proof; leaves the caller's page untouched.

Follow native Next links rather than manufacturing unseen pages. Require the
whole pinned collection, not just all matching rows on the first page. Never
pass this traversal or its reference membership to the actor.
    """
    from .browser_page_wait import settle_gitlab_capture
    validate(q)
    if q.get('scope')!='all_accessible_non_archived':raise ValueError('Complete directory scope required')
    if page_key(page.url)!=page_key(ALL_START):raise ValueError('Wrong complete license directory start')
    origin=urlsplit(page.url);target=page.url;members=[];matches=[];seen=set()
    reader=page.context.new_page()
    try:
        for number in range(1,51):
            u=urlsplit(target);params=parse_qs(u.query,keep_blank_values=True)
            if (u.scheme!=origin.scheme or u.netloc!=origin.netloc or u.path!='/explore/projects'or u.fragment
                or params!={'non_archived':['true'],'sort':['name_asc'],'page':[str(number)]}or target in seen):
                raise ValueError('Native license pagination changed scope or repeated a page')
            seen.add(target)
            response=reader.goto(target,wait_until='domcontentloaded',timeout=60000)
            if not response or response.status!=200 or reader.url!=target:
                raise ValueError('Native license directory unavailable or redirected')
            settle_gitlab_capture(reader)
            if reader.evaluate('() => window.gon?.current_user_id')!=q['account_user_id']:
                raise ValueError('Native license account changed')
            current=public_project_paths(reader)
            members+=current;matches+=license_labels(reader,current,q['license_name'])['projects']
            if len(members)!=len(set(members))or not set(members)<=set(q['members']):
                raise ValueError('Native license page contains duplicate or unexpected projects')
            nexts=list(dict.fromkeys(reader.locator('a[rel=next]').evaluate_all(
                'es=>es.filter(e=>e.getClientRects().length).map(e=>e.getAttribute("href"))')))
            if len(nexts)>1:raise ValueError('Ambiguous native next page')
            if not nexts:
                if set(members)!=set(q['members']):raise ValueError('Incomplete native license collection')
                return {'projects':matches}
            target=urljoin(target,nexts[0])
        raise ValueError('Unbounded native license pagination')
    finally:
        reader.close()
