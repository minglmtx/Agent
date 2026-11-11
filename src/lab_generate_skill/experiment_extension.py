"""Add training tasks from a frozen experiment's unused pool; combine paid outputs."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import shutil

import yaml

from .config import load_settings
from .experiment_split import stratified_order, normalize_goal
from .io_utils import atomic_write_json, iter_jsonl
from .openrouter_distill import output_lock, export_candidates
from .schemas import CompactSkill


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def tasks(root, split):
    return list(iter_jsonl(root / split / 'tasks.jsonl'))


def summary(rows):
    return dict(tasks=len(rows), candidate_trajectories=sum(len(g['selected']) for g in rows),
        domains=dict(Counter(g['domain'] for g in rows)),
        outcome_profiles=dict(Counter(g['outcome_profile'] for g in rows)),
        selected_outcomes=dict(Counter(r['outcome'] for g in rows for r in g['selected'])))


def prepare_extra(base, output, cap=1000, seed=43, task_ids=None):
    base, output = Path(base).resolve(), Path(output).resolve()
    if cap < 1:
        raise ValueError('cap must be positive')
    if output.exists():
        raise FileExistsError('Extension directory already exists; do not overwrite a frozen selection')
    pool = tasks(base, 'unused')
    selected, remaining = [], []
    eligible = pool if task_ids is None else [g for g in pool if g['task_id'] in task_ids]
    if task_ids is not None and {g['task_id'] for g in eligible} != set(task_ids):
        raise ValueError('Requested replacement task is not in unused pool')
    count = 0
    for group in stratified_order(eligible, seed):
        n = len(group['selected'])
        if count + n <= cap:
            selected.append(group)
            count += n
        else:
            remaining.append(group)
    if task_ids is not None:
        selected_ids = {g['task_id'] for g in selected}
        remaining = [g for g in pool if g['task_id'] not in selected_ids]
    if not selected:
        raise ValueError('No complete task group fits the extension cap')
    settings = load_settings(base / 'config.yaml')
    output.mkdir(parents=True)
    train = output / 'train/trajectories'
    train.mkdir(parents=True)
    hashes = {}
    with ExitStack() as stack:
        sources = {}
        for domain in settings.collection.domains:
            destination = train / f'{domain}.jsonl'
            with destination.open('wb') as dst:
                for group in sorted(selected, key=lambda g: g['task_id']):
                    if group['domain'] != domain:
                        continue
                    for record in group['selected']:
                        path = record['source_file']
                        if path not in sources:
                            sources[path] = stack.enter_context(Path(path).open('rb'))
                        src = sources[path]
                        src.seek(record['byte_offset'])
                        line = src.read(record['byte_length'])
                        if hashlib.sha256(line).hexdigest() != record['line_sha256']:
                            raise ValueError('Source trajectory changed')
                        dst.write(line)
            hashes[str(destination)] = sha(destination)
    subsets = dict(train=selected, dev=tasks(base, 'dev'), test=tasks(base, 'test'), unused=remaining)
    for name, rows in subsets.items():
        (output / name).mkdir(exist_ok=True)
        # Keep held-out manifests byte-identical to the original experiment.
        if name in ('dev', 'test'):
            shutil.copy2(base / name / 'tasks.jsonl', output / name / 'tasks.jsonl')
        else:
            with (output / name / 'tasks.jsonl').open('w') as handle:
                for row in sorted(rows, key=lambda r: (r['domain'], r['task_id'])):
                    handle.write(json.dumps(row, ensure_ascii=False) + '\n')
    manifest = dict(base_experiment=str(base), base_manifest_sha256=sha(base / 'split_manifest.json'),
        seed=seed, training_trajectory_cap=cap, inspected_tasks_forced_to_train=[],
        source_pool='base unused only', requested_task_ids=sorted(task_ids) if task_ids else None, train_file_sha256=hashes,
        splits={name: summary(rows) for name, rows in subsets.items()},
        excluded_base_train_tasks=len(tasks(base, 'train')), task_overlap=0,
        grouping='website + normalized exact goal; all starts kept together')
    atomic_write_json(output / 'split_manifest.json', manifest)
    shutil.copy2(base / 'trajectory_to_compact_skill.md', output / 'trajectory_to_compact_skill.md')
    settings.paths.prompt_template = output / 'trajectory_to_compact_skill.md'
    settings.paths.trajectories_dir = train
    settings.paths.artifacts_dir = output / 'results'
    settings.skill_build.max_attempts = 2
    (output / 'config.yaml').write_text(yaml.safe_dump(settings.model_dump(mode='json'), sort_keys=False))
    verify_extra(base, output)
    return manifest


def verify_extra(base, extra):
    base, extra = Path(base).resolve(), Path(extra).resolve()
    manifest = json.loads((extra / 'split_manifest.json').read_text())
    if Path(manifest['base_experiment']) != base or manifest['base_manifest_sha256'] != sha(base / 'split_manifest.json'):
        raise ValueError('Base split manifest changed')
    if (base / 'trajectory_to_compact_skill.md').read_bytes() != (extra / 'trajectory_to_compact_skill.md').read_bytes():
        raise ValueError('Prompt snapshots differ')
    for name in ('dev', 'test'):
        if (base / name / 'tasks.jsonl').read_bytes() != (extra / name / 'tasks.jsonl').read_bytes():
            raise ValueError('Held-out split changed')
    pool = {r['task_id']: r for r in tasks(base, 'unused')}
    selected = tasks(extra, 'train')
    if any(g['task_id'] not in pool or g != pool[g['task_id']] for g in selected):
        raise ValueError('Extension must use unchanged groups from base unused pool')
    seen_tasks, seen_goals, seen_traces = set(), set(), set()
    for root, name in [(base, 'train'), (base, 'dev'), (base, 'test'), (extra, 'train')]:
        rows = tasks(root, name)
        ids = {g['task_id'] for g in rows}
        goals = {(g['domain'], normalize_goal(g['task_instruction'])) for g in rows}
        trace_ids = {r['trace_id'] for g in rows for r in g['records']}
        if seen_tasks & ids or seen_goals & goals or seen_traces & trace_ids:
            raise ValueError('Task, goal or trajectory leakage detected')
        seen_tasks |= ids
        seen_goals |= goals
        seen_traces |= trace_ids
    for file, digest in manifest['train_file_sha256'].items():
        if sha(file) != digest:
            raise ValueError('Extension input changed')
    expected = {r['trace_id']: g for g in selected for r in g['selected']}
    actual = set()
    for file in manifest['train_file_sha256']:
        for row in iter_jsonl(file):
            tid = row['trace_id']
            if tid in actual or tid not in expected or row['task_id'] != expected[tid]['task_id']:
                raise ValueError('Unexpected or duplicate extension trajectory')
            actual.add(tid)
    if actual != set(expected) or len(actual) > manifest['training_trajectory_cap']:
        raise ValueError('Extension count mismatch')
    settings = load_settings(extra / 'config.yaml')
    if settings.paths.trajectories_dir != extra / 'train/trajectories' or settings.skill_build.max_attempts != 2:
        raise ValueError('Extension configuration changed')
    return dict(verified=True, extra_tasks=len(selected), extra_trajectories=len(actual),
                overlap_with_base_train=0, heldout_unchanged=True)


def combine(base, extra, output):
    """Create a derived snapshot with provenance and postprocess-compatible inputs.

    Inputs must be idle. Re-run after either extraction resumes to refresh the
    snapshot. Does not call an LLM or perform semantic clustering.
    """
    base, extra, output = (Path(p).resolve() for p in (base, extra, output))
    if output in (base, extra) or output in base.parents or output in extra.parents:
        raise ValueError('Combined output must be separate from source experiments')
    verify_extra(base, extra)
    output.mkdir(parents=True, exist_ok=True)
    identity = dict(base=str(base), extra=str(extra))
    marker = output / 'merge_sources.json'
    with output_lock(output), ExitStack() as stack:
        if marker.exists():
            if json.loads(marker.read_text()) != identity:
                raise ValueError('Combined directory belongs to different sources')
        elif any(p.name != '.distill.lock' for p in output.iterdir()):
            raise ValueError('Combined directory is not empty')
        for root in sorted((base, extra)):
            stack.enter_context(output_lock(root / 'results'))
            if not (root / 'results/raw_generations.jsonl').exists():
                raise ValueError(f'No completed API responses yet in {root.name}')
        atomic_write_json(marker, identity)
        candidate_rows, generation_rows = {}, {}
        report = []
        billing_reservations = []
        for root in (base, extra):
            reservations = root / 'results/billing_reservations.json'
            if reservations.exists():
                billing_reservations.extend(json.loads(reservations.read_text()))
            allowed = {r['trace_id'] for g in tasks(root, 'train') for r in g['selected']}
            candidates = root / 'results/raw_candidates.jsonl'
            per_source = set()
            if candidates.exists():
                for row in iter_jsonl(candidates):
                    ids = row['trace_ids']
                    if len(ids) != 1 or not set(ids) <= allowed:
                        raise ValueError('Candidate refers to a non-training trajectory')
                    CompactSkill.model_validate(row['candidate'])
                    key = (row['generation_id'], row['candidate_index'])
                    if key in candidate_rows and candidate_rows[key] != row:
                        raise ValueError('Conflicting candidate IDs')
                    candidate_rows[key] = row
                    per_source.update(ids)
            for row in iter_jsonl(root / 'results/raw_generations.jsonl'):
                if not set(row['trace_ids']) <= allowed:
                    raise ValueError('Generation refers to a non-training trajectory')
                key = (row['generation_id'], row.get('attempt', 1))
                if key in generation_rows and generation_rows[key] != row:
                    raise ValueError('Conflicting generation attempts')
                generation_rows[key] = row
            report.append(dict(experiment=str(root), planned_trajectories=len(allowed),
                               trajectories_with_valid_skill=len(per_source)))
        settings = load_settings(base / 'config.yaml')
        train = output / 'train/trajectories'
        results = output / 'results'
        train.mkdir(parents=True, exist_ok=True)
        results.mkdir(exist_ok=True)
        # Copy once; later refreshes only replace the small result ledgers.
        inputs = {str(root): json.loads((root / 'split_manifest.json').read_text())['train_file_sha256']
                  for root in (base, extra)}
        input_marker = output / 'combined_inputs.json'
        if input_marker.exists() and json.loads(input_marker.read_text()) != inputs:
            raise ValueError('Frozen source inputs changed')
        for domain in settings.collection.domains:
            destination = train / f'{domain}.jsonl'
            if not input_marker.exists() or not destination.exists():
                temp = destination.with_suffix('.tmp')
                with temp.open('wb') as dst:
                    for root in (base, extra):
                        file = root / 'train/trajectories' / f'{domain}.jsonl'
                        if sha(file) != inputs[str(root)][str(file)]:
                            raise ValueError('Training file changed')
                        with file.open('rb') as src:
                            shutil.copyfileobj(src, dst)
                temp.replace(destination)
        atomic_write_json(input_marker, inputs)
        for name, rows in [('raw_candidates.jsonl', candidate_rows), ('raw_generations.jsonl', generation_rows)]:
            temp = results / ('.' + name + '.tmp')
            with temp.open('w') as handle:
                for key in sorted(rows):
                    handle.write(json.dumps(rows[key], ensure_ascii=False) + '\n')
            temp.replace(results / name)
        atomic_write_json(results / "billing_reservations.json", billing_reservations)
        totals = export_candidates(results)
        shutil.copy2(base / 'trajectory_to_compact_skill.md', output / 'trajectory_to_compact_skill.md')
        settings.paths.prompt_template = output / 'trajectory_to_compact_skill.md'
        settings.paths.trajectories_dir = train
        settings.paths.artifacts_dir = results
        (output / 'postprocess_config.yaml').write_text(yaml.safe_dump(settings.model_dump(mode='json'), sort_keys=False))
        metadata = dict(sources=report, candidate_skills=totals['candidate_skills'],
            source_reported_cost_usd=totals['reported_cost_usd'],
            reserved_unconfirmed_cost_usd=totals['reserved_unconfirmed_cost_usd'],
            all_planned_trajectories_have_skills=all(r['planned_trajectories'] == r['trajectories_with_valid_skill'] for r in report),
            semantic_deduplication=False, additional_api_cost_usd=0)
        atomic_write_json(output / 'merge_report.json', metadata)
        return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('prepare', 'verify', 'merge'):
        p = sub.add_parser(command)
        p.add_argument('--base', type=Path, required=True)
        p.add_argument('--extra', type=Path, required=True)
        if command == 'prepare':
            p.add_argument('--cap', type=int, default=1000)
        if command == 'merge':
            p.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare_extra(args.base, args.extra, args.cap)['splits']['train']
    elif args.command == 'verify':
        result = verify_extra(args.base, args.extra)
    else:
        result = combine(args.base, args.extra, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
