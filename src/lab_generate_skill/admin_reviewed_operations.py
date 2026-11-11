"""Two source-bound native operations; private capture and terminal checks only."""
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit
import hashlib,json

VERSION='admin-reviewed-date-design-v1'
KIND='reviewed_admin_operation'
DATE='7dfd7947cbf21b1561b6'
DESIGN='c8de5316f4877a385aa2'
PAGE_KEY='reviewed_date_filter_evidence'

@lru_cache(maxsize=1)
def _definitions():
    data=json.loads((Path(__file__).resolve().parents[2]/'configs/admin-reviewed-operations-v1.json').read_text())
    if data.get('version')!=VERSION or {x['source_task_id']for x in data['tasks']}!={DATE,DESIGN}or len(data['tasks'])!=2:
        raise ValueError('Exact reviewed date/design source definitions required')
    return {x['source_task_id']:x for x in data['tasks']}

def definition(source):return deepcopy(_definitions().get(source))

def runtime_id(contract):
    digest=hashlib.sha256(json.dumps(contract,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:12]
    return contract['source_task_id']+'@reviewed-operation-'+digest

def source_row(contract):
    return dict(source_task_id=contract['source_task_id'],source_goal=contract['original_goal'],
                goal=contract['goal'],kind='derived',runtime_task_id=runtime_id(contract))

def bind(row,state,contract):
    if any(row.get(k)!=v for k,v in source_row(contract).items()):
        raise ValueError('Reviewed operation public source definition differs')
    sid=contract['source_task_id']
    if definition(sid)!=contract:raise ValueError('Reviewed operation contract differs')
    if state.get('record_errors'):raise ValueError('Complete initial native evidence required')
    if sid==DESIGN:
        from .admin_saved_design_core import split,MATERIAL
        base,_=split(state)
        if any(r['sku']==MATERIAL['sku']for r in base['records']['product']):
            raise ValueError('Creation target already exists at reset')
    else:
        from .admin_calendar_filter_core import expected_orders
        expected_orders(state)
    spec=dict(kind=KIND,source_task_id=sid,operation=contract['operation'])
    if sid==DATE:spec['required_grid_operation']=deepcopy(contract['required_grid_operation'])
    return dict(source_task_id=sid,runtime_task_id=runtime_id(contract),goal=contract['goal'],kind='derived',
                scope_id=0,start_path=contract['start_path'],status='ready_for_single_attempt',spec=spec,
                task_revision=dict(version=VERSION,source_task_id=sid,source_goal=contract['original_goal'],
                    runtime_goal=contract['goal'],reason=contract['derivation_reason'],
                    contains_reference_answer=False,contains_action_sequence=False,equivalent_to_original=False))

def extend_capture(value,site,project,root,source):
    if source!=DESIGN:return value
    from .admin_saved_design_core import capture
    return capture(site,project,root,lambda:value)

def orders_grid_path(url):
    # Both routes are native Magento Orders index endpoints. Do not accept
    # arbitrary deeper paths, another grid or another host via this predicate.
    return urlsplit(url).path.rstrip('/') in ('/admin/sales/order','/admin/sales/order/index')

def settled_order_grid(grid):
    from .admin_calendar_grid_checks import PROTOCOL
    if (not isinstance(grid,dict) or grid.get('protocol')!=PROTOCOL or grid.get('probe_error')
            or not isinstance(grid.get('provider'),dict)):
        raise ValueError('Native Orders provider unavailable')
    p=grid['provider'];params=p.get('params');rows=p.get('row_ids');total=p.get('total_records')
    if (not isinstance(params,dict) or params.get('namespace')!='sales_order_grid'
            or not isinstance(params.get('filters'),dict)
            or not isinstance(rows,list) or any(not isinstance(x,str)or not x.isdecimal()for x in rows)
            or len(rows)!=len(set(rows)) or type(total)is not int or total<len(rows)
            or p.get('loading')is not False or p.get('last_error')is not False):
        raise ValueError('Native Orders provider incomplete or pending')
    receipts=grid.get('receipts')
    if not isinstance(receipts,list)or not receipts:raise ValueError('No completed Orders response')
    r=receipts[-1]
    if (not isinstance(r,dict)or r.get('response_valid')is not True
            or type(r.get('status'))is not int or not 200<=r['status']<300
            or not isinstance(r.get('params'),dict)
            or r.get('row_ids')!=rows or r.get('total_records')!=total):
        raise ValueError('Orders response not applied to current provider')
    return True

def extend_page_probe(page,result):
    spec=getattr(page,'_admin_ui_spec',{})
    if spec.get('kind')!=KIND or spec.get('source_task_id')!=DATE:return result
    # An ordinary wrong page is an observable noncompletion. Never navigate it
    # to obtain private evidence, and never reveal this provider data to Actor.
    if not orders_grid_path(result['url']):return result
    try:
        operation=spec['required_grid_operation']
        items=page.evaluate("""name=>{const p=require('uiRegistry').get(name);if(!p)throw Error('provider missing');const data=typeof p.data==='function'?p.data():p.data;return data.items.map(x=>({entity_id:x.entity_id,created_at:x.created_at}));}""",operation['provider'])
        visible=page.locator('table.data-grid tbody tr:visible').all_text_contents()
        result[PAGE_KEY]=dict(provider_items=items,visible_rows=visible)
    except Exception as error:
        result[PAGE_KEY]=dict(capture_error=type(error).__name__)
    return result

def evaluate(binding,before,after,page,answer,runtime_error=None):
    result=dict(version=VERSION,status='unknown',reward=None,checks={},answer=answer,
                official_webarena_score=False,paid_judge_calls=0)
    if runtime_error:return dict(result,reason='runtime_error')
    try:
        if not isinstance(before,dict)or not isinstance(after,dict)or not isinstance(page,dict):
            raise ValueError('Missing final native or page evidence')
        spec=binding['spec'];sid=binding['source_task_id'];contract=definition(sid)
        if contract is None or spec['kind']!=KIND or spec['source_task_id']!=sid or spec['operation']!=contract['operation']:
            raise ValueError('Unexpected source operation binding')
        if any(type(page.get(k))is not bool for k in ('login','page_error'))or not page.get('url'):
            raise ValueError('Incomplete terminal page capture')
        checks=dict(same_local_deployment=urlsplit(page['url']).netloc==binding['site_netloc'],
                    valid_authenticated_page=not(page['login']or page['page_error']))
        if sid==DESIGN:
            from .admin_saved_design_core import evaluate as judge
            raw=judge(before,after)
        else:
            from .admin_calendar_filter_core import expected_orders,judge
            from .admin_calendar_grid_checks import checks as grid_checks
            if before.get('record_errors')or after.get('record_errors'):raise ValueError('Incomplete native record capture')
            expected_orders(before)
            if before['records']!=after['records']or before['display_timezone']!=after['display_timezone']:
                raise ValueError('Native read-only state changed')
            checks['correct_orders_grid']=orders_grid_path(page['url'])
            if not all(checks.values()):return dict(result,status='failure',reward=0.0,checks=checks,reason=None)
            grid=page['ui_contract']['grid_operation']
            if spec['required_grid_operation']!=contract['required_grid_operation']:raise ValueError('Date filter parameters changed')
            operation_checks=grid_checks(spec['required_grid_operation'],grid)
            # A complete settled native provider can positively show that the
            # required date filter is absent. Full date-result capture is needed
            # to prove the filtered result, not to negate a missing prerequisite.
            # Missing/pending/incorrect provider evidence remains unknown.
            if operation_checks['requested_grid_parameters_current'] is False:
                settled_order_grid(grid)
                checks.update(operation_checks)
                return dict(result,status='failure',reward=0.0,checks=checks,reason=None)
            evidence=page.get(PAGE_KEY)
            if not isinstance(evidence,dict)or evidence.get('capture_error'):raise ValueError('Missing full date-filter page capture')
            raw=judge(before,after,operation_checks,grid,evidence['provider_items'],evidence['visible_rows'])
        if raw['evaluation_status']=='unknown':return dict(result,reason='native_evidence_unavailable',evidence_error=raw.get('error'))
        if any(type(v)is not bool for v in raw['checks'].values()):raise ValueError('Nonboolean native check')
        checks.update(raw['checks']);passed=all(checks.values())
        return dict(result,status='success'if passed else'failure',reward=float(passed),checks=checks,reason=None)
    except (ValueError,KeyError,TypeError,StopIteration)as error:
        return dict(result,reason='native_evidence_unavailable',evidence_error=type(error).__name__+': '+str(error))
