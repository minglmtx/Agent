"""Optional local artifact actions; not registered in the browser actor yet.

Only current public native URLs authorize an operation. No expected project,
HEAD/tree, task goal, evaluator answers or private database enters this adapter.
Each candidate attempt must construct a fresh root/client. Tool completion is
an artifact operation, never a task-success judgment.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import uuid
from urllib.parse import parse_qs, unquote,urlsplit
from .gitlab_local_artifacts_v2 import local_native_url,redacted_url,LocalSubscriptionClient

VERSION='public-native-local-artifact-actions-draft-v1'
TOOL_SCHEMAS={
    'clone_repository':{'arguments':{'url':'string'},'description':'Clone the currently observed native local HTTP repository URL into this attempt workspace.'},
    'subscribe_feed':{'arguments':{'url':'string','kind':'atom|calendar'},'description':'Create an active local client subscription and fetch the native feed. This is an explicit local-client environment capability.'},
    'refresh_subscription':{'arguments':{'subscription_id':'string'},'description':'Refresh a previously created local subscription from its own saved native URL.'},
    'list_local_artifacts':{'arguments':{},'description':'List actual artifacts created in this attempt; it does not evaluate the task.'},
}


PUBLIC_NATIVE_URLS=r"""() => {
 const visible=e=>{if(!e||!e.isConnected||![...e.getClientRects()].some(r=>r.width>0&&r.height>0))return false;for(let n=e;n;n=n.parentElement){const style=getComputedStyle(n);if(style.display==='none'||style.visibility==='hidden'||style.visibility==='collapse'||Number(style.opacity)===0)return false;if(n.tagName==='DETAILS'&&!n.open&&!n.querySelector(':scope > summary')?.contains(e))return false;}return true;};
 return {url:location.href,input_urls:[...document.querySelectorAll('input')].filter(e=>visible(e)&&!['hidden','password'].includes(e.type)).map(e=>e.value),
         link_urls:[...document.querySelectorAll('a[href]')].filter(visible).map(e=>e.getAttribute('href'))};
}"""


def clone_native_url(value,origin):
    url=local_native_url(value,origin);part=urlsplit(url)
    path=unquote(part.path)
    if part.query or not path.endswith('.git')or not re.fullmatch(r'/[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+\.git',path):raise ValueError('A native local HTTP repository clone URL is required')
    return url


def run_git(args,*,timeout=180):
    """No shell, global credential helper, hooks, submodules or redirect fallback."""
    env={**os.environ,'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_TERMINAL_PROMPT':'0','GIT_LFS_SKIP_SMUDGE':'1'}
    prefix=['git','-c','credential.helper=','-c','core.hooksPath=/dev/null','-c','core.fsmonitor=false','-c','protocol.allow=never','-c','protocol.http.allow=always','-c','protocol.https.allow=always','-c','http.followRedirects=false']
    proc=subprocess.Popen(prefix+list(args),env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    try:
        try:stdout,stderr=proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            proc.communicate(timeout=5)
            raise TimeoutError('Native repository operation exceeded its finite deadline')from None
        if proc.returncode:raise RuntimeError('Native repository operation failed (exit '+str(proc.returncode)+')')
        return stdout.decode('utf-8',errors='strict').strip()
    finally:
        if proc.poll()is None:
            try:os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            proc.wait(timeout=5)
        proc.stdout.close();proc.stderr.close()


def native_feed_kind(url):
    """Recognize format advertised by a current native public URL.

    Payload parsing and exact-origin authorization remain separate checks.
    Duplicate or contradictory format parameters never authorize a feed.
    """
    part = urlsplit(url)
    formats = parse_qs(part.query, keep_blank_values=True).get('format', [])
    if len(formats) > 1:
        return None
    if part.path.endswith('.ics'):
        return 'calendar' if not formats or formats == ['ics'] else None
    if part.path.endswith('.atom'):
        return 'atom' if not formats or formats == ['atom'] else None
    return 'atom' if formats == ['atom'] else None


class LocalArtifactActions:
    def __init__(self,root,origin,request):
        parsed=urlsplit(origin)
        if parsed.scheme not in('http','https')or not parsed.netloc or parsed.path not in('','/')or parsed.query or parsed.fragment or parsed.username:raise ValueError('Exact leased site origin required')
        self.origin=origin.rstrip('/');self.request=request;self.root=Path(root)
        self.root.mkdir(mode=0o700,parents=True,exist_ok=False)
        self.repositories=self.root/'repositories';self.repositories.mkdir(mode=0o700)
        self.client=LocalSubscriptionClient(self.root/'subscriptions');self.observed_clones=set();self.observed_feeds={};self.records={}

    def observe_native_urls(self,*,clone_urls=(),feeds=()):
        """Replace candidates on each observation; caller supplies only public DOM."""
        self.observed_clones=set();self.observed_feeds={}
        clones={clone_native_url(value,self.origin)for value in clone_urls};native_feeds={}
        for row in feeds:
            if not isinstance(row,dict)or set(row)!={'url','kind'}or row['kind']not in('atom','calendar'):raise ValueError('Native feed URL and format required')
            url=local_native_url(row['url'],self.origin,calendar=row['kind']=='calendar')
            if native_feed_kind(url) != row['kind']:raise ValueError('Feed format does not match its native resource')
            native_feeds[(url,row['kind'])]=True
        self.observed_clones=clones;self.observed_feeds=native_feeds

    def observe_page(self,page):
        public=page.evaluate(PUBLIC_NATIVE_URLS)
        part=urlsplit(public['url']);origin=urlsplit(self.origin)
        if(part.scheme,part.netloc)!=(origin.scheme,origin.netloc):
            self.observe_native_urls();raise ValueError('Current page does not belong to this local artifact environment')
        clones=[];feeds=[]
        for value in public['input_urls']:
            try:clones.append(clone_native_url(value,self.origin))
            except(ValueError,TypeError):pass
        for value in public['link_urls']:
            try:
                kind=native_feed_kind(value)
                if kind is None:continue
                url=local_native_url(value,self.origin,calendar=kind=='calendar')
                feeds.append({'url':url,'kind':kind})
            except(ValueError,TypeError):pass
        self.observe_native_urls(clone_urls=clones,feeds=feeds)
        return self.public_native_candidates()


    def _fetch(self,url):
        url=local_native_url(url,self.origin)
        response=self.request.get(url,timeout=45000,max_redirects=0)
        if getattr(response,'url',None)!=url:raise ValueError('Native feed response did not preserve its exact resource URL')
        return response

    def clone_repository(self,url):
        url=clone_native_url(url,self.origin)
        if url not in self.observed_clones:raise ValueError('Clone URL is absent from the current public native observation')
        ident=uuid.uuid4().hex;folder=self.repositories/ident
        run_git(['clone','--depth=1','--no-recurse-submodules','--',url,str(folder)])
        if not(folder/'.git').is_dir():raise ValueError('No actual local repository was created')
        head=run_git(['-C',str(folder),'rev-parse','HEAD'],timeout=30);tree=run_git(['-C',str(folder),'rev-parse','HEAD^{tree}'],timeout=30)
        remote=run_git(['-C',str(folder),'remote','get-url','origin'],timeout=30)
        root=run_git(['-C',str(folder),'rev-parse','--show-toplevel'],timeout=30)
        if remote!=url or Path(root).resolve()!=folder.resolve()or run_git(['-C',str(folder),'status','--porcelain'],timeout=30):raise ValueError('Local clone identity or checked-out files are incomplete')
        if not re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}',head)or not re.fullmatch('[0-9a-f]{40}|[0-9a-f]{64}',tree):raise ValueError('Native repository object identity missing')
        record={'artifact_id':ident,'kind':'git_clone','status':'created','url':redacted_url(url),'head':head,'tree':tree,'checked_out':True,
                'actual_artifact_operation':True,'task_success_not_evaluated':True}
        file=self.root/(ident+'.json');file.write_text(json.dumps(record)+'\n');os.chmod(file,0o600);self.records[ident]=record
        return self._public(record)

    def subscribe_feed(self,url,kind):
        if kind not in('atom','calendar'):raise ValueError('Supported native feed format required')
        url=local_native_url(url,self.origin,calendar=kind=='calendar')
        matches=[native for native,format_ in self.observed_feeds if format_==kind and(url==native or url==redacted_url(native))]
        if len(matches)!=1:raise ValueError('Feed is absent or ambiguous in the current public native observation')
        url=matches[0]
        record=self.client.subscribe(url,self.origin,kind,self._fetch);self.records[record['subscription_id']]=record
        return self._public(record)

    def refresh_subscription(self,subscription_id):
        if subscription_id not in self.records or 'subscription_id'not in self.records[subscription_id]:raise ValueError('A subscription created in this attempt is required')
        record=self.client.refresh(subscription_id,self.origin,self._fetch);self.records[subscription_id]=record
        return self._public(record)

    def _public(self,record):
        if record.get('kind')=='git_clone':return {k:record[k]for k in('artifact_id','kind','status','url','actual_artifact_operation','task_success_not_evaluated')}
        parsed=record['parsed'];return {'subscription_id':record['subscription_id'],'kind':record['kind'],'active':record['active'],
            'successful_refreshes':record['successful_refreshes'],'url':record['url'],'entry_count':parsed.get('entries',parsed.get('events')),
            'explicit_local_client_adaptation':True,'task_success_not_evaluated':True}

    def list_local_artifacts(self):return [self._public(record)for record in self.records.values()]

    def public_native_candidates(self):
        return {'clone_urls':sorted(redacted_url(value)for value in self.observed_clones),
                'feeds':[{'url':redacted_url(url),'kind':kind}for url,kind in sorted(self.observed_feeds)]}

    def dispatch(self,name,args):
        if name not in TOOL_SCHEMAS or not isinstance(args,list):raise ValueError('Declared local artifact operation required')
        expected={'clone_repository':1,'subscribe_feed':2,'refresh_subscription':1,'list_local_artifacts':0}[name]
        if len(args)!=expected or any(not isinstance(value,str)for value in args):raise ValueError('Artifact arguments must match the advertised operation')
        return getattr(self,name)(*args)
