"""Candidate native save/reopen checks; captures must be independently qualified."""
from urllib.parse import urlsplit,unquote
import ast,re
VERSION='native-map-upload-diary-save-v187-r5'
SOURCES={'upload':'ca83744cd6665d0bf7ba','diary':'f4e78317c35308b7e404'}

def snapshot(value):
    if not isinstance(value,dict)or value.get('passed')is not True or value.get('read_only')is not True:raise ValueError('Native readonly snapshot unavailable')
    for key in ('users','diaries','traces'):
        rows=value.get(key)
        if not isinstance(rows,list)or any(not isinstance(r,dict)or type(r.get('id'))is not int or (key!='users'and r['id']<=0)for r in rows):raise ValueError('Incomplete native record inventory: '+key)
        if len({r['id']for r in rows})!=len(rows):raise ValueError('Duplicate native identity')
    for r in value['users']:
        if not isinstance(r.get('email'),str)or not r['email']or not isinstance(r.get('display_name'),str):raise ValueError('Native author identity unavailable')
    for key,fields in [('diaries',('title','body')),('traces',('name','description','visibility'))]:
        for r in value[key]:
            if type(r.get('user_id'))is not int or type(r.get('visible'))is not bool or any(not isinstance(r.get(k),str)for k in fields):raise ValueError('Incomplete native saved record')
            if key=='traces':
                if 'file'not in r:raise ValueError('Native original-file evidence unavailable')
                f=r['file']
                if f is not None and (not isinstance(f,dict)or type(f.get('bytes'))is not int or f['bytes']<=0 or not isinstance(f.get('filename'),str)or not re.fullmatch('[0-9a-f]{64}',str(f.get('sha256')))):raise ValueError('Native file evidence malformed')
    return value

def evaluate(kind,before,after,c,witness,page,origin,*,runtime_error=None,capture_error=None,trace=None):
    if kind not in SOURCES or c.get('source_task_id')!=SOURCES[kind]:raise ValueError('Exact source contract required')
    checks={}
    def result(status,reason):return dict(version=VERSION,status=status,reward={'success':1,'failure':0,'unknown':None}[status],checks=checks,reason=reason)
    if runtime_error or capture_error:return result('unknown','Runtime or evidence capture failed.')
    try:
        snapshot(before);snapshot(after);params=c['parameters'];account=params['account'];root=urlsplit(origin)
        if not isinstance(witness,dict)or witness.get('capture_complete')is not True or not isinstance(witness.get('events'),list):raise ValueError('Actual save/readback evidence unavailable')
        authors=[r for r in before['users']if r['email']==account['email']and r['display_name']==account['display_name']]
        if len(authors)!=1 or authors[0]['id']<=0 or not authors[0]['display_name']or authors[0]not in after['users']:raise ValueError('Declared existing native author not bound')
        uid=authors[0]['id'];key='traces'if kind=='upload'else'diaries';old={r['id']for r in before[key]}
        fresh=[r for r in after[key]if r['id']not in old and r['user_id']==uid and r['visible']]
        if kind=='upload':
            matched=[r for r in fresh if r['name']==re.sub(r'[^a-zA-Z0-9.]','_',params['filename'])and r['description']==params['description']and r['visibility']==params['visibility']]
            checks['new_native_identity']=len(matched)==1
            file=matched[0]['file']if len(matched)==1 else None
            checks['saved_original_file']=bool(file and file['sha256']==params['public_file']['sha256'])
        else:
            matched=[r for r in fresh if r['title']==params['title']and r['body']==params['body']]
            checks['new_saved_author_title_body']=len(matched)==1
        save_path='/traces'if kind=='upload'else'/diary';saved=[];readbacks=[]
        for e in witness['events']:
            if not isinstance(e,dict)or e.get('kind')not in ('saved','reopened')or type(e.get('sequence'))is not int or not isinstance(e.get('url'),str)or type(e.get('status'))is not int or e.get('native_response_completed')is not True:raise ValueError('Malformed native request receipt')
            u=urlsplit(e['url'])
            if (u.scheme,u.netloc)!=(root.scheme,root.netloc):continue
            if e['kind']=='saved':
                if e.get('method')=='POST'and u.path.rstrip('/')==save_path and e['status']in (200,201,302,303):saved.append(e)
            elif e.get('method')=='GET'and e['status']==200 and not u.query and not u.fragment:
                if not isinstance(e.get('public_observation'),str):raise ValueError('Actual public readback missing')
                readbacks.append(e)
        checks['native_save']=bool(saved);checks['public_reopen']=False
        if len(matched)==1:
            r=matched[0];path='/user/'+account['display_name']+('/traces/'if kind=='upload'else'/diary/')+str(r['id'])
            values=[account['display_name'],r['name'],params['description']]if kind=='upload'else[account['display_name'],params['title'],params['body']]
            checks['public_reopen']=any(unquote(urlsplit(e['url']).path).rstrip('/')==path and any(s['sequence']<e['sequence']for s in saved)and all(v in e['public_observation']for v in values)for e in readbacks)
        if all(checks.values()):
            return result('success','Native saved record and actual public readback verified; no additional terminal-page requirement.')
        if not isinstance(page,dict)or type(page.get('http_status'))is not int or any(type(page.get(k))is not bool for k in ('login_page','error_page')):
            raise ValueError('Native terminal document unavailable')
        current=urlsplit(page['url'])
        healthy=200<=page['http_status']<300 and not page['login_page'] and not page['error_page'] and (current.scheme,current.netloc)==(root.scheme,root.netloc)
        if not healthy:
            if not witness['events'] and actor_unmapped_route(trace,c,page,origin):
                return result('failure','Actor explicitly navigated to an unmapped native route; complete native state and capture prove no save.')
            raise ValueError('Native terminal document unhealthy')
        return result('failure','Native saved record and actual public readback checked; rendering, per-point audit and future interaction are outside scope.')
    except (ValueError,KeyError,TypeError)as exc:return result('unknown',str(exc))


def actor_unmapped_route(trace,contract,page,origin):
    """Only a native routing 404 attributable to an explicit Actor goto.

No click error, missing capture, server error, mapped-object 404 or other origin
is converted to a task failure. Required save/readback errors remain unknown.
"""
    if not isinstance(trace,dict) or trace.get('error') is not None or trace.get('task_id')!=contract['task_id'] or trace.get('task_instruction')!=contract['goal']:
        return False
    root,current=urlsplit(origin),urlsplit(page.get('url',''))
    if (current.scheme,current.netloc)!=(root.scheme,root.netloc) or page.get('http_status')!=404 or page.get('login_page') is not False or page.get('error_page') is not True:
        return False
    diagnostic='No route matches [GET] "'+current.path+'"'
    if page.get('title')!='Action Controller: Exception caught' or page.get('heading_texts',[])[:2]!=['Routing Error',diagnostic] or diagnostic not in page.get('page_text',''):
        return False
    if not isinstance(trace.get('messages'),list):
        return False
    for message in trace['messages']:
        if not isinstance(message,dict) or message.get('role')!='assistant':
            continue
        try:
            call=ast.parse(message.get('action_payload',''),mode='eval').body
            if not isinstance(call,ast.Call) or not isinstance(call.func,ast.Name) or call.func.id!='goto' or len(call.args)!=1 or call.keywords:
                continue
            target=ast.literal_eval(call.args[0])
            if not isinstance(target,str):
                continue
            parts=urlsplit(target)
            if (parts.scheme,parts.netloc,parts.path,parts.query)==(current.scheme,current.netloc,current.path,current.query):
                return True
        except (ValueError,TypeError,SyntaxError):
            continue
    return False
