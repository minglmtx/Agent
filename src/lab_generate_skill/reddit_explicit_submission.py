"""Exact, explicitly revised Reddit submission/draft tasks.

This optional adapter has no creative-writing or relevance judge. Private saved
references never become actor input; only the declared derived goal carries its
new exact parameters. Legacy submission rules are not changed.
"""
import hashlib
import json
from urllib.parse import urlsplit
from .reddit_submission import submission_state
from .native_form_text import same_form_body
from .site_navigation_rules import valid_initial_page

VERSION = 'reddit-explicit-submission-v1'
ADMISSION_VERSION = 'reddit-explicit-submission-admission-v1'
KINDS = {'published_text', 'draft_title', 'draft_body', 'forum_selection'}

READ = r'''() => {
 const visible=e=>{if(!e||!e.isConnected||![...e.getClientRects()].some(r=>r.width>0&&r.height>0))return false;for(let n=e;n;n=n.parentElement){const s=getComputedStyle(n);if(s.display==='none'||s.visibility==='hidden'||s.visibility==='collapse'||Number(s.opacity)===0)return false;if(n.tagName==='DETAILS'&&!n.open&&!n.querySelector(':scope > summary')?.contains(e))return false;}return true;};
 return {url:location.href,forms:[...document.querySelectorAll('#main form')].filter(f=>f.querySelector('[name="submission[title]"]')).map(f=>({
  action:new URL(f.getAttribute('action')||location.href,location.href).href,method:f.method,
  fields:[...f.querySelectorAll('input,select,textarea')].filter(e=>/^submission\[(title|body|forum|url|mediaType)\]$/.test(e.name)).map(e=>({name:e.name,tag:e.tagName,type:e.type,value:e.value,checked:e.type==='radio'?e.checked:null,visible:visible(e),disabled:!!e.disabled,
   selected:e.tagName==='SELECT'?[...e.selectedOptions].map(o=>({value:o.value,label:o.text})):null})),
  forum_controls:[...f.querySelectorAll('[role="combobox"]')].map(e=>({text:e.innerText.trim(),visible:visible(e),expanded:e.getAttribute('aria-expanded')})),
  submit_buttons:[...f.querySelectorAll('button[type="submit"],input[type="submit"]')].map(e=>({label:e.innerText.trim()||e.value,visible:visible(e),disabled:!!e.disabled}))
 }))};
}'''


def validate_contract(c):
    s=c.get('explicit_submission')
    if c.get('domain')!='reddit' or not isinstance(s,dict) or s.get('kind') not in KINDS:
        raise ValueError('Explicit Reddit submission kind required')
    expected={'published_text':{'kind','forum','title','body'},'draft_title':{'kind','title'},
              'draft_body':{'kind','body'},'forum_selection':{'kind','forum'}}[s['kind']]
    if set(s)!=expected or any(not isinstance(s[k],str) or not s[k].strip() for k in expected-{'kind'}):
        raise ValueError('Exact nonempty declared fields required')
    if(c.get('task_id')==c.get('source_task_id') or c.get('task_text_changed') is not True
       or c.get('original_evaluation_equivalence') is not False or c.get('goal')!=c.get('derived_goal')
       or not isinstance(c.get('goal'),str)or not c['goal'].strip()or c.get('goal')==c.get('original_goal')
       or not isinstance(c.get('original_goal'),str) or c.get('heldout_quarantine') is not False):
        raise ValueError('An explicit isolated training derivative and source mapping are required')


def fingerprint(c):
    validate_contract(c)
    keys=('task_id','source_task_id','domain','goal','derived_goal','original_goal','start_path','recorded_start_paths',
          'source_trace_ids','explicit_submission','task_text_changed','original_evaluation_equivalence','heldout_quarantine','task_version')
    return hashlib.sha256(json.dumps({k:c.get(k)for k in keys},sort_keys=True).encode()).hexdigest()


def state(site,username,baseline=None):
    return submission_state(site,username,baseline)


def validate_initial(c,initial):
    validate_contract(c)
    if(not isinstance(initial,dict) or type(initial.get('user_id'))is not int or initial['user_id']<=0
       or initial.get('added')!=[] or not isinstance(initial.get('forums'),list)
       or not isinstance(initial.get('known_id_ranges'),list) or not isinstance(initial.get('protected_content'),dict)):
        raise ValueError('Clean native submission baseline required')
    name=c['explicit_submission'].get('forum')
    if name is not None and len([r for r in initial['forums']if r['name']==name])!=1:
        raise ValueError('Declared forum is missing or ambiguous')


def _draft_checks(c,public,site_origin,initial):
    if not isinstance(public,dict) or not isinstance(public.get('forms'),list):raise ValueError('Missing native draft capture')
    spec=c['explicit_submission'];forms=public['forms'];u=urlsplit(public.get('url',''));origin=urlsplit(site_origin)
    checks={'native_submission_form':len(forms)==1 and (u.scheme,u.netloc)==(origin.scheme,origin.netloc) and u.path=='/submit' and not u.query}
    if len(forms)!=1:return checks
    form=forms[0]
    if not isinstance(form,dict) or not isinstance(form.get('fields'),list) or not isinstance(form.get('forum_controls'),list):raise ValueError('Malformed native draft form')
    target=urlsplit(form.get('action',''))
    checks['native_form_action']=form.get('method')=='post' and (target.scheme,target.netloc)==(origin.scheme,origin.netloc) and target.path=='/submit' and not target.query
    for key in ('title','body'):
        if key not in spec:continue
        rows=[r for r in form['fields']if r.get('name')=='submission['+key+']']
        if any(not isinstance(r.get('value'),str) or type(r.get('visible'))is not bool or type(r.get('disabled'))is not bool for r in rows):raise ValueError('Malformed native draft field')
        checks['requested_'+key]=len(rows)==1 and rows[0]['value']==spec[key] and rows[0]['visible']is True and rows[0]['disabled']is False
    if 'forum' in spec:
        rows=[r for r in form['fields']if r.get('name')=='submission[forum]'];controls=[r for r in form['forum_controls']if r.get('visible')is True]
        if any(not isinstance(r.get('selected'),list) for r in rows):raise ValueError('Malformed native forum selection')
        selected=rows[0]['selected']if len(rows)==1 else[]
        if any(not isinstance(r,dict)or not isinstance(r.get('value'),str)or not isinstance(r.get('label'),str)for r in selected):raise ValueError('Malformed selected forum identity')
        expected=[r for r in initial['forums']if r['name']==spec['forum']]
        checks['requested_forum']=len(selected)==1 and len(expected)==1 and selected[0].get('value')==str(expected[0]['id']) and selected[0].get('label')==spec['forum'] and len(controls)==1 and controls[0].get('text')==spec['forum']
    return checks


def evaluate(c,page,initial,final,*,site_origin,public=None,runtime_error=None):
    validate_contract(c)
    unknown=lambda reason:{'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':reason}
    if runtime_error:return unknown('Environment or inference error')
    if(not isinstance(page,dict)or type(page.get('http_status'))is not int or not 200<=page['http_status']<500):return unknown('Missing terminal document or server/transport error')
    try:validate_initial(c,initial)
    except (ValueError,KeyError,TypeError):return unknown('Missing or malformed native initial state')
    if(not isinstance(final,dict)or final.get('user_id')!=initial['user_id']or final.get('known_id_ranges')!=initial['known_id_ranges']
       or not isinstance(final.get('added'),list)or not isinstance(final.get('protected_content'),dict)or not isinstance(final.get('forums'),list)):
        return unknown('Missing or mismatched native submission baseline')
    checks={'page_valid':valid_initial_page(page,site_origin=site_origin),
            'existing_content_unchanged':final['protected_content']==initial['protected_content'],
            'forums_unchanged':final['forums']==initial['forums']}
    spec=c['explicit_submission']
    if spec['kind']=='published_text':
        checks['one_submission_saved']=len(final['added'])==1
        if len(final['added'])==1:
            row=final['added'][0]
            required={'id','forum_id','user_id','title','url','body','image_id','media_type','visibility'}
            if(not isinstance(row,dict)or not required<=set(row)or any(type(row[k])is not int or row[k]<=0 for k in('id','forum_id','user_id'))or any(not isinstance(row[k],str)for k in('title','body','media_type','visibility'))):return unknown('Malformed persisted submission row')
            forums={r['id']:r['name']for r in initial['forums']}
            checks.update(correct_author=row.get('user_id')==initial['user_id'],requested_forum=forums.get(row.get('forum_id'))==spec['forum'],
                          requested_title=row.get('title')==spec['title'],requested_body=same_form_body(row.get('body'),spec['body']),
                          text_submission=row.get('url')in(None,'')and row.get('image_id')is None and row.get('media_type')=='url',
                          publicly_visible=row.get('visibility')=='visible')
    else:
        checks['draft_not_published']=final['added']==[]
        try:checks.update(_draft_checks(c,public,site_origin,initial))
        except (ValueError,TypeError,KeyError):return unknown('Malformed or missing public draft capture')
    passed=all(checks.values())
    return {'version':VERSION,'status':'success'if passed else'failure','reward':float(passed),'checks':checks,'reason':None}


def expected_controls(c):
    validate_contract(c)
    if c['explicit_submission']['kind']=='published_text':
        return dict.fromkeys(('no_op','filled_unsaved','wrong_forum','wrong_title','wrong_body','404','login'),'failure')|{'positive':'success','saved_then_home':'success'}
    return dict.fromkeys(('no_op','wrong_value','wrong_page','published_negative','404','login'),'failure')|{'positive':'success'}


def require_admission(c,proof):
    validate_contract(c)
    if(proof.get('version')!=ADMISSION_VERSION or proof.get('contract_fingerprint')!=fingerprint(c)
       or proof.get('passed')is not True or proof.get('reset_mode')!='two_fresh_sites_restored_per_source'
       or proof.get('api_calls')!=0 or len(proof.get('cycles',[]))!=2):raise ValueError('Stale or incomplete explicit-submission admission')
    cycles=proof['cycles']
    for row in cycles:
        validate_initial(c,row.get('initial_state'))
        if(row.get('passed')is not True or row.get('checks')!=expected_controls(c)or row.get('initial_valid')is not True
           or row.get('restored')is not True or row.get('initial_state')!=row.get('final_state')
           or not row.get('initial_fingerprint')or row['initial_fingerprint']!=row.get('final_fingerprint')
           or not isinstance(row.get('private_protected_before'),dict)or not row['private_protected_before']
           or row['private_protected_before']!=row.get('private_protected_after')):
            raise ValueError('Native positive/negative/restore controls incomplete')
    if(cycles[0]['initial_state']!=cycles[1]['initial_state']or cycles[0]['initial_fingerprint']!=cycles[1]['initial_fingerprint']
       or cycles[0]['private_protected_before']!=cycles[1]['private_protected_before']):
        raise ValueError('Fresh explicit-submission baselines differ')
