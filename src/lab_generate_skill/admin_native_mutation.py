"""Source-scoped private evidence; no extra observations or action recovery."""
from copy import deepcopy
from functools import lru_cache
import hashlib,json,subprocess
from pathlib import Path
from . import admin_native_mutation_checks as checks

KEY='_native_mutation_evidence'
@lru_cache(maxsize=1)
def _config():
    data=json.loads((Path(__file__).resolve().parents[2]/'configs/admin-native-mutations-v1.json').read_text())
    if data['version']!='admin-native-mutations-v1':raise ValueError('Unknown native mutation configuration')
    ids=[t['source_task_id']for t in data['tasks']]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate native mutation source')
    return data

def definition(source):
    rows=[c for c in _config()['tasks']if c['source_task_id']==source]
    return deepcopy(rows[0])if rows else None

def fixture_source(source):
    from .admin_category_operations import definition as category_definition
    if category_definition(source) is not None:return source
    from .admin_reviewed_operations import definition as reviewed_definition
    reviewed = reviewed_definition(source)
    if reviewed is not None:return reviewed['fixture_source_id']
    if definition(source) is not None:return _config()['fixture_source_id']
    from .admin_material_creation import fixture_source as original
    return original(source)

def combine(payload):
    base=deepcopy(payload['base'])
    if KEY in base:raise ValueError('Native evidence key collision')
    base[KEY]=deepcopy(payload['native'])
    return base

def split(state):
    if not isinstance(state,dict)or KEY not in state:raise ValueError('Missing private native evidence')
    return {'base':{k:v for k,v in state.items()if k!=KEY},'native':state[KEY]}

def extend_capture(value,site,project,root,source):
    if definition(source)is None:return value
    if KEY in value:raise ValueError('Native evidence key collision')
    state=Path(site.temp.name)/'webarena-admin'
    command=['apptainer','exec','--cleanenv','--containall','--no-home','--no-mount','bind-paths,hostfs,cwd',
      '--pwd','/','--bind',str(state)+':/state','--bind',str(state/'app')+':/var/www/magento2',
      '--bind',str(project/'cluster/admin-native-mutation-state.php')+':/native-read.php:ro',
      str(root/'containers/webarena/shopping-admin.sif'),'php','/native-read.php']
    result=subprocess.run(command,capture_output=True,text=True,timeout=45)
    if result.returncode:raise RuntimeError('native_state_capture_failed')
    native=json.loads(result.stdout)
    if not isinstance(native,dict)or set(native)!={'stock','synonyms','design','themes'}or any(not isinstance(v,list)for v in native.values()):
        raise ValueError('Incomplete private native capture')
    return combine({'base':value,'native':native})

def runtime_id(contract):
    if not contract['derived']:return contract['source_task_id']
    digest=hashlib.sha256(json.dumps(contract,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:12]
    return contract['source_task_id']+'@derived-native-'+digest

def bind(row,state,contract):
    expected_kind='derived'if contract['derived']else 'original'
    if (row.get('goal')!=contract['goal']or row.get('source_goal')!=contract['original_goal']
        or row.get('kind')!=expected_kind or row.get('runtime_task_id')!=runtime_id(contract)):
        raise ValueError('Native task public definition differs')
    private=split(state)
    if contract['operation']in('stock_threshold','duplicate_product'):
        checks.only([p for p in private['base']['records']['product']if p['sku']==contract['source_sku']])
    revision=None
    if contract['derived']:
        revision=dict(version='admin-native-mutations-v1',source_task_id=contract['source_task_id'],
          source_goal=contract['original_goal'],runtime_goal=contract['goal'],
          reason='Declare parameters of the locally demonstrated operation.',
          contains_reference_answer=False,contains_action_sequence=False,equivalent_to_original=False)
    return dict(source_task_id=contract['source_task_id'],runtime_task_id=runtime_id(contract),
      goal=contract['goal'],kind=expected_kind,scope_id=0,start_path=contract['declared_local_start_path'],
      status='ready_for_single_attempt',task_revision=revision,
      spec=dict(kind='native_mutation',native_contract=deepcopy(contract)))

def evaluate(binding,before,after,page,answer,runtime_error=None):
    unknown=dict(version=checks.VERSION,status='unknown',reward=None,checks={},answer=answer,
      official_webarena_score=False,paid_judge_calls=0)
    if runtime_error:return dict(unknown,reason='runtime_error')
    try:
        # The origin is the actual isolated site, never taken from the final page.
        site_netloc=binding['site_netloc']
        origin='http://'+site_netloc
        result=checks.evaluate(binding['spec']['native_contract'],split(before),split(after),page,origin)
        return dict(result,answer=answer,official_webarena_score=False,paid_judge_calls=0)
    except (ValueError,TypeError,KeyError)as exc:
        return dict(unknown,reason=type(exc).__name__+':'+str(exc))
