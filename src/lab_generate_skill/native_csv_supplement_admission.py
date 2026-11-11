"""Join retained CSV controls to independently captured reset supplements.

The caller restores hash-bound archives into private directories. This gate
recomputes native evidence; it never rewrites historical timed-out cycles.
The returned admission is for an online development attempt, not training.
"""
from pathlib import Path
import hashlib
import re
from urllib.parse import urlsplit

VERSION = 'native-csv-retained-controls-reset-supplement-v1'


def require_supplement(driver, case, groups):
    if case.get('family') != 'native_all_merge_request_csv':
        raise ValueError('This supplemental gate covers native CSV controls only')
    if not isinstance(groups, list) or len(groups) != 2:
        raise ValueError('Two independently captured control/reset groups required')
    contracts, references, baselines, controls_ids, reset_ids = [], [], [], [], []
    first_control = None

    def read(directory, name):
        return driver.read(driver.artifact(Path(directory), name))

    for cold, group in enumerate(groups):
        directory = Path(group['controls_directory'])
        supplement = Path(group['supplement_directory'])
        c = read(directory, 'materialized-contract.json')
        driver._materialization_matches(case, c)
        private = read(directory, 'private-reference.json')
        local = []
        rows = {}
        for name, expected in driver.expectations(c).items():
            row = read(directory / name, 'native-private-receipt.json')
            driver.require_control(c, row, expected, directory / name)
            driver._reset(read(directory, 'reset-' + name + '.json'))
            if row['private_reference'] != private:
                raise ValueError('Control private reference differs')
            local.append((row['native_before_initialization'], row['protected_before'], row['refs_before']))
            rows[name] = row
        if not local or any(v != local[0] for v in local):
            raise ValueError('Original control reset states disagree')
        received = read(directory / 'positive', 'csv-original-native-receipts.json')
        negatives = driver.csv_artifact_negatives(received[0], private['reference'], rows['positive']['site_origin'])
        if (read(directory, 'csv-artifact-negatives.json') != negatives
                or not negatives or any(v['judgment']['status'] != 'failure' for v in negatives.values())):
            raise ValueError('Native MIME negative controls do not recompute')
        cleanup = read(directory.parent, 'worker-cleanup.json')
        state = cleanup.get('native_site_state_path', cleanup.get('original_state_path'))
        if (not isinstance(state, str) or not Path(state).is_absolute()
                or cleanup.get('fresh_instance_id') != hashlib.sha256(state.encode()).hexdigest()
                or cleanup.get('state_exists_after_close') is not False
                or cleanup.get('services_stopped') is not True
                or cleanup.get('remaining_process_ids') != []
                or cleanup.get('native_site_exit_completed') is not True):
            raise ValueError('Original worker cleanup not proven')
        report = read(supplement, 'report.json')
        if (read(supplement, 'contract.json') != c
                or report.get('source_task_id') != c['source_task_id']
                or report.get('cold') != cold or report.get('actor_attempts') != 0
                or report.get('api_calls') != 0 or report.get('training_admitted') is not False
                or report.get('native_reset_supplement_passed') is not True
                or report.get('checks') != {
                    'both_full_states_and_independent_references_match_original': True,
                    'generation_advanced_and_complete_restore': True, 'site_closed': True}
                or 'error_type' in report or 'cleanup_error_type' in report
                or not re.fullmatch('[0-9a-f]{64}', report.get('fresh_instance_id', ''))):
            raise ValueError('Supplement contract/lifecycle does not match')
        driver._reset(read(supplement, 'reset.json'))
        for name in ('before-reset', 'after-reset'):
            folder = supplement / name
            state = read(folder, 'state.json')
            reference = read(folder, 'reference.json')
            driver.shared.verify_initialization(folder, state)
            if ((state['native_before_initialization'], state['protected_before'], state['refs_before']) != local[0]
                    or reference != private['reference']):
                raise ValueError('Supplement baseline differs from original controls')
            raw = read(folder / 'csv-reference', 'native-reference.json')
            invocation = read(folder / 'csv-reference', 'native-invocation.json')
            if invocation.get('returncode') != 0 or not raw.get('rows'):
                raise ValueError('Original native reference capture missing')
            origin = urlsplit(raw['rows'][0]['URL'])
            if driver.native.normalize_reference(raw, origin.scheme + '://' + origin.netloc) != reference:
                raise ValueError('Raw native CSV reference does not recompute')
        contracts.append(c); references.append(private); baselines.append(local[0])
        controls_ids.append(cleanup['fresh_instance_id']); reset_ids.append(report['fresh_instance_id'])
        if first_control is None:
            first_control = rows['initial_no_op']
    if (len(set(controls_ids + reset_ids)) != 4 or contracts[0] != contracts[1]
            or references[0] != references[1] or baselines[0] != baselines[1]):
        raise ValueError('Independent groups or their full baseline/reference disagree')
    return {'version': VERSION, 'passed': True, 'source_task_id': case['source_task_id'],
            'contract': contracts[0], 'first_control': first_control,
            'original_control_instance_ids': controls_ids, 'supplement_instance_ids': reset_ids,
            'historical_cycles_rewritten': False, 'training_admission_written': False,
            'ordinary_controls_per_cold': len(driver.expectations(contracts[0]))}
