"""Freeze task-disjoint Go-Browse subsets without loading all trajectories in RAM."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import random
import shutil

import yaml

from .config import load_settings
from .gobrowse_data import normalize_goal
from .io_utils import atomic_write_json, iter_jsonl


def stratum(group):
    return (group['domain'], group['outcome_profile'], len(group['selected']))


def stratified_order(groups, seed):
    """Interleave seeded shuffles in proportion to stratum size."""
    bins = defaultdict(list)
    for group in sorted(groups, key=lambda g: g['task_id']):
        bins[stratum(group)].append(group)
    rng = random.Random(seed)
    for key in sorted(bins):
        rng.shuffle(bins[key])
    total = {key: len(value) for key, value in bins.items()}
    used = Counter()
    while bins:
        key = min(bins, key=lambda k: ((used[k] + 1) / total[k], k))
        yield bins[key].pop()
        used[key] += 1
        if not bins[key]:
            del bins[key]


def assign_splits(groups, *, cap, dev_tasks, test_tasks, seed, forced_train):
    if cap < 1 or dev_tasks < 1 or test_tasks < 1:
        raise ValueError('cap and held-out task counts must be positive')
    forced = sorted([g for g in groups if g['task_id'] in forced_train], key=lambda g: g['task_id'])
    pool = [g for g in groups if g['task_id'] not in forced_train]
    if len(pool) < dev_tasks + test_tasks:
        raise ValueError('Not enough independent tasks for held-out sets')
    ordered = list(stratified_order(pool, seed))
    test = ordered[:test_tasks]
    dev = ordered[test_tasks:test_tasks + dev_tasks]
    train = list(forced)
    count = sum(len(g['selected']) for g in train)
    if count > cap:
        raise ValueError('Previously inspected tasks exceed the training cap')
    unused = []
    for group in stratified_order(ordered[test_tasks + dev_tasks:], seed + 1):
        n = len(group['selected'])
        if count + n <= cap:
            train.append(group)
            count += n
        else:
            unused.append(group)
    splits = dict(train=train, dev=dev, test=test, unused=unused)
    ids = [g['task_id'] for subset in splits.values() for g in subset]
    assert len(ids) == len(set(ids)) == len(groups)
    return splits


def index_inputs(settings, prior_ledgers):
    inspected = {trace_id for p in prior_ledgers for row in iter_jsonl(p)
                 for trace_id in row['trace_ids']}
    by_goal = {}
    ids = {}
    seen_traces = set()
    sources = []
    invalid = 0
    for domain in sorted(settings.collection.domains):
        path = settings.paths.trajectories_dir / f'{domain}.jsonl'
        digest = hashlib.sha256()
        with path.open('rb') as handle:
            while True:
                offset = handle.tell()
                line = handle.readline()
                if not line:
                    break
                digest.update(line)
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get('error') or row.get('quality_flags') or row['evaluation_outcome'] not in ('correct', 'incorrect'):
                    invalid += 1
                    continue
                if row['domain'] != domain or row['trace_id'] in seen_traces:
                    raise ValueError('Domain mismatch or duplicate trace ID')
                seen_traces.add(row['trace_id'])
                key = (domain, normalize_goal(row['task_instruction']))
                task_id = row['task_id']
                if task_id in ids and ids[task_id] != key:
                    raise ValueError('One task ID describes multiple goals')
                ids[task_id] = key
                group = by_goal.setdefault(key, dict(domain=domain, task_id=task_id,
                    task_instruction=key[1], records=[], inspected=False))
                if group['task_id'] != task_id:
                    raise ValueError('Equivalent goals have different IDs; regroup before splitting')
                group['inspected'] |= row['trace_id'] in inspected
                group['records'].append(dict(trace_id=row['trace_id'], outcome=row['evaluation_outcome'],
                    source_file=str(path), byte_offset=offset, byte_length=len(line),
                    line_sha256=hashlib.sha256(line).hexdigest(), rounds=row['rounds']))
        sources.append(dict(path=str(path), bytes=path.stat().st_size, sha256=digest.hexdigest()))
    groups = list(by_goal.values())
    for group in groups:
        pos = sorted([r for r in group['records'] if r['outcome'] == 'correct'], key=lambda r: r['trace_id'])
        neg = sorted([r for r in group['records'] if r['outcome'] == 'incorrect'], key=lambda r: r['trace_id'])
        rng = random.Random(f"{settings.collection.base_seed}:{group['task_id']}")
        rng.shuffle(pos)
        rng.shuffle(neg)
        chosen = pos[:1] + neg[:1]
        chosen += (pos[1:] + neg[1:])[:2 - len(chosen)]
        group['selected'] = chosen
        group['outcome_profile'] = 'paired' if pos and neg else ('success_only' if pos else 'failure_only')
    return groups, sources, invalid


def prepare(config, output, *, cap=4000, dev_tasks=120, test_tasks=160, prior_ledgers=()):
    settings = load_settings(config)
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError('Choose a new experiment directory; frozen splits are never overwritten')
    groups, sources, invalid = index_inputs(settings, prior_ledgers)
    forced = {g['task_id'] for g in groups if g['inspected']}
    splits = assign_splits(groups, cap=cap, dev_tasks=dev_tasks, test_tasks=test_tasks,
                           seed=settings.collection.base_seed, forced_train=forced)
    output.mkdir(parents=True)
    train_dir = output / 'train/trajectories'
    train_dir.mkdir(parents=True)
    hashes = {}
    # Copy only the selected training trajectories; held-out manifests point at
    # immutable source offsets, and cannot be consumed by the distillation runner.
    for domain in sorted(settings.collection.domains):
        digest = hashlib.sha256()
        source = settings.paths.trajectories_dir / f'{domain}.jsonl'
        destination = train_dir / f'{domain}.jsonl'
        with source.open('rb') as src, destination.open('wb') as dst:
            for group in sorted(splits['train'], key=lambda g: g['task_id']):
                if group['domain'] != domain:
                    continue
                for record in group['selected']:
                    src.seek(record['byte_offset'])
                    line = src.read(record['byte_length'])
                    if hashlib.sha256(line).hexdigest() != record['line_sha256']:
                        raise ValueError('Source changed while preparing experiment')
                    dst.write(line)
                    digest.update(line)
        hashes[str(destination)] = digest.hexdigest()
    summary = {}
    for name, subset in splits.items():
        folder = output / name
        folder.mkdir(exist_ok=True)
        with (folder / 'tasks.jsonl').open('w') as handle:
            for group in sorted(subset, key=lambda g: (g['domain'], g['task_id'])):
                handle.write(json.dumps(group, ensure_ascii=False) + '\n')
        summary[name] = dict(tasks=len(subset), candidate_trajectories=sum(len(g['selected']) for g in subset),
            domains=dict(sorted(Counter(g['domain'] for g in subset).items())),
            outcome_profiles=dict(sorted(Counter(g['outcome_profile'] for g in subset).items())),
            selected_outcomes=dict(Counter(r['outcome'] for g in subset for r in g['selected'])))
    manifest = dict(seed=settings.collection.base_seed, training_trajectory_cap=cap,
        grouping='website + normalized exact goal; all start pages kept together',
        split_method='seeded task sampling stratified by website, outcome profile and available trajectory count',
        evaluation_protocol='Custom held-out tasks; not official WebArena or an OOD split',
        inspected_tasks_forced_to_train=sorted(forced), prior_ledgers=[str(p) for p in prior_ledgers],
        excluded_invalid_trajectories=invalid, source_files=sources, train_file_sha256=hashes,
        splits=summary, task_overlap=0, total_tasks=len(groups))
    atomic_write_json(output / 'split_manifest.json', manifest)
    shutil.copy2(settings.paths.prompt_template, output / 'trajectory_to_compact_skill.md')
    settings.paths.prompt_template = output / 'trajectory_to_compact_skill.md'
    settings.paths.trajectories_dir = train_dir
    settings.paths.artifacts_dir = output / 'results'
    settings.skill_build.max_attempts = 2
    settings.skill_build.selection = 'outcome_balanced'
    settings.skill_build.require_outcome_pair = False
    (output / 'config.yaml').write_text(yaml.safe_dump(settings.model_dump(mode='json'), sort_keys=False))
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--cap', type=int, default=4000)
    parser.add_argument('--dev-tasks', type=int, default=120)
    parser.add_argument('--test-tasks', type=int, default=160)
    parser.add_argument('--prior-ledger', action='append', default=[], type=Path)
    args = parser.parse_args()
    manifest = prepare(args.config, args.output, cap=args.cap, dev_tasks=args.dev_tasks,
                       test_tasks=args.test_tasks, prior_ledgers=args.prior_ledger)
    print(json.dumps(manifest['splits'], indent=2))


if __name__ == '__main__':
    main()
