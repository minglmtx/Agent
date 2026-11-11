"""Development migration triage from public goals and provenance metadata.

Exact matches are evidence of overlap. Lexical neighbours are review candidates,
never proof of semantic equivalence or disjointness. This module cannot migrate
tasks, admit a runtime, create training targets, or read trajectory contents.
"""
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from difflib import SequenceMatcher
import re

from .data_scope import norm


IDENTITY_FIELDS = ('source_task_id', 'task_id', 'dataset_task_id', 'runtime_task_id')
GOAL_FIELDS = ('task_instruction', 'original_task_instruction')
EXACT_KINDS = ('identity', 'goal', 'trace_id', 'trace_sha256')


def canonical_id(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Missing source identity')
    value = value.strip()
    # The corpus uses a 20-hex source identity and both single/double-hyphen
    # derived suffixes. Arbitrary external names retain their exact identity.
    match = re.fullmatch(r'([0-9a-f]{20})(?:-.+)?', value)
    return match.group(1) if match else value


def task_facts(row, split, ordinal):
    if not isinstance(row, dict) or not row.get('domain'):
        raise ValueError('Task domain required')
    ids = {row[key] for key in IDENTITY_FIELDS if row.get(key)}
    if not ids or not isinstance(row.get('task_instruction'), str) or not norm(row['task_instruction']):
        raise ValueError('Task identity and public goal required')
    goals = {norm(row[key]) for key in GOAL_FIELDS if row.get(key)}
    traces, hashes = set(), set()
    for obj in (row, row.get('source_trace_provenance', {})):
        if not isinstance(obj, dict):
            raise ValueError('Malformed source trace provenance')
        for field in ('records', 'selected'):
            for trace in obj.get(field, []):
                if trace.get('trace_id'):
                    traces.add(trace['trace_id'])
                if trace.get('line_sha256'):
                    hashes.add(trace['line_sha256'])
    sid = canonical_id(row.get('source_task_id') or row.get('task_id'))
    return dict(key=f'{split}:{ordinal}:{sid}', split=split, source_task_id=sid,
                domain=row['domain'], public_goal=row['task_instruction'],
                identity=ids | {canonical_id(value) for value in ids},
                goal={(row['domain'], value) for value in goals},
                trace_id=traces, trace_sha256=hashes)


def bank_facts(row, ordinal):
    if not row.get('skill_id') or not row.get('domain') or not row.get('source_task_ids') or not row.get('source_goals'):
        raise ValueError('Bank provenance required')
    ids = set(row['source_task_ids'])
    traces = set(row.get('source_trace_ids', []))
    if row.get('representative_trace_id'):
        traces.add(row['representative_trace_id'])
    return dict(key=f"bank:{ordinal}:{row['skill_id']}", split='bank',
                source_task_id=None, skill_id=row['skill_id'], domain=row['domain'],
                public_goal=None, identity=ids | {canonical_id(value) for value in ids},
                goal={(row['domain'], norm(goal)) for goal in row['source_goals']},
                trace_id=traces, trace_sha256=set())


def public_reference(fact):
    return {key: fact[key] for key in ('key', 'split', 'source_task_id', 'skill_id', 'domain') if key in fact}


def classify_matches(exact):
    strong = {row['split'] for row in exact
              if set(row['matched_by']) & {'identity', 'trace_id', 'trace_sha256'}}
    goals = {row['split'] for row in exact if 'goal' in row['matched_by']}
    # Identical wording may refer to different objects in different initial
    # pages. It does not prove that either task is already represented.
    for splits, label in [({'test'}, 'test'), ({'train', 'replacement_train', 'bank'}, 'training_or_bank'),
                          ({'dev'}, 'development'), ({'unused'}, 'unused')]:
        if strong & splits:
            return label+'_identity_or_trace_overlap'
        if goals & splits:
            return label+'_exact_goal_requires_initial_context_review'
    return 'no_exact_overlap_semantic_review_pending'


def audit_development(splits, bank, *, workers=4):
    if set(splits) != {'dev', 'test', 'train', 'replacement_train', 'unused'}:
        raise ValueError('All five current splits required')
    if type(workers) is not int or not 1 <= workers <= 8:
        raise ValueError('Expected one to eight workers')
    facts = [task_facts(row, split, index) for split, rows in splits.items()
             for index, row in enumerate(rows)]
    facts += [bank_facts(row, index) for index, row in enumerate(bank)]
    by_key = {fact['key']: fact for fact in facts}
    development = [fact for fact in facts if fact['split'] == 'dev']
    indexes = {kind: defaultdict(set) for kind in EXACT_KINDS}
    for fact in facts:
        for kind in EXACT_KINDS:
            for value in fact[kind]:
                indexes[kind][value].add(fact['key'])
    by_domain_goal = defaultdict(set)
    for fact in facts:
        for key in fact['goal']:
            by_domain_goal[key].add(fact['key'])
    token_sets = {key: set(re.findall(r'\w+', key[1])) for key in by_domain_goal}

    def inspect(source):
        matches = defaultdict(lambda: defaultdict(list))
        for kind in EXACT_KINDS:
            for value in source[kind]:
                for target in indexes[kind][value] - {source['key']}:
                    matches[target][kind].append(value)
        exact = [dict(public_reference(by_key[key]),
                      matched_by={kind: sorted(values) for kind, values in sorted(evidence.items())})
                 for key, evidence in sorted(matches.items())]
        candidates = {}
        for key in sorted(source['goal']):
            tokens = token_sets[key]
            for other, targets in by_domain_goal.items():
                if key[0] != other[0] or key == other:
                    continue
                other_tokens = token_sets[other]
                intersection = len(tokens & other_tokens)
                union = len(tokens | other_tokens)
                jaccard = intersection / union if union else 0.0
                # A cheap candidate filter, deliberately not an admission rule.
                if intersection < 2 or jaccard < 0.35:
                    continue
                ratio = SequenceMatcher(None, key[1], other[1], autojunk=False).ratio()
                if ratio < 0.65 and jaccard < 0.65:
                    continue
                for target in targets - {source['key']} - set(matches):
                    score = max(ratio, jaccard)
                    old = candidates.get(target)
                    if old is None or score > old['score']:
                        candidates[target] = dict(public_reference(by_key[target]),
                            compared_goal=key[1], candidate_goal=other[1],
                            score=score, character_ratio=ratio, token_jaccard=jaccard,
                            semantic_equivalence_verified=False)
        status = classify_matches(exact)
        return dict(source_task_id=source['source_task_id'], row_key=source['key'],
                    domain=source['domain'], public_goal=source['public_goal'],
                    status=status, exact_matches=exact,
                    lexical_review_candidates=sorted(candidates.values(), key=lambda row: (-row['score'], row['key'])),
                    semantic_review_complete=False, migrate_to_training=False,
                    training_admitted=False, independent_dev_evaluation_retained=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        records = list(pool.map(inspect, development))
    summary = dict(dev_rows=len(development), unique_dev_sources=len({row['source_task_id'] for row in development}),
                   split_counts={split: len(rows) for split, rows in splits.items()}, bank_rows=len(bank),
                   statuses=dict(Counter(row['status'] for row in records)),
                   rows_with_lexical_candidates=sum(bool(row['lexical_review_candidates']) for row in records),
                   lexical_candidate_pairs=sum(len(row['lexical_review_candidates']) for row in records),
                   exact_overlap_rows=sum(bool(row['exact_matches']) for row in records),
                   semantic_overlap_verified=False, semantic_disjointness_verified=False,
                   migrated_rows=0, model_calls=0, actor_calls=0, paid_api_calls=0,
                   trajectory_contents_read=False, split_modified=False, bank_modified=False,
                   workers=workers)
    return dict(version='dev-training-overlap-audit-v1', summary=summary, records=records)
