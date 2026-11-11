"""Private native subscription checks shared by Atom and upcoming calendars.

Public scope comes only from the declared task. Native references and saved
client bytes are evaluator-only and never become actor observations or tools.
"""
from pathlib import Path
from urllib.parse import urlencode
import json,re,shutil,subprocess,tempfile,time
from .source_revision_binding import binding
from .gitlab_feed_scope import native_subscription_query
from .gitlab_feed_reference import inspect_atom_reference, inspect_calendar_reference
from .io_utils import atomic_write_json


def feed_spec(contract):
    binding(contract)
    if contract.get('domain') != 'gitlab' or contract.get('original_benchmark_equivalence') is not False:
        raise ValueError('Explicit native local-client adaptation required')
    p = contract['public_parameters']; kind = p.get('kind'); count = p.get('required_successful_fetches')
    if (contract.get('family') != 'gitlab_local_artifact.'+str(kind) or kind not in ('atom','calendar')
            or p.get('client') != 'attempt_local_persisted_subscription' or p.get('state') != 'opened'
            or type(count) is not int or count < 1):
        raise ValueError('Declared kind, open scope and positive fetch count required')
    common = {'kind','client','state','required_successful_fetches','scope','collection'}
    if kind == 'atom':
        project = p.get('project'); collection = p.get('collection')
        if (set(p) != common|{'project'} or p['scope'] != 'project_open_collection'
                or not isinstance(project,str) or not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+',project)
                or collection not in ('issues','merge_requests')):
            raise ValueError('Exact public Atom project and collection required')
        base = '/'+project+'/-/'+collection; path=base+'.atom'; filters={'state':['opened']}
    else:
        if (set(p) != common|{'due_date_window'} or p['scope'] != 'current_account_assigned_open_issues'
                or p['collection'] != 'issues' or p['due_date_window'] != 'next_month_and_previous_two_weeks'):
            raise ValueError('Exact native current-account calendar window required')
        project=None;collection='issues';base='/dashboard/issues';path=base+'.ics'
        filters={'state':['opened'],'assignee_username':['{authenticated_username}'],
                 'due_date':['next_month_and_previous_two_weeks']}
    return dict(kind=kind,project_path=project,collection=collection,feed_path=path,
                feed_filters=filters,page_path=base+'?'+urlencode(filters,doseq=True,safe='{}'),
                required_successful_fetches=count)


def reference(site, username, contract, context, url, destination, *, sort_cookies=None, session=None):
    """Reuse the already verified native read-only Rails finder, not an LLM."""
    spec=feed_spec(contract)
    params=native_subscription_query(url,origin=site.url,contract=spec,username=username)
    allowed = {'issuable_sort','issue_sort','mergerequest_sort'}
    if sort_cookies is None:
        sort_cookies = {c['name']:c['value'] for c in context.cookies(site.url) if c['name'] in allowed}
    if not isinstance(sort_cookies,dict) or set(sort_cookies)-allowed or any(not isinstance(v,str) for v in sort_cookies.values()):
        raise ValueError('Only captured native sort preferences may be restored')
    request=dict(username=username,kind=spec['kind'],query=params,collection=spec['collection'],
                 project_path=spec['project_path'],sort_cookies=sort_cookies)
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    if session is not None:
        if session.site is not site:
            raise ValueError('Native reader belongs to another isolated website')
        return session.read(request,destination)
    with tempfile.TemporaryDirectory(prefix='native-feed-reference-',dir=site.state) as directory:
        folder=Path(directory);(folder/'input.json').write_text(json.dumps(request));(folder/'input.json').chmod(0o600)
        shutil.copyfile(Path(__file__).with_suffix('.rb'),folder/'reference.rb')
        command=['bash','/state/service.sh','gitlab-rails','env','RAILS_ENV=production',
                 '/opt/gitlab/embedded/bin/bundle','exec','/opt/gitlab/embedded/service/gitlab-rails/bin/rails',
                 'runner','-e','production','/state/'+folder.name+'/reference.rb','/state/'+folder.name+'/input.json']
        started=time.monotonic()
        try:result=site.command(command,capture_output=True,text=True,timeout=120)
        except (subprocess.CalledProcessError,subprocess.TimeoutExpired) as error:
            for label in ('stdout','stderr'):
                value=getattr(error,label,None) or ''
                if isinstance(value,bytes):value=value.decode('utf-8',errors='replace')
                target=destination.with_name(destination.stem+'-private-'+label+'.txt')
                target.write_text(value[-65536:]);target.chmod(0o600)
            raise
        lines=[line[len('LAB_FEED_REFERENCE='):] for line in result.stdout.splitlines() if line.startswith('LAB_FEED_REFERENCE=')]
        if len(lines)!=1:raise ValueError('Complete native feed reference required')
        value=json.loads(lines[0]);value['seconds']=time.monotonic()-started
        atomic_write_json(destination,value);destination.chmod(0o600);return value


def stable_reference(before,after):
    keys=('kind','username','account_id','project_id','selected_rows','rows','sort','native_date','native_options')
    return all(before.get(k)==after.get(k) for k in keys)


def inspect_payload(payload,contract,reference,*,origin):
    spec=feed_spec(contract)
    if reference.get('kind')!=spec['kind'] or not isinstance(reference.get('selected_rows'),list):
        raise ValueError('Independent native selection of the declared kind required')
    if spec['kind']=='calendar':
        return inspect_calendar_reference(payload,origin=origin,rows=reference['selected_rows'])
    return inspect_atom_reference(payload,origin=origin,project_path=spec['project_path'],project_id=reference['project_id'],
        collection=spec['collection'],filters=spec['feed_filters'],rows=reference['rows'],
        expected_page_iids=[r['iid'] for r in reference['selected_rows']])


def evaluate_client(contract,client,reference,*,origin,username,expected_url,regular):
    """Inspect a sealed/restored ordinary client via its strict public protocol.

    The caller binds reference before/after, native state protection and the
    authentic sealed client. A URL or a successful HTTP fetch alone is not a
    persisted subscription. Only boolean checks leave this function.
    """
    spec=feed_spec(contract)
    params=native_subscription_query(expected_url,origin=origin,contract=spec,username=username)
    if (reference.get('username')!=username or reference.get('kind')!=spec['kind']
            or type(reference.get('account_id')) is not int or reference['account_id']<=0):
        raise ValueError('Native account or reference kind differs')
    options=reference.get('native_options',{})
    if any(options.get(k)!=v for k,v in params.items()):
        raise ValueError('Native finder scope differs from declared subscription')
    saved=content=False
    for folder in sorted(client.root.iterdir()):
        if not folder.is_dir() or folder.is_symlink():continue
        if not client.completion(folder.name,expected_url=expected_url,expected_kind=spec['kind'],
                                 min_refreshes=spec['required_successful_fetches']):continue
        saved=True
        record=json.loads(regular(folder,'state.json').read_text())
        valid=[]
        for event in record['refreshes']:
            payload=regular(folder,event['body_file']).read_bytes()
            valid.append(inspect_payload(payload,contract,reference,origin=origin)['payload_verified'])
        if valid and all(valid):content=True
    checks={'saved_subscription_with_declared_fetches':saved,'fetched_content_matches_native_selection':content}
    return dict(status='success' if all(checks.values()) else 'failure',reward=1. if all(checks.values()) else 0.,checks=checks)
