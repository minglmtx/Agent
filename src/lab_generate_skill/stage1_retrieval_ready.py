"""Immutable CPU retrieval handoff; no live website, model service, or targets.

The encoding unit is the entire ordered eligible list used by the old entry.
Sharing arbitrary full-bank vectors changes the batch context and is deliberately
not supported. A checkpoint owns its original references and bypasses this input.
"""
from copy import deepcopy
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path

from . import data_scope
from .data_scope import FIELDS, filter_bank, norm, require_runtime_references

VERSION = 'stage1-cpu-retrieval-ready-v1'
METHOD = dict(
    encoder='sentence-transformers/all-MiniLM-L6-v2', device='cpu',
    document_template='Title: {title}\nPrinciple: {principle}\nWhen to apply: {when_to_apply}',
    document_batch='entire ordered eligible list; encode default batch_size=32',
    query_batch='one literal public goal', normalize_embeddings=True,
    score='numpy encoded_documents @ encoded_query',
    ordering=['descending float(score)', 'ascending skill_id'], top_k=6,
    vector_reuse='identical entire ordered document text list only')


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    allow_nan=False).encode()).hexdigest()


def read_pin(ref):
    if not isinstance(ref, dict) or sha(ref['path']) != ref['sha256']:
        raise ValueError('Retrieval pinned input changed')
    return json.loads(Path(ref['path']).read_text())


def implementation():
    return dict(method=METHOD, module_sha256=sha(__file__),
                data_scope_sha256=sha(data_scope.__file__),
                packages={name: version(name) for name in
                          ('sentence-transformers', 'transformers', 'torch', 'numpy')})


def model_manifest(directory):
    directory = Path(directory).resolve()
    # Download bookkeeping is not model input. All nonhidden files, including
    # local Python/config/tokenizer/weights, are pinned; symlinks are rejected.
    members = {}
    for path in sorted(directory.rglob('*')):
        relative = path.relative_to(directory)
        if any(part.startswith('.') for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError('Retrieval model must have regular immutable files')
        if path.is_file():
            members[str(relative)] = sha(path)
    if not {'model.safetensors', 'modules.json', 'tokenizer.json'} <= members.keys():
        raise ValueError('Incomplete local MiniLM model')
    return dict(path=str(directory), files=members, files_sha256=digest(members))


def source_inputs(plan, source, *, bank, scope, allowed):
    sid, active, runtime = (source[k] for k in
                            ('source_task_id', 'active_task_id', 'runtime_task_id'))
    domain = source['domain']
    if active not in allowed or allowed[active]['domain'] != domain:
        raise ValueError('Source is outside frozen training scope')
    goal = allowed[active]['task_instruction']
    reserved = {tuple(value) for value in scope['reserved_goal_keys']}
    if (domain, norm(goal)) in reserved:
        raise ValueError('Held-out task cannot enter retrieval preparation')
    blocked = {sid, active, runtime} | set(scope['blocked_bank_source_task_ids'])
    eligible, _ = filter_bank(bank, blocked, reserved | {(domain, norm(goal))},
                             excluded_skill_ids=scope.get('excluded_skill_ids', []))
    eligible = [row for row in eligible if row['domain'] == domain]
    if len(eligible) < 6 or len({r['skill_id'] for r in eligible}) != len(eligible):
        raise ValueError('Need at least six distinct eligible same-site skills')
    return goal, eligible


def binding(plan, source, *, goal, eligible, scope):
    return dict(
        source=deepcopy(source),
        plan={key: deepcopy(plan[key]) for key in
              ('root', 'bank', 'scope', 'allowed', 'formal_capsule',
               'training_pointer', 'workflow')},
        literal_goal=goal, normalized_goal=norm(goal),
        exclusions=dict(
            source_ids=sorted({source[k] for k in
                              ('source_task_id', 'active_task_id', 'runtime_task_id')} |
                             set(scope['blocked_bank_source_task_ids'])),
            goal_keys=sorted([list(pair) for pair in
                              ({tuple(x) for x in scope['reserved_goal_keys']} |
                               {(source['domain'], norm(goal))})]),
            skill_ids=sorted(scope.get('excluded_skill_ids', []))),
        eligible_rows_sha256=digest(eligible),
        eligible_skill_ids=[row['skill_id'] for row in eligible])


def documents(eligible):
    return [METHOD['document_template'].format(**row) for row in eligible]


def select_references(eligible, scores):
    if len(scores) != len(eligible) or any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or
            not math.isfinite(value) for value in scores):
        raise ValueError('Retrieval scores must be finite and cover all eligible rows')
    indices = sorted(range(len(eligible)),
                     key=lambda i: (-float(scores[i]), eligible[i]['skill_id']))[:6]
    refs = [{key: eligible[i][key] for key in (*FIELDS, 'skill_id')} for i in indices]
    require_runtime_references(refs, bank=eligible)
    if len({ref['skill_id'] for ref in refs}) != 6:
        raise ValueError('Retrieval references must have six distinct IDs')
    return refs


def make_ready(plan, source, *, goal, eligible, scope, scores, model, comparison):
    scores = [float(score) for score in scores]
    if comparison.get('old_cpu_top6_exact') is not True:
        raise ValueError('Ready references require a successful old-path comparison')
    return dict(version=VERSION, status='complete',
                binding=binding(plan, source, goal=goal, eligible=eligible, scope=scope),
                producer_runtime_capsule=deepcopy(plan['capsule']),
                implementation=implementation(), model=model, scores=scores,
                refs=select_references(eligible, scores), comparison=comparison,
                training_data=False, generative_model_calls=0, actor_calls=0)


def consume_ready(plan, source, *, goal, eligible, scope):
    """Return optional pinned refs. A resume never reads or replaces its refs.

    No supplied-ready failure falls back to encoder construction. This function
    does not authorize a live run: the entry still checks source qualification,
    frozen runtime attestation, reset, actual initial capture, and runtime refs.
    """
    if source.get('checkpoint') or 'retrieval_ready' not in plan:
        return None
    mapping = plan['retrieval_ready']
    if not isinstance(mapping, dict) or source['source_task_id'] not in mapping:
        raise ValueError('Ready map must explicitly bind this fresh source')
    artifact = read_pin(mapping[source['source_task_id']])
    if artifact.get('version') != VERSION or artifact.get('status') != 'complete':
        raise ValueError('Retrieval ready artifact is incomplete')
    expected = binding(plan, source, goal=goal, eligible=eligible, scope=scope)
    if artifact.get('binding') != expected:
        raise ValueError('Retrieval source, scope, goal, bank, or runtime binding changed')
    if artifact.get('implementation') != implementation():
        raise ValueError('Retrieval method or package version changed')
    if artifact.get('model') != model_manifest(Path(plan['root']) / 'models/all-MiniLM-L6-v2'):
        raise ValueError('Retrieval model changed')
    if artifact.get('comparison', {}).get('old_cpu_top6_exact') is not True:
        raise ValueError('Retrieval old-path comparison was not passed')
    refs = select_references(eligible, artifact.get('scores', []))
    if artifact.get('refs') != refs:
        raise ValueError('Saved references differ from exact score ordering')
    return refs
