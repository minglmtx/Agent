"""Ordinary heldout preferences adapter: original public task, one allowed write.

This module neither grants training admission nor creates a release. The outer
gate must first verify the real independent native review and its source pins.
"""
from pathlib import Path
from urllib.parse import urlsplit
import hashlib,json,os
from .heldout_preferences_binding import validate_binding,require_initial,evaluate_attempt


def require(value,message):
    if not value:raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x')as f:
        json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())


def public_contract(binding):
    c=validate_binding(binding,executable=True)
    require(c['source_task_id']=='7771149f5802d818da29'
            and c['preferences']['targets']=={'auto_fetch_submission_titles':False},'Only the qualified first source')
    return {key:c[key]for key in ('task_id','domain','goal','start_path')}


def claim_record(sid,*,plan_ref,release_ref,job_id):
    require(sid=='7771149f5802d818da29'and str(job_id).isdigit(),'One fixed source and actual job required')
    return dict(source_task_id=sid,plan=plan_ref,release=release_ref,job_id=str(job_id),
                automatic_retry=False,purpose='codebase_acceptance')


def claim_source(root,sid,*,plan_ref,release_ref,job_id,other_claim_paths):
    require(not any(os.path.lexists(x)for x in other_claim_paths),'Another source attempt or continuation already exists')
    record=claim_record(sid,plan_ref=plan_ref,release_ref=release_ref,job_id=job_id)
    write(Path(root)/(sid+'.json'),record)
    return record


def verify_claim(root,sid,claim_ref,*,plan_ref,release_ref,job_id,other_claim_paths):
    path=Path(root)/(sid+'.json');data=path.read_bytes()
    require(claim_ref==dict(path=str(path),sha256=hashlib.sha256(data).hexdigest())
            and not any(os.path.lexists(x)for x in other_claim_paths),'Persistent claim changed or mixed continuation')
    record=json.loads(data)
    require(record==claim_record(sid,plan_ref=plan_ref,release_ref=release_ref,job_id=job_id),'Claim source/plan/release/job differs')
    return record


def capture_private(page,site,auth):
    from probe_content_sites import capture_current
    state=capture_current(page,'reddit')
    state['page_text']=page.locator('body').inner_text()
    state['local_links']=page.locator('a[href]').evaluate_all('es=>es.map(e=>({text:e.textContent,href:e.href}))')
    cdp=page.context.new_cdp_session(page)
    try:state['native_ax_nodes']=cdp.send('Accessibility.getFullAXTree')['nodes']
    finally:cdp.detach()
    account=page.get_by_role('button',name=auth['username'],exact=True).is_visible()
    anonymous=page.locator('nav a[href="/login"]').is_visible()and page.locator('nav a[href="/registration"]').is_visible()
    state['source_authentication_check']=dict(expected='authenticated',account_menu_visible=account,
        login_signup_visible=anonymous,passed=account and not anonymous)
    state['native_profiler_surface']=page.evaluate(r'''() => ({
        toolbar_elements:document.querySelectorAll('.sf-toolbar, .sf-toolbarreset').length,
        profiler_links:[...document.querySelectorAll('a[href]')].filter(a=>/^\/(?:_profiler|_wdt)(?:\/|$)/.test(new URL(a.href).pathname)).length})''')
    return state


def require_initial_protection(binding,before,qualified_baseline):
    """Fresh full DB baseline, before any browser or Actor generation.

    Native qualification may allow the final target-column transition. The
    initial state still has to match the actually qualified complete baseline.
    Each physical catalog is validated completely. PostgreSQL relation_oid is
    compared only within one instance; all other catalog fields match across
    the qualified and fresh independent instances.
    """
    from .heldout_preferences_protection import VERSION,verify_transition
    public_contract(binding)
    require(VERSION=='heldout-preferences-exact-user-protection-v2',
            'Actual qualified physical-schema protection version required')
    verify_transition(binding,qualified_baseline,qualified_baseline)
    verify_transition(binding,before,before)
    def structure(snapshot):
        return [{k:v for k,v in row.items()if k!='relation_oid'}for row in snapshot['users_catalog']]
    require(before['preferences']['values']['auto_fetch_submission_titles']is True
            and before['original_full13']==qualified_baseline['original_full13']
            and before['preferences']==qualified_baseline['preferences']
            and before['projection']==qualified_baseline['projection']
            and before['users_columns']==qualified_baseline['users_columns']
            and structure(before)==structure(qualified_baseline),
            'Fresh complete original account/database baseline differs')
    return dict(passed=True,binding_sha256=binding['binding_sha256'],
                protected_version=VERSION,full13_equal=True,complete_account_equal=True,
                physical_schema_equal_except_relation_oid=True,
                qualified_relation_oid=qualified_baseline['users_catalog'][0]['relation_oid'],
                fresh_relation_oid=before['users_catalog'][0]['relation_oid'],
                checked_before_browser_and_generation=True)


def make_session(site,binding,auth,directory,before,qualified_baseline):
    # Private database evidence is used only by the gate. Public Task/setup and
    # the unchanged Actor request builder never receive it.
    directory=Path(directory)
    initial_guard=require_initial_protection(binding,before,qualified_baseline)
    write(directory/'initial-protection-binding.json',initial_guard)
    before_preferences=before['preferences']
    from browsergym.core.env import BrowserEnv
    from browsergym.core.task import AbstractBrowserTask
    from .gobrowse_runtime import BrowserGymSession
    from .browser_action_timing import make_browser_action_set,make_browser_action_mapping
    from .browser_request_policy import install_local_network_policy
    from .site_auth import login
    public=public_contract(binding)

    class Task(AbstractBrowserTask):
        def __init__(self,seed):super().__init__(seed);self.timeout=60000
        def setup(self,page):
            install_local_network_policy(page.context,urlsplit(site.url).netloc)
            login(page,site,auth)
            page.goto(site.url+public['start_path'],wait_until='domcontentloaded',timeout=60000)
            initial=capture_private(page,site,auth);write(directory/'initial-page.json',initial)
            check=require_initial(binding,initial,before_preferences,site_origin=site.url)
            write(directory/'initial-page-binding.json',check)
            return public['goal'],{}
        def validate(self,page,chat_messages):return 0.,False,'',{}

    class Session(BrowserGymSession):
        def __init__(self,settings,task):
            self.domain='reddit';self.index=0;self.download_directory=directory/'browser-downloads'
            self.action_set=make_browser_action_set()
            self.action_description=self.action_set.describe(with_long_description=True,with_examples=True)
            self.env=BrowserEnv(Task,headless=True,timeout=60000,
                action_mapping=make_browser_action_mapping(self.action_set),wait_for_user_message=False,
                viewport={'width':1280,'height':720})
        def record(self,observation,action=None):
            write(directory/('step-%03d.json'%self.index),dict(step=self.index,action=action,observation=observation))
            self.index+=1
        def reset(self,seed):
            result=super().reset(seed);self.record(result[0])
            page=capture_private(self.env.page,site,auth);write(directory/'initial-observation-page.json',page)
            checked=require_initial(binding,page,before_preferences,site_origin=site.url)
            require(result[0]['url']==page['url'],'Actual first Actor observation URL differs')
            write(directory/'initial-observation-binding.json',dict(checked,observation_sha256=digest(result[0]),
                actual_observation_url=result[0]['url'],page_url=page['url'],checked_before_first_generation=True))
            return result
        def step(self,action):
            result=super().step(action);self.record(result[0],action);return result
        def close(self):
            try:
                if self.env.page is not None:write(directory/'terminal-page.json',capture_private(self.env.page,site,auth))
            finally:
                super().close();write(directory/'browser-closed.json',dict(closed=True))
    return Session


def judge_transition(binding,terminal,before,after,*,site_origin,trace_error=None):
    """Keep whole users protection except this account's exact public target.

    Do not replace this with before==after: a real successful preference write
    necessarily changes the original users digest. Unknown remains unknown.
    """
    return evaluate_attempt(binding,terminal,before,after,site_origin=site_origin,runtime_error=trace_error)
