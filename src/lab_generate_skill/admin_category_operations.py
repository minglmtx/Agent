"""Two explicit local category variants; private initialization and evidence only."""
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit
import hashlib,json,re,subprocess
from .admin_category_rules import SOURCES,identity,edge,position_judgment,query_judgment
VERSION='admin-category-operations-v1';KIND='native_category_operation';PAGE_KEY='native_category_evidence'
@lru_cache(maxsize=1)
def _definitions():
 data=json.loads((Path(__file__).resolve().parents[2]/'configs/admin-category-operations-v1.json').read_text())
 if data.get('version')!=VERSION or len(data['tasks'])!=2 or {r['source_task_id']for r in data['tasks']}!=set(SOURCES):raise ValueError('Exact category source definitions required')
 return {r['source_task_id']:r for r in data['tasks']}
def definition(source):return deepcopy(_definitions().get(source))
def runtime_id(contract):return contract['source_task_id']+'@category-'+hashlib.sha256(json.dumps(contract,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:12]
def source_row(contract):return dict(source_task_id=contract['source_task_id'],source_goal=contract['original_goal'],goal=contract['goal'],kind='derived',runtime_task_id=runtime_id(contract))
def bind(row,state,contract):
 if definition(contract['source_task_id'])!=contract or any(row.get(k)!=v for k,v in source_row(contract).items()):raise ValueError('Category public source definition differs')
 cat,products=identity(state)
 if int(edge(state,cat,products['WSH12'])['position'])!=0 or int(edge(state,cat,products['WT07'])['position'])!=1:raise ValueError('Declared category baseline differs')
 actual=[r for r in state['records']['category_product']if str(r['category_id'])==cat]
 if len(actual)!=2:raise ValueError('Declared category membership differs')
 sid=contract['source_task_id']
 return dict(source_task_id=sid,runtime_task_id=runtime_id(contract),goal=contract['goal'],kind='derived',scope_id=0,start_path=contract['start_path'],status='ready_for_single_attempt',spec=dict(kind=KIND,source_task_id=sid,operation=contract['operation']),task_revision=dict(version=VERSION,source_task_id=sid,source_goal=contract['original_goal'],runtime_goal=contract['goal'],reason=contract['derivation_reason'],contains_reference_answer=False,contains_action_sequence=False,equivalent_to_original=False))
def initialize_fixture(site,contract):
 if definition(site.init_task_id)!=contract:raise ValueError('Source-bound category initialization required')
 state=site.state/'webarena-admin';project=site.project
 command=['apptainer','exec','--cleanenv','--containall','--no-home','--no-mount','bind-paths,hostfs,cwd','--pwd','/','--bind',str(state)+':/state','--bind',str(state/'app')+':/var/www/magento2','--bind',str(project/'cluster/admin-category-fixture.php')+':/fixture.php:ro',str(site.root/'containers/webarena/shopping-admin.sif'),'php','/fixture.php']
 r=subprocess.run(command,capture_output=True,text=True,timeout=180)
 if r.returncode:raise RuntimeError('Native declared category initialization failed')
 receipt=json.loads(r.stdout)
 if receipt.get('passed')is not True or receipt.get('task_operation_precompleted')is not False:raise ValueError('Native category initialization receipt invalid')
 (site.logs/'category-initialization.json').write_text(json.dumps(dict(source_task_id=site.init_task_id,fixture_source_id=contract['fixture_source_id'],receipt=receipt),indent=2)+'\n')
def install(page,binding):
 if binding['spec'].get('kind')!=KIND or binding['spec'].get('operation')!='sku_search':return
 from .admin_category_browser import install as observe
 page._admin_category_receipts=observe(page,'http://'+binding['site_netloc'])
def extend_page_probe(page,result):
 spec=getattr(page,'_admin_ui_spec',{})
 if spec.get('kind')!=KIND or spec.get('operation')!='sku_search':return result
 try:
  # A complete ordinary page with no displayed category grid is a real
  # noncompletion. Failure to read a displayed native grid remains unknown.
  route=bool(re.search(r'^/admin/catalog/category/(?:edit|grid)/id/[0-9]+(?:/|$)',urlsplit(result['url']).path))
  loc=page.locator('#catalog_category_products_table')
  count=loc.count()
  if count>1:raise ValueError('Ambiguous native category grid')
  shown=count==1 and loc.is_visible()
  evidence=dict(category_grid_displayed=bool(route and shown),receipts=deepcopy(getattr(page,'_admin_category_receipts',None)))
  if evidence['category_grid_displayed']:
   from .admin_category_browser import capture
   evidence['view']=capture(page)
  result[PAGE_KEY]=evidence
 except Exception as exc:result[PAGE_KEY]=dict(capture_error=type(exc).__name__)
 return result

def evaluate(binding,before,after,page,answer,runtime_error=None):
 result=dict(version=VERSION,status='unknown',reward=None,checks={},answer=answer,official_webarena_score=False,paid_judge_calls=0)
 if runtime_error:return dict(result,reason='runtime_error')
 try:
  contract=definition(binding['source_task_id']);spec=binding['spec']
  if contract is None or spec!=dict(kind=KIND,source_task_id=contract['source_task_id'],operation=contract['operation']):raise ValueError('Category source binding differs')
  if not isinstance(page,dict)or not page.get('url')or any(type(page.get(k))is not bool for k in ('login','page_error')):raise ValueError('Complete terminal page required')
  identity(before);identity(after)
  checks=dict(same_local_deployment=urlsplit(page['url']).netloc==binding['site_netloc'],valid_authenticated_page=not(page['login']or page['page_error']))
  if contract['operation']=='position':raw=position_judgment(before,after)
  else:
   checks['read_only_state_unchanged']=before==after
   evidence=page.get(PAGE_KEY)
   if not isinstance(evidence,dict)or evidence.get('capture_error')or type(evidence.get('category_grid_displayed'))is not bool or not isinstance(evidence.get('receipts'),list):raise ValueError('Complete native category observation required')
   checks['category_grid_displayed']=evidence['category_grid_displayed']
   if not all(checks.values()):return dict(result,status='failure',reward=0.0,checks=checks,reason=None)
   raw=query_judgment(after,evidence.get('view'),evidence['receipts'])
  if raw['status']=='unknown':return dict(result,reason='native_evidence_unavailable',evidence_error=raw.get('error'))
  checks.update(raw['checks']);success=all(checks.values())
  return dict(result,status='success'if success else'failure',reward=1.0 if success else 0.0,checks=checks,reason=None)
 except (KeyError,ValueError,TypeError,AttributeError)as exc:return dict(result,reason=type(exc).__name__+':'+str(exc))
