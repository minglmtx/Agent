"""Reuse native evidence for an explicitly revised description predicate.

This is offline requalification, not evidence that an actor has executed the
new goal. Original receipts remain immutable and their full gate runs first.
"""
from copy import deepcopy
import importlib.util
from pathlib import Path

from .gitlab_project_description import revise_contract
from .source_revision_binding import binding, fingerprint


def require_revision(original, candidate):
    binding(original)
    binding(candidate)
    expected = revise_contract(original)
    expected['task_id'] = original['source_task_id'] + '--observed-process-v3'
    if candidate != expected:
        raise ValueError('Revision changes more than the declared description contract')
    if (candidate.get('training_admitted') is not False
            or candidate.get('normal_gate_passed') is not False):
        raise ValueError('Offline qualification cannot declare training admission')
    return {'original_contract_sha256': fingerprint(original),
            'candidate_contract_sha256': fingerprint(candidate),
            'source_task_id': candidate['source_task_id']}


def qualify(original, candidate, cycles, directories, *, original_driver, candidate_component):
    identity = require_revision(original, candidate)
    # The original driver verifies the original actual goal/AX, native sources,
    # every table/reference guard, reset generations, and worker cleanup.
    gate = original_driver.require_two_cold(original, cycles, directories)
    if gate.get('passed') is not True:
        raise ValueError('Original complete native gate did not pass')
    candidate_component.enabled(candidate)
    if candidate_component.DOM_READ != original_driver.component.DOM_READ:
        raise ValueError('Changed observation capture requires new native evidence')
    expected = original_driver.expectations(original)
    controls = []
    for number, cycle in enumerate(cycles):
        if set(cycle['controls']) != set(expected):
            raise ValueError('All original controls are required')
        for name, row in cycle['controls'].items():
            # Deep copies ensure a candidate cannot mutate the retained proof.
            actual = candidate_component.evaluate(deepcopy(candidate),
                deepcopy(row['private_reference']), deepcopy(row['terminal']),
                deepcopy(row['captures']), deepcopy(row['events']), row['site_origin'])
            if actual != row['judgment'] or actual.get('status') != expected[name]:
                raise ValueError('Revised predicate changes an original control: ' + name)
            controls.append({'cold': number, 'control': name, 'status': actual['status'],
                             'checks': actual['checks']})
    return dict(identity, original_native_gate=gate, controls=controls,
        qualification='original_full_gate_and_revised_predicate_verified',
        original_receipts_rewritten=False, changed_goal_executed=False,
        current_actor_required=True, training_admitted=False, api_calls=0)


def bind_driver(original_driver, candidate_component, original, candidate):
    """Bind the ordinary native lifecycle to a qualified revised predicate.

    Load the already frozen driver into a separate namespace: changing a global
    on the original module would also alter the code verifying old receipts.
    The caller must freeze/pin these modules through its regular bootstrap.
    This does not bypass scheduling, reservations, or actor-attempt claims.
    """
    require_revision(original, candidate)
    path = Path(original_driver.__file__)
    if not path.is_file() or path.is_symlink():
        raise ValueError('A frozen original driver file is required')
    specification = importlib.util.spec_from_file_location(
        original_driver.__name__ + '_description_revision', path)
    driver = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(driver)
    # The ordinary lifecycle has no new navigation policy or synthetic actions.
    if not callable(getattr(driver, 'make_hooks', None)):
        raise ValueError('Original ordinary hook factory is required')
    original_contract, revised_contract = deepcopy(original), deepcopy(candidate)
    driver.component = candidate_component

    def require_qualified(contract, cycles, directories):
        if contract != revised_contract:
            raise ValueError('Runtime task differs from the qualified revision')
        value = qualify(original_contract, revised_contract, cycles, directories,
                        original_driver=original_driver,
                        candidate_component=candidate_component)
        return dict(value, passed=True, normal_gate_passed=False)

    driver.require_two_cold = require_qualified
    return driver


def public_answer_fields(contract):
    """Only the explicitly public record schema, never a reference answer."""
    declaration = contract.get('public_parameters', {}).get('description_format')
    if (not isinstance(declaration, dict) or not declaration
            or any(not isinstance(k, str) or not k.strip()
                   or v != 'ordered records with operation and ui_label'
                   for k, v in declaration.items())):
        raise ValueError('Explicit public ordered-record response schema required')
    return {name: 'record_set' for name in declaration}
