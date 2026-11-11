"""Strict review-only compatibility with a completed native CPU contract."""
import copy
import json
from pathlib import Path
from lab_generate_skill.reddit_remaining_runtime import VERSION


def bind_normal_contract(normal_contract, *, normal_result_path, admission_path):
    """Add reviewed runtime fields while retaining all original CPU semantics."""
    if not isinstance(normal_contract,dict) or not isinstance(normal_contract.get('native_family'),dict) or normal_contract.get('domain')!='reddit':
        raise ValueError('Original native Reddit normal binding required')
    c=copy.deepcopy(normal_contract)
    c['reddit_native_task']=c.pop('native_family')
    c.update(family='reddit_native_runtime',completion={},runtime_version=VERSION,
             admission_result=str(admission_path),normal_control_result=str(normal_result_path),
             normal_admission=False,shared_runtime_ready=False)
    return c


def require_original_binding(contract,normal_contract,wave):
    """Accept only the exact transformation of this same wave's original binding.

    The shared gate separately checks the proof path, exact terminal job, heldout
    aliases and generation artifacts. This check cannot activate a task. Unknown
    extra fields, removed fields, changed types or source semantics all fail.
    """
    if not isinstance(contract,dict):raise ValueError('Native runtime binding required')
    expected=bind_normal_contract(normal_contract,
        normal_result_path=Path(wave).resolve()/'normal-controls/result.json',
        admission_path=contract.get('admission_result',''))
    if json.dumps(expected,sort_keys=True)!=json.dumps(contract,sort_keys=True):
        raise ValueError('Admission changed the original native normal binding')
