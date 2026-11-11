"""Current native callback port; original runner and CPU constructors excluded."""
from lab_generate_skill.gitlab_project_description import NAMESPACE_READER, namespace_label

import json,re

from html.parser import HTMLParser

from html import unescape

from urllib.parse import urlsplit,parse_qs,unquote

from lab_generate_skill.source_revision_binding import binding

from lab_generate_skill.site_navigation_rules import valid_initial_page

from . import gitlab_next_public as public

from .gitlab_next_native import timestamp,PendingCapability

def visible_text(value):
 class Text(HTMLParser):
  def __init__(self):super().__init__();self.parts=[]
  def handle_data(self,data):self.parts.append(data)
 # Native release descriptions are markdown rendered into the native drawer;
 # compare every body word, removing presentation markup and URL destinations.
 value=re.sub(r'!?\[([^\]]*)\]\([^)]*\)',r'\1',value)
 parser=Text();parser.feed(value);value=' '.join(parser.parts)
 value=re.sub(r'(?m)^\s*(?:#{1,6}|[-*+]\s|>\s)\s*','',value)
 return re.sub(r'\s+',' ',unescape(value).replace('**','').replace('__','').replace('`','')).strip()

def closure_answer(value):
 if not isinstance(value,dict)or set(value)!={'closed_at','merge_requests'}:return None
 iids=value['merge_requests']
 if not isinstance(iids,list)or any(type(i)is not int or i<=0 for i in iids)or len(iids)!=len(set(iids)):return None
 try:closed=timestamp(value['closed_at'])if value['closed_at']is not None else None
 except(ValueError,TypeError):return None
 if (closed is None)!=(not iids):return None
 return {'closed_at':closed,'merge_requests':sorted(iids)}

VERSION='gitlab-next-native-capabilities-v1';FAMILY='gitlab_next_native'

VERSION='gitlab-next-native-capabilities-v1';FAMILY='gitlab_next_native'

OPERATIONS={'last_closed','switch_account','whats_new','blank_description'}

DOM_READ=r'''() => {
 const visible=e=>!!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
 const main=document.querySelector('main.content,#content-body')||document.querySelector('main');
 const drawers=[...document.querySelectorAll('.gl-drawer,.whats-new-modal,#whats-new-modal,[data-testid="whats-new-drawer"]')].filter(visible);
 const form=document.querySelector('form#new_project');
 return {url:location.href,account_id:window.gon?.current_user_id??null,body_page:document.body.dataset.page,
 capture_truncated:false,main_text:main?.innerText||'',
 times:[...document.querySelectorAll('main time[datetime],#content-body time[datetime]')].filter(visible).map(e=>({datetime:e.getAttribute('datetime'),context:e.parentElement.innerText})),
 closed_links:[...document.querySelectorAll('main a[href],#content-body a[href]')].filter(visible).filter(e=>/Closed/.test(e.innerText)).map(e=>({text:e.innerText.trim(),path:new URL(e.href).pathname+new URL(e.href).search})),
 projects:[...document.querySelectorAll('.project-row')].map(e=>({path:e.querySelector('a.project[href]')?.getAttribute('href'),name:e.querySelector('a.text-plain.js-prefetch-document[href]')?.innerText.trim(),description:(e.querySelector('.project-details .description,.project-description')?.innerText.trim()||'').replace(/\s+/g,' ')})),
 next_links:[...document.querySelectorAll('.pagination a[href]')].filter(visible).filter(e=>/^Next\s*$/i.test(e.innerText)).map(e=>e.getAttribute('href')),
 drawer:drawers.length===1?{visible:true,text:drawers[0].innerText,headings:[...drawers[0].querySelectorAll('h1,h2,h3,h4')].map(e=>e.innerText.trim())}:null,
 links:[...document.querySelectorAll('a[href]')].filter(visible).map(e=>({text:e.innerText.trim(),path:new URL(e.href).pathname+new URL(e.href).hash})),
 blank_form:form&&visible(form)?{id:form.id,namespace_field:(__NAMESPACE_READER__)(form),fields:[...form.querySelectorAll('input,select,textarea')].filter(e=>e.type!=='hidden').map(e=>({name:e.name,required:e.required,id:e.id,label:e.id?[...document.querySelectorAll('label')].find(l=>l.htmlFor===e.id)?.innerText.trim():null})),buttons:[...form.querySelectorAll('button,input[type="submit"]')].filter(visible).map(e=>e.innerText.trim()||e.value)}:null};}'''

DOM_READ=DOM_READ.replace('__NAMESPACE_READER__',NAMESPACE_READER)

def enabled(c):
 binding(c)
 if c.get('domain')!='gitlab'or c.get('family')!=FAMILY or c.get('public_parameters',{}).get('operation')not in OPERATIONS:raise ValueError('Explicit supported native source family required')
 if c.get('training_admitted')is not False or c.get('normal_gate_passed')is not False:raise ValueError('CPU candidate cannot claim admission')
 if c.get('public_task_input',{}).get('goal')!=c['goal']or c['public_task_input'].get('public_parameters')!=c['public_parameters']:raise ValueError('Complete identical public task inputs required')
 return True

def public_goal(c):
 enabled(c);public.public_input(c)
 return public.append_parameters(c,c['goal'])

def capture(page):return page.evaluate(DOM_READ)

def answer(terminal):
 value=terminal.get('answer','')
 if isinstance(value,dict):return value
 if not isinstance(value,str):return None
 try:return json.loads(value)
 except (ValueError,TypeError):return None

def valid_capture(v):
 return isinstance(v,dict)and v.get('capture_truncated')is False and isinstance(v.get('url'),str)and isinstance(v.get('body_page'),str)and isinstance(v.get('main_text'),str)

def collection_checks(private,captures,origin):
 """Compare every real page and every row, rejecting partial/guessed results."""
 expected={r['path']:r for r in private['source_rows']};pages={};valid=True
 for v in captures:
  if not valid_capture(v):valid=False;continue
  u=urlsplit(v['url']);q=parse_qs(u.query,keep_blank_values=True)
  if u.netloc!=urlsplit(origin).netloc or u.path!='/explore/projects'or set(q)-{'non_archived','sort','page'}or q.get('sort',['name_asc'])!=['name_asc']or q.get('non_archived',['true'])!=['true']:continue
  number=q.get('page',['1'])
  if len(number)!=1 or not number[0].isdecimal()or int(number[0])<1:valid=False;continue
  if v.get('account_id')!=private['access']['user']['id']or not isinstance(v.get('projects'),list)or not isinstance(v.get('next_links'),list):valid=False;continue
  index=int(number[0])
  if index in pages and (pages[index]['projects'],pages[index]['next_links'])!=(v['projects'],v['next_links']):valid=False
  pages[index]=v
 paths=[];values_ok=True
 for number,v in sorted(pages.items()):
  for r in v['projects']:
   if not isinstance(r,dict)or not isinstance(r.get('path'),str):values_ok=False;continue
   path=unquote(urlsplit(r['path']).path).strip('/');paths.append(path)
   ref=expected.get(path)
   values_ok &= bool(ref and r.get('name')==ref['display_name']and r.get('description')==ref['description_text'])
 complete=bool(pages)and sorted(pages)==list(range(1,len(pages)+1))and len(paths)==len(set(paths))and set(paths)==set(expected)
 if pages:complete &= not pages[max(pages)]['next_links']
 return {'complete_native_directory':bool(valid and complete),'exact_independent_native_directory_values':bool(values_ok and complete)}

def blank_checks(private,captures,response):
 forms=[v['blank_form']for v in captures if valid_capture(v)and v.get('blank_form')]
 forms=[f for f in forms if f.get('id')=='new_project']
 expected=private['required_operations'];steps=response.get('steps')if isinstance(response,dict)and set(response)=={'steps'}else None
 if not isinstance(steps,list)or any(not isinstance(s,dict)or set(s)!={'operation','ui_label'}or not isinstance(s['ui_label'],str)or not s['ui_label'].strip()for s in steps):steps=[]
 operations=[s['operation']for s in steps]
 shape=operations==expected
 labels={}
 for f in forms:
  for row in f.get('fields',[]):
   if row.get('name')=='project[name]':labels['set_project_name']=row.get('label')
   # The native personal namespace may be a static field rather than a select.
  labels['check_project_namespace']=namespace_label(f)
  labels['submit_create_project']=next((b for b in f.get('buttons',[])if re.fullmatch('Create project',b,re.I)),None)
 for v in captures:
  for link in v.get('links',[])if valid_capture(v)else[]:
   if link.get('path')=='/projects/new':labels['open_project_creation']=link['text']
   if link.get('path')=='/projects/new#blank_project':labels['choose_blank_project']=link['text'].split('Create a blank project')[0].strip()
 # Visibility is a process parameter supplied to both models, not a secret
 # chosen by a judge. The exact native form input must actually exist.
 visibility=any(any(r.get('name')=='project[visibility_level]'for r in f.get('fields',[]))for f in forms)
 labels['choose_visibility']='Private'if visibility else None
 ui=shape and all(labels.get(s['operation'])and s['ui_label'].casefold()==labels[s['operation']].casefold()for s in steps)
 return {'actual_native_blank_form_observed':bool(forms and visibility),'correct_ordered_creation_description':shape,'actual_native_UI_labels_in_description':bool(ui)}

def evaluate(c,private,terminal,captures,events,origin):
 enabled(c);operation=c['public_parameters']['operation'];v=terminal.get('gitlab_next_capture')
 checks={'valid_terminal_document':valid_initial_page(terminal,site_origin=origin),'actual_bound_native_capture':valid_capture(v)}
 if not all(checks.values()):return {'version':VERSION,'status':'failure','reward':0.,'checks':checks,'private_reference_values_in_feedback':False}
 reply=answer(terminal);path=urlsplit(v['url']).path
 if operation=='last_closed':
  target='/'+private['project']['path']+'/-/merge_requests';wanted=private['answer'];matches=closure_answer(reply)==wanted
  if wanted['closed_at']is None:
   q=parse_qs(urlsplit(v['url']).query);correct=path==target and q.get('state')==['closed']and any(re.fullmatch(r'Closed\s+0',r.get('text',''))for r in v.get('closed_links',[]))
  else:
   iids=wanted['merge_requests'];correct=any(path==target+'/'+str(i)for i in iids)
   times=[]
   for t in v.get('times',[]):
    try:times.append(timestamp(t.get('datetime')))
    except (ValueError,TypeError):pass
   correct &= wanted['closed_at']in times
  checks.update(correct_native_closed_object=bool(correct),exact_independent_native_closure_answer=matches)
 elif operation=='literal_projects':
  checks.update(collection_checks(private,captures,origin));checks['exact_literal_complete_project_answer']=reply==private['answer']
 elif operation=='switch_account':
  signedout=[i for i,e in enumerate(events)if e.get('kind')=='capture'and e.get('account_id')is None and e.get('path')=='/users/sign_in']
  login=[i for i,e in enumerate(events)if e.get('kind')=='native_request'and e.get('method')=='POST'and e.get('path')=='/users/sign_in']
  initial=any(e.get('kind')=='capture'and e.get('account_id')==private['initial_id']for e in events)
  checks.update(initial_account_observed=initial,actual_sign_out_then_native_sign_in=bool(signedout and login and min(signedout)<max(login)),distinct_requested_account_authenticated=v.get('account_id')==private['target_id']and private['initial_id']!=private['target_id'],password_was_independently_qualified=private.get('password_verified')is True)
 elif operation=='blank_description':checks.update(blank_checks(private,captures,reply))
 else:
  drawer=v.get('drawer');text=drawer.get('text','')if isinstance(drawer,dict)else''
  checks.update(native_whats_new_drawer_visible=isinstance(drawer,dict)and drawer.get('visible')is True,
   complete_latest_local_release_titles_visible=all(card['title']in text for card in private['cards']),
   complete_latest_local_release_bodies_visible=all(visible_text(card['description'])in visible_text(text)for card in private['cards']))
 passed=all(checks.values());return {'version':VERSION,'status':'success'if passed else'failure','reward':float(passed),'checks':checks,'private_reference_values_in_feedback':False}

def posterior_feedback(j):return {'status':j['status'],'reward':j['reward'],'checks':[{'name':k,'passed':v}for k,v in j.get('checks',{}).items()],'reference_values_provided':False,'action_sequence_provided':False}
