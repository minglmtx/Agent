"""Native offline group-import terminal predicate for explicit training tasks.

This module does not choose actions or turn a native capability receipt into
actor admission. Metadata-only export/import is not cross-instance project
or repository migration.
"""
from copy import deepcopy
import hashlib
import re
from .site_navigation_rules import valid_initial_page
from .source_revision_binding import binding

VERSION = 'gitlab-local-group-import-v1'
PROJECTION_KEYS = {'description', 'labels', 'milestones', 'members', 'project_count'}


def validate_reference(reference):
    if (not isinstance(reference, dict) or reference.get('native_export_service_used') is not True
            or reference.get('projects_included') is not False
            or not re.fullmatch('[0-9a-f]{64}', reference.get('asset_sha256', ''))
            or type(reference.get('bytes')) is not int or not 0 < reference['bytes'] <= 20_000_000):
        raise ValueError('Pinned native metadata export reference required')
    projection(reference.get('expected'))
    if reference['expected']['project_count'] != 0:
        raise ValueError('Project migration is outside this declared metadata task')


def projection(value):
    if not isinstance(value, dict) or set(value) != PROJECTION_KEYS:
        raise ValueError('Complete native metadata projection required')
    if not isinstance(value['description'], str) or type(value['project_count']) is not int or value['project_count'] < 0:
        raise ValueError('Invalid native description or project count')
    for field, width in [('labels', 3), ('milestones', 4), ('members', 2)]:
        rows = value[field]
        if not isinstance(rows, list):raise ValueError('Missing native relation: '+field)
        for row in rows:
            if not isinstance(row, list) or len(row) != width or not isinstance(row[0], str) or not row[0]:
                raise ValueError('Malformed native relation: '+field)
            if field == 'members':
                if type(row[1]) is not int:raise ValueError('Native member permission required')
            elif any(x is not None and not isinstance(x, str) for x in row[1:]):
                raise ValueError('Native relation values must be recorded text or null')
        if len({row[0] for row in rows}) != len(rows):raise ValueError('Ambiguous native relation identities')
    return {**value, **{key: sorted(value[key], key=lambda r:r[0]) for key in ('labels','milestones','members')}}


def validate_contract(contract):
    binding(contract)
    spec = contract.get('group_import')
    if (contract.get('domain') != 'gitlab' or not isinstance(spec, dict)
            or set(spec) != {'version', 'name', 'path', 'visibility_level', 'asset_sha256', 'scope'}
            or spec['version'] != VERSION or spec['scope'] != 'native_local_group_metadata'
            or contract.get('original_benchmark_equivalence') is not False
            or contract.get('is_explicit_derivative') is not True
            or type(spec['visibility_level']) is not int or spec['visibility_level'] not in (0,10,20)
            or not isinstance(spec['name'], str) or not spec['name'].strip()
            or not re.fullmatch(r'[a-z][a-z0-9-]{0,100}', spec['path'])
            or not re.fullmatch('[0-9a-f]{64}', spec['asset_sha256'])):
        raise ValueError('Explicit metadata-only local group import contract required')
    return spec


def verify_asset(contract, reference, path):
    from pathlib import Path
    spec=validate_contract(contract);validate_reference(reference);path=Path(path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError('Regular absolute local group-export asset required')
    if path.stat().st_size != reference['bytes'] or path.stat().st_size > 20_000_000:
        raise ValueError('Native group export size mismatch')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != reference['asset_sha256'] or digest != spec['asset_sha256']:
        raise ValueError('Native group export bytes do not match the declared task')


def evaluate(contract, reference, page, initial, final, *, site_origin,
             finished_status, pending_statuses, runtime_error=None):
    """One terminal comparison. Pending/failed infrastructure stays unscored.

    Caller supplies an installed-native enum mapping and complete private state.
    A page title or successful redirect is never sufficient proof of import.
    """
    def unknown(reason):
        return dict(version=VERSION,status='unknown',reward=None,checks={},reason=reason)
    if runtime_error:return unknown('Environment or inference error')
    try:
        spec=validate_contract(contract);validate_reference(reference)
        if reference['asset_sha256'] != spec['asset_sha256']:raise ValueError('Reference belongs to another asset')
        if type(finished_status) is not int or not isinstance(pending_statuses, (list,tuple)) or any(type(x)is not int for x in pending_statuses) or finished_status in pending_statuses:
            raise ValueError('Explicit native import state mapping required')
        for state in (initial,final):
            if not isinstance(state,dict) or set(state) != {'groups','project_fingerprint','target'}:
                raise ValueError('Complete terminal group state required')
            if not isinstance(state['groups'],list) or not re.fullmatch('[0-9a-f]{64}',state['project_fingerprint']):
                raise ValueError('Complete group and project protection required')
            for row in state['groups']:
                if set(row)!={'id','md5'} or type(row['id'])is not int or not re.fullmatch('[0-9a-f]{32}',row['md5']):
                    raise ValueError('Malformed native group protection')
            if len({r['id']for r in state['groups']})!=len(state['groups']):raise ValueError('Duplicate native group identity')
        if initial['target'] is not None:raise ValueError('Target already present at task start')
        if not isinstance(page,dict) or type(page.get('http_status'))is not int or not 200 <= page['http_status'] < 500:
            raise ValueError('Missing terminal document or transport failure')
        old={r['id']:r for r in initial['groups']};new={r['id']:r for r in final['groups']}
        added=set(new)-set(old);target=final['target']
        checks=dict(page_valid=valid_initial_page(page,site_origin=site_origin),
                    existing_groups_unchanged=all(new.get(k)==v for k,v in old.items()),
                    existing_projects_unchanged=initial['project_fingerprint']==final['project_fingerprint'],
                    exactly_one_group_created=len(added)==1,target_exists=target is not None)
        if target is not None:
            if not isinstance(target,dict)or set(target)!={'identity','projection','native_import_states'}:
                raise ValueError('Complete persisted target required')
            ident=target['identity']
            if not isinstance(ident,dict)or set(ident)!={'id','name','path','description','visibility_level'}:
                raise ValueError('Complete persisted target identity required')
            if type(ident['id'])is not int or ident['id'] not in new or type(ident['visibility_level'])is not int:
                raise ValueError('Target identity not present in native namespace snapshot')
            actual=projection(target['projection'])
            if ident['description']!=actual['description']:raise ValueError('Target description/projection differ')
            imports=target['native_import_states']
            if not isinstance(imports,list):raise ValueError('Missing native import states')
            for row in imports:
                if set(row)!={'group_id','user_id','status','jid'} or any(type(row[k])is not int for k in ('group_id','user_id','status')):
                    raise ValueError('Malformed native import state')
                if row['group_id']!=ident['id'] or not isinstance(row['jid'],str) or not row['jid']:
                    raise ValueError('Native import record belongs to another object')
            if any(r['status'] in pending_statuses for r in imports):return unknown('Native import is still pending after bounded settlement')
            if any(r['status'] != finished_status for r in imports):return unknown('Native import reported an unsuccessful state; inspect native worker')
            checks.update(target_is_new=ident['id'] in added,requested_name=ident['name']==spec['name'],
                          requested_path=ident['path']==spec['path'],requested_visibility=ident['visibility_level']==spec['visibility_level'],
                          native_import_finished=len(imports)==1,
                          exported_metadata_preserved=actual==projection(reference['expected']))
        passed=all(checks.values())
        return dict(version=VERSION,status='success'if passed else'failure',reward=float(passed),checks=checks,reason=None)
    except (ValueError,KeyError,TypeError) as error:return unknown(str(error))


def feedback(result):
    return dict(status=result['status'],reward=result['reward'],reason=result.get('reason'),
                checks=[dict(condition=k,passed=v)for k,v in result['checks'].items()],
                reference_values_provided=False,action_sequence_provided=False)
