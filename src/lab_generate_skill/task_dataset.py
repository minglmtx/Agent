"""Current task definitions, independent of frozen runtime and raw trace provenance."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_task_dataset(pointer: Path) -> dict:
    config = json.loads(pointer.read_text())
    manifest = Path(config['replacement_manifest'])
    if sha256(manifest) != config['replacement_manifest_sha256']:
        raise ValueError('Current task replacement manifest has changed')
    data = json.loads(manifest.read_text())
    data['excluded_source_task_ids'] = []
    if config.get('exclusion_manifest'):
        exclusion_path = Path(config['exclusion_manifest'])
        if sha256(exclusion_path) != config.get('exclusion_manifest_sha256'):
            raise ValueError('Current task exclusion manifest has changed')
        exclusions = json.loads(exclusion_path.read_text())['exclusions']
        ids = [row['task_id'] for row in exclusions]
        if (any(not isinstance(tid, str) or not tid for tid in ids)
                or len(set(ids)) != len(ids)
                or any(not row.get('reason') for row in exclusions)):
            raise ValueError('Distinct source identities and exclusion reasons required')
        data['excluded_source_task_ids'] = ids
    for item in data['replacements']:
        for field in ('admission_proof', 'task_definition'):
            if sha256(Path(item[field])) != item[field + '_sha256']:
                raise ValueError(f"Changed {field} for {item['source_task_id']}")
    for name, digest in config['split_file_sha256'].items():
        if sha256(Path(config['split_root']) / name) != digest:
            raise ValueError(f'Changed current split: {name}')
    if config.get('catalog_sha256') and sha256(Path(config['catalog'])) != config['catalog_sha256']:
        raise ValueError('Current task catalog has changed')
    data['status_resolutions'] = []
    if config.get('status_resolution_manifest'):
        path = Path(config['status_resolution_manifest'])
        if sha256(path) != config['status_resolution_manifest_sha256']:
            raise ValueError('Task status resolution manifest has changed')
        resolutions = json.loads(path.read_text())['records']
        for item in resolutions:
            for evidence, digest in item['evidence_sha256'].items():
                if sha256(Path(evidence)) != digest:
                    raise ValueError(f"Changed resolution evidence for {item['source_task_id']}")
        data['status_resolutions'] = resolutions
    return data


def apply_task_dataset(rows: list[dict], pointer: Path) -> list[dict]:
    """Replace public goals, never promote old evaluations to valid targets."""
    data = load_task_dataset(pointer)
    replacements = {x['source_task_id']: x for x in data['replacements']}
    resolutions = {x['source_task_id']: x for x in data['status_resolutions']}
    excluded = set(data['excluded_source_task_ids'])
    # A retired source may have a previously approved derivative; neither is
    # active after exclusion, and its old score must not restore it to the table.
    replacements = {k: v for k, v in replacements.items() if k not in excluded}
    resolutions = {k: v for k, v in resolutions.items() if k not in excluded}
    found = set()
    resolved = set()
    result = []
    for original in rows:
        row = dict(original)
        tid = row['task_id']
        source_id = row.get('source_task_id') or tid.split('--', 1)[0]
        if tid in excluded or source_id in excluded:
            continue
        item = replacements.get(tid)
        row.update({
            'current_dataset_task_id': tid,
            'current_dataset_runtime_task_id': tid,
            'current_dataset_replacement': False,
            'current_dataset_original_goal': '',
            'current_dataset_admission_proof': '',
            'superseded_unknown_is_current_pending': '',
            'superseded_unknown_is_training_target': False,
            'task_resolution_status': '',
            'task_resolution_result': '',
            'task_resolution_start_path': '',
            'task_resolution_is_latest_runtime_admission': False,
        })
        if item:
            if row['domain'] != item['domain']:
                raise ValueError(f'Domain mismatch: {tid}')
            if row['goal'] not in (item['original_goal'], item['derived_goal']):
                raise ValueError(f'Unexpected goal for replaced task: {tid}')
            found.add(tid)
            row.update({
                'goal': item['derived_goal'],
                'current_dataset_task_id': item['dataset_task_id'],
                'current_dataset_runtime_task_id': item['existing_derived_task_id'],
                'current_dataset_replacement': True,
                'current_dataset_original_goal': item['original_goal'],
                'current_dataset_admission_proof': item['admission_proof'],
                'superseded_unknown_is_current_pending': False,
            })
        resolution = resolutions.get(tid)
        if resolution:
            if row['goal'] != resolution['goal'] or row['domain'] != resolution['domain']:
                raise ValueError(f'Resolution task definition mismatch: {tid}')
            resolved.add(tid)
            row.update({
                'task_resolution_status': 'success',
                'task_resolution_result': resolution['result'],
                'task_resolution_start_path': resolution['start_path'],
                'repair_state': 'historical_normal_actor_success_verified_original_goal',
                'codebase_issue': '',
                'superseded_unknown_is_current_pending': False,
            })
        result.append(row)
    if found != set(replacements):
        raise ValueError(f'Missing replacement sources: {sorted(set(replacements) - found)}')
    if resolved != set(resolutions):
        raise ValueError(f'Missing resolution sources: {sorted(set(resolutions) - resolved)}')
    return result
