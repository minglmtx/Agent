"""Join original template controls with independently reset missing branches.

Archives are restored and hash-checked by the frozen caller. Historical failed
cycles remain intact; this validator reads their completed branches directly.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import re

VERSION = 'native-template-retained-controls-supplement-v1'
REASON = 'Qualify and publicly supply the explicitly selected native local repository template before inference.'
HISTORICAL_REASONS = {
    REASON,
    'Qualify and publicly supply an actual local basic static repository template before inference.',
    'Qualify and publicly supply an actual requested local Django repository template before inference.',
}


def canonical_contract(contract):
    """Normalize only the reviewed initialization and explanatory metadata.

    Public goal, selected template, namespace and all source bindings remain
    exact. In particular this cannot substitute Plain HTML for a Django task.
    """
    c = deepcopy(contract)
    if (c.get('family') != 'native_repository_template'
            or c.get('driver_key') != 'gitlab-remaining'
            or c.get('gitlab_cache_initialization') not in (None, 'wiki_issue')
            or c.get('public_parameters_revision', {}).get('reason') not in HISTORICAL_REASONS):
        raise ValueError('Unreviewed template materialization metadata')
    c['gitlab_cache_initialization'] = 'wiki_issue'
    c['public_parameters_revision']['reason'] = REASON
    return c


def require_supplement(driver, case, groups):
    if case.get('family') != 'native_repository_template' or not isinstance(groups, list) or len(groups) != 2:
        raise ValueError('Two native template control/supplement groups required')
    contracts, references, baselines, original_ids, new_ids = [], [], [], [], []
    first = None

    def read(directory, name):
        return driver.read(driver.artifact(Path(directory), name))

    for cold, group in enumerate(groups):
        old, new = Path(group['controls_directory']), Path(group['supplement_directory'])
        old_c = read(old, 'materialized-contract.json')
        new_c = read(new, 'materialized-contract.json')
        c = canonical_contract(new_c)
        driver._materialization_matches(case, c)
        if (canonical_contract(old_c) != c
                or driver.public.render(old_c) != driver.public.render(c)
                or driver.public.render(new_c) != driver.public.render(c)):
            raise ValueError('Public task/template changed across evidence groups')
        private = read(old, 'private-reference.json')
        if private != read(new, 'private-reference.json'):
            raise ValueError('Independent native template reference changed')
        report = read(new, 'report.json')
        if (report.get('source_task_id') != c['source_task_id'] or report.get('cold') != cold
                or report.get('parent_archive_sha256') != group.get('controls_archive_sha256')
                or not re.fullmatch('[0-9a-f]{64}', group.get('controls_archive_sha256', ''))
                or report.get('actor_attempts') != 0 or report.get('api_calls') != 0
                or report.get('training_admitted') is not False
                or report.get('native_supplement_passed') is not True
                or report.get('checks') != {'prepared_baseline_matches_original': True,
                    'final_reset_and_private_reference_match': True, 'site_closed': True}
                or 'error_type' in report or 'cleanup_error_type' in report
                or not re.fullmatch('[0-9a-f]{64}', report.get('fresh_instance_id', ''))):
            raise ValueError('Supplement source, lifecycle or archive binding differs')
        missing = {'unsaved', 'wrong_template'}
        if {v['name'] for v in report['controls']} != missing or len(report['controls']) != 2:
            raise ValueError('Both missing branches must be present exactly once')
        retained, supplements = [], []
        for name, expected in driver.expectations(old_c).items():
            folder = (new if name in missing else old) / name
            row = read(folder, 'native-private-receipt.json')
            driver.require_control(new_c if name in missing else old_c, row, expected, folder)
            if row['private_reference'] != private:
                raise ValueError('Control source reference changed')
            state = tuple(row[k] for k in ('native_before_initialization', 'protected_before', 'refs_before'))
            if name in missing:
                driver._reset(read(new, 'reset-' + name + '.json'))
                supplements.append(state)
                if first is None:
                    first = row  # Actual prepared-state receipt, never a fabricated cycle.
            else:
                retained.append(state)
        if len(retained) != 5 or len(supplements) != 2 or any(v != retained[0] for v in retained):
            raise ValueError('Original controls do not cover the same baseline')
        expected = (retained[0][1], retained[0][1], retained[0][2])
        prepared = read(new / 'prepared-baseline', 'state.json')
        driver.shared.verify_initialization(new / 'prepared-baseline', prepared)
        if (tuple(prepared[k] for k in ('native_before_initialization', 'protected_before', 'refs_before')) != expected
                or any(v != expected for v in supplements)):
            raise ValueError('Prepared native state differs from original post-initialization state')
        final = read(new, 'final-reset.json')
        driver._reset(final)
        driver.shared.verify_initialization(new / 'final-reset', {
            'native_before_initialization': final['cold'], 'protected_before': final['before'],
            'native_initialization_effects': final['effects']})
        if (final['cold'], final['before'], final['refs']) != expected or final['private_baseline'] != private['baseline']:
            raise ValueError('Final reset and independent template reference differ')
        cleanup = read(old.parent, 'worker-cleanup.json')
        state = cleanup.get('native_site_state_path', cleanup.get('original_state_path'))
        if (not isinstance(state, str) or not Path(state).is_absolute()
                or cleanup.get('fresh_instance_id') != hashlib.sha256(state.encode()).hexdigest()
                or cleanup.get('state_exists_after_close') is not False
                or cleanup.get('services_stopped') is not True
                or cleanup.get('remaining_process_ids') != []
                or cleanup.get('native_site_exit_completed') is not True):
            raise ValueError('Original worker cleanup not proven')
        original_ids.append(cleanup['fresh_instance_id']); new_ids.append(report['fresh_instance_id'])
        contracts.append(c); references.append(private); baselines.append(expected)
    if (len(set(original_ids + new_ids)) != 4 or contracts[0] != contracts[1]
            or references[0] != references[1] or baselines[0] != baselines[1]):
        raise ValueError('Cold source/initialization isolation or equivalence failed')
    return {'version': VERSION, 'passed': True, 'source_task_id': case['source_task_id'],
            'contract': contracts[0], 'first_control': first,
            'original_control_instance_ids': original_ids, 'supplement_instance_ids': new_ids,
            'historical_cycles_rewritten': False, 'training_admission_written': False,
            'ordinary_controls_per_cold': 7}
