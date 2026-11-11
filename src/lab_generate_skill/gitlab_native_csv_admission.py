"""Formal CSV gate over complete native evidence; never a browser action policy.

The raw producer result is a capability proof. Only an original, qualified
scope may reuse its matching full two-fresh proof. An unqualified collection
cannot inherit an Open-only reference without a separately reviewed protocol.
No admission flag, source reward, queued request or local-mail receipt alone
is evidence of a complete export.
"""
import copy
import re
from urllib.parse import urlsplit

from .gitlab_native_csv_probe import PROTECTED_TABLES, terminal_judgment

VERSION = 'gitlab-native-csv-formal-evidence-gate-v1'
CONTROLS = {'positive','wrong_native_project','wrong_native_closed_filter','no_op',
    'queued_without_attachment','wrong_user_reference','wrong_collection_receipt',
    'truncated_receipt','missing_column','missing_row','altered_field','404','anonymous_login'}
CHAIN_FILES = {'app/models/issue.rb','app/models/work_items/type.rb',
    'app/controllers/projects/issues_controller.rb','app/workers/issuable_export_csv_worker.rb',
    'app/finders/issues_finder.rb','app/finders/merge_requests_finder.rb',
    'app/services/issues/export_csv_service.rb','app/services/merge_requests/export_csv_service.rb',
    'app/services/issuable/export_csv/base_service.rb','app/mailers/emails/issues.rb',
    'app/mailers/emails/merge_requests.rb','lib/csv_builder.rb'}


class ScopeProtocolUnproven(ValueError):
    pass


def full_snapshot(value):
    if not isinstance(value,dict) or set(value)!=set(PROTECTED_TABLES):
        raise ValueError('Every complete native protected table is required')
    for record in value.values():
        if (not isinstance(record,dict) or set(record)!={'rows','columns','key','sha256'}
                or type(record['rows'])is not int or record['rows']<0
                or not isinstance(record['columns'],list) or not record['columns']
                or not all(isinstance(x,str)and x for x in record['columns'])
                or len(set(record['columns']))!=len(record['columns'])
                or not isinstance(record['key'],list) or not record['key']
                or not set(record['key'])<=set(record['columns'])
                or not isinstance(record['sha256'],str)
                or not re.fullmatch('[0-9a-f]{64}',record['sha256'])):
            raise ValueError('Full native column/key/row fingerprint is incomplete')


def _require_controls(case, proof, *, native_baseline, state, controls, revision=False):
    """Derive the gate from actual raw results, not cached passed/admitted bits.

    This is deliberately the scope of the currently executed CPU proof. The
    unqualified MR original remains in scope, but cannot yet use this gate.
    """
    # The running native factory supplies this independent, complete pre-model
    # snapshot. Never derive the schema trust anchor from the proposed proof.
    full_snapshot(native_baseline)
    if (not isinstance(case,dict) or not case.get('source_task_id')
            or not isinstance(case.get('goal'),str) or not case['goal']
            or not isinstance(case.get('recorded_start_paths'),list)
            or not case['recorded_start_paths'] or case.get('start_path')!=case['recorded_start_paths'][0]
            or case.get('native_default_state')!=state):
        raise ValueError('Unchanged original first context and executed native scope required')
    if case.get('original_scope_protocol_requires_review')is not False:
        raise ScopeProtocolUnproven('The unqualified original must retain its scope-review gap')
    if (not isinstance(proof,dict) or proof.get('status')!='complete'
            or any(type(proof.get(k))is not int or proof[k]!=0 for k in ('actor_attempts','api_calls','task_admissions'))
            or proof.get('normal_bindings_written')is not False):
        raise ValueError('Actual complete zero-model raw CPU evidence is required')
    cycles=proof.get('cycles')
    if not isinstance(cycles,list)or len(cycles)!=2:
        raise ValueError('Two complete fresh cycles are required')
    baselines=[];references=[];chains=[]
    for cycle in cycles:
        if (cycle.get('completed')is not True or cycle.get('protected_records_unchanged')is not True
                or cycle.get('bound_account_auth_metadata_restored_exactly')is not True
                or cycle.get('all_existing_jobs_preserved')is not True
                or any(type(cycle.get(k))is not int or cycle[k]!=0 for k in ('actor_attempts','api_calls','task_admissions'))):
            raise ValueError('Native restoration, complete queue and zero-model evidence required')
        full_snapshot(cycle['initial_protected']);full_snapshot(cycle['final_protected'])
        if cycle['initial_protected']!=cycle['final_protected']:
            raise ValueError('A protected row or column changed')
        rows=[row for row in cycle.get('cases',[])if row.get('source_task_id')==case['source_task_id']]
        if len(rows)!=1:raise ValueError('Exact original source evidence missing or duplicated')
        row=rows[0]
        if (row.get('original_goal')!=case.get('original_goal',case['goal']) or row.get('original_start_path')!=case['start_path']
                or row.get('original_context_before_private_discovery')is not True
                or row.get('original_scope_protocol_requires_review')is not False
                or row.get('consumer_failure')is not None
                or row.get('native_ui_producers_complete')is not True
                or row.get('native_delivery_received')is not True
                or set(row.get('controls',{}))!=controls
                or any(v is not True for v in row['controls'].values())):
            raise ValueError('All original-context native positive and negative controls required')
        if revision and (row.get('native_export_state')!=state or row.get('task_version_goal')!=case['goal'] or row.get('task_revision')!=case['task_revision']):
            raise ValueError('Actual complete All task-version proof required; Open results cannot qualify')
        native=cycle.get('native_chain_sha256')
        if (not isinstance(native,dict) or set(native)!=CHAIN_FILES
                or any(not isinstance(v,str)or not re.fullmatch('[0-9a-f]{64}',v)for v in native.values())):
            raise ValueError('Unchanged complete native export chain is required')
        reference=cycle.get('private_reference_set',{}).get(case['source_task_id'])
        if not isinstance(reference,dict)or len(reference.get('rows',[]))!=case['actual_native_selected_count']:
            raise ValueError('Actual full UI selection and independent reference disagree')
        baselines.append(cycle['initial_protected']);references.append(reference);chains.append(native)
    if baselines[0]!=native_baseline:
        raise ValueError('Complete running native baseline/schema differs from the proposed proof')
    if baselines[0]!=baselines[1] or references[0]!=references[1] or chains[0]!=chains[1]:
        raise ValueError('Independent fresh instance or reference changed')
    return {'version':VERSION,'source_task_id':case['source_task_id'],
            'native_state':state,'baseline':copy.deepcopy(baselines[0]),
            'private_reference':copy.deepcopy(references[0]),'native_chain':copy.deepcopy(chains[0]),
            'fresh_cycles':2,'normal_binding_created':False,'actor_attempts':0,'api_calls':0}


def require_original_open_controls(case, proof, *, native_baseline):
    return _require_controls(case,proof,native_baseline=native_baseline,state='opened',controls=CONTROLS)


ALL_REVISION='explicit-all-native-merge-request-export-v1'
ALL_CONTROLS=(CONTROLS-{'wrong_native_closed_filter'})|{'wrong_native_open_filter'}


def require_all_revision_controls(case,proof,*,native_baseline):
    # This named protocol does not claim equivalence to the unqualified source.
    if (case.get('task_revision')!=ALL_REVISION or
        case.get('original_goal')!='Export the list of merge requests as a CSV file.' or
        case.get('goal')!='Export all merge requests in the current project as a CSV file.' or
        case.get('target',{}).get('collection')!='merge_requests' or
        case.get('eligible_for_training')is not False or case.get('original_scope_gap_preserved')is not True):
        raise ScopeProtocolUnproven('Explicit complete All revision with retained original scope gap required')
    return _require_controls(case,proof,native_baseline=native_baseline,state='all',controls=ALL_CONTROLS,revision=True)


def require_scope_controls(case,proof,*,native_baseline):
    if case.get('native_default_state')=='all':
        return require_all_revision_controls(case,proof,native_baseline=native_baseline)
    return require_original_open_controls(case,proof,native_baseline=native_baseline)


def terminal_feedback(judgment):
    """Only posterior check outcomes; no private records or action instructions."""
    return {'status':judgment['status'],'reward':judgment['reward'],
            'checks':[{'name':key,'passed':value}for key,value in judgment.get('checks',{}).items()],
            'private_reference_values_provided':False,'action_sequence_provided':False}


def reference_for_native_origin(reference, site_origin):
    """Bind the canonical proof to the trusted running factory, never MIME data."""
    if not isinstance(site_origin,str) or any(c.isspace()for c in site_origin):
        raise ValueError('Trusted running native site origin required')
    origin=urlsplit(site_origin)
    if (origin.scheme not in ('http','https') or not origin.netloc or not origin.hostname
            or origin.username is not None or origin.password is not None or origin.path not in ('','/')
            or origin.query or origin.fragment):
        raise ValueError('Trusted running native origin must not contain a page or credentials')
    # Validate the port too. Binding never guesses a host or port from output.
    origin.port
    bound=copy.deepcopy(reference)
    for row in bound['rows']:
        value=row.get('URL');parsed=urlsplit(value)if isinstance(value,str)else None
        if (parsed is None or parsed.scheme!='local' or parsed.netloc
                or not parsed.path.startswith('/') or parsed.path.startswith('//')
                or not value.startswith('local:/')):
            raise ValueError('Canonical independent record URL missing')
        row['URL']=site_origin.rstrip('/')+value[len('local:'):]
    return bound


def score_received(gate, received, *, site_origin, page_valid=True, runtime_error=False,
                   complete_state_preserved=True, complete_prior_queue_preserved=True):
    if gate.get('version')!=VERSION:raise ValueError('Reviewed complete native gate required')
    if runtime_error or not complete_state_preserved or not complete_prior_queue_preserved:
        return {'status':'unknown','reward':None,'checks':{},'reason':'Native runtime or full protection incomplete'}
    reference=reference_for_native_origin(gate['private_reference'],site_origin)
    return terminal_judgment(received,reference,page_valid=page_valid)
