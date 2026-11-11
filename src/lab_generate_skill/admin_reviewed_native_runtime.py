"""Explicit current-runtime binding for preserved native capability evidence.

The caller still re-evaluates the actual saved/unsaved states and reset proof.
A historical actor score never authorizes this handoff.
"""
import hashlib,json
from pathlib import Path
VERSION='admin-reviewed-native-runtime-v1'

def _read(pin):
    p=Path(pin['path']);raw=p.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=pin['sha256']:
        raise ValueError('Current native handoff input changed: '+str(p))
    return json.loads(raw)

def _hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def verify_current_native_handoff(current,certificate,source,row,binding,original,publication):
    pin=current.get('validation',{}).get('reviewed_admin_native_runtime')
    if not pin:raise ValueError('Current native runtime handoff is absent')
    h=_read(pin)
    if (h.get('version')!=VERSION or h.get('runtime_version')!=current['version']
            or h.get('current_files_sha256')!=current['actor_submission']['files_sha256']):
        raise ValueError('Native handoff belongs to a different runtime')
    records=h.get('sources',[]);selected=[r for r in records if r['source_task_id']==source]
    if len({r['source_task_id']for r in records})!=len(records) or len(selected)!=1:
        raise ValueError('Native source not uniquely registered')
    r=selected[0]
    for key in ('definition','native_review','original_admission','compatibility'):
        if r[key]!=certificate[key]:raise ValueError('Native proof differs: '+key)
        _read(r[key])
    if r['source_row']!=row or r['binding_sha256']!=_hash(binding):
        raise ValueError('Native public goal/start/specification changed')
    if r['initial_state_sha256']!=_hash(original['state']):
        raise ValueError('Native initial state changed')
    validation=_read(h['combined_validation'])
    if not validation.get('passed'):
        raise ValueError('Merged runtime validation did not pass')
    changed={n:d for n,d in current['actor_submission']['files_sha256'].items()
             if {**publication['unchanged_files_sha256'],**publication['changed_files_sha256']}.get(n)!=d}
    tested={**publication['unchanged_files_sha256'],**publication['changed_files_sha256']}
    verify_removed_dependencies(tested,current['actor_submission']['files_sha256'],h.get('reviewed_removed_files',{}))
    if any(h['reviewed_changes'].get(n)!=d for n,d in changed.items()):
        raise ValueError('Native dependency change outside reviewed scope')
    if any(current['actor_submission']['files_sha256'].get(n)!=d
           for n,d in validation['source_files'].items()):
        raise ValueError('Merged runtime differs from tested code')
    # Scope and original source-byte comparisons are bound to the reviewed
    # publication; no task ID alone can override a failed capability check.
    if not r.get('original_operation_start_and_reset_preserved'):
        raise ValueError('Native operation compatibility not established')
    regression=_read(validation['regression'])
    if regression.get('returncode')!=0:
        raise ValueError('Merged runtime regression incomplete')
    return h['version']


def verify_removed_dependencies(tested,current,reviewed):
    """An obsolete dependency may retire only under an exact prior-byte review."""
    removed={n:d for n,d in tested.items()if n not in current}
    if any(reviewed.get(n)!=d for n,d in removed.items()):
        raise ValueError('Native dependency removal outside reviewed scope')
