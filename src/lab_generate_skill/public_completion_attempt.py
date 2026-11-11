"""One new attempt for a reviewed, explicitly different completion goal.

Historical model successes and failures are retained as-is. Exact terminal jobs,
raw artifacts, original public inputs and source reservations are checked before
the ordinary launcher can acquire the new definition's exclusive lease.
"""
import io
import os
from copy import deepcopy
import re
import json
from pathlib import Path, PurePosixPath
import tarfile

from .answer_protocol_repair import Authority, pinned, regular, sha, plain
from . import public_completion_runtime as runtime
from . import public_navigation_revision as navigation_revision
from .source_revision_binding import fingerprint, local_path, binding
from .control_job_set import TERMINAL

VERSION = 'reviewed-public-completion-attempt-v1'
REQUIRED = ('attempt-started.json', 'result.json', 'trajectory.json', 'generation-000.json')


def _member_name(name):
    p = PurePosixPath(name)
    if not isinstance(name, str) or str(p) != name or p.is_absolute() or '..' in p.parts or '\\' in name:
        raise ValueError('Exact relative historical member required')
    return name


def _history_files(record, directory, task_id):
    """Verify existing bytes in place; do not generate another expanded copy."""
    members = record.get('files')
    if not isinstance(members, dict) or not members:
        raise ValueError('Complete retained task file manifest required')
    current = {str(p.relative_to(directory)): p for p in directory.rglob('*') if p.is_file()}
    if set(current) != set(members) or any(p.is_symlink() for p in directory.rglob('*')):
        raise ValueError('Historical task directory changed or contains links')
    values = {}
    for name, metadata in members.items():
        _member_name(name)
        data = regular(current[name])
        if metadata != {'bytes': len(data), 'sha256': sha(data)}:
            raise ValueError('Historical task artifact changed')
        if name in REQUIRED:
            values[name] = json.loads(data)
    archived = record.get('archived_partition')
    if archived:
        index = json.loads(pinned(archived['index']))
        if index.get('archival_status') != 'complete_member_archive_saved':
            raise ValueError('Complete original archive required')
        if Path(archived['archive']['path']).stat().st_size > 256*1024**2:
            raise ValueError('Use a bounded original task evidence partition')
        raw = pinned(archived['archive'])
        if sha(raw) != index.get('archive_sha256'):
            raise ValueError('Archive differs from its complete member index')
        seen = set()
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
            for member in archive:
                name = _member_name(member.name)
                if not member.isfile() or name in seen or member.size > 64*1024**2:
                    raise ValueError('Unique bounded regular archive members required')
                seen.add(name); data = archive.extractfile(member).read()
                if index.get('members', {}).get(name) != {'bytes': len(data), 'sha256': sha(data)}:
                    raise ValueError('Retained archive member changed')
                prefix = task_id+'/'
                if name.startswith(prefix) and name[len(prefix):] in REQUIRED:
                    key = name[len(prefix):]; value = json.loads(data)
                    if key in values and values[key] != value:
                        raise ValueError('Expanded and archived original attempts differ')
                    values[key] = value
        if seen != set(index['members']):
            raise ValueError('Incomplete original archive coverage')
        pointer_path = directory/'attempt-archive.json'
        pointer = json.loads(regular(pointer_path))
        if pointer.get('task_id') != task_id or pointer.get('archive_sha256') != index['archive_sha256']:
            raise ValueError('Historical actor directory belongs to another archive')
    if not set(REQUIRED) <= values.keys():
        raise ValueError('Original attempt marker, result, trajectory and actual prompt required')
    return values, {name: value for name, value in members.items() if '/' not in name}


def _plain_navigation_scope(candidate, record, base, *, kind="navigation"):
    """A public wording revision with exactly the same native page contract.

    No runtime adapter is needed: the ordinary navigation runner retains its
    original initialization, collection, reset, integrity and terminal checks.
    This branch binds an explicit public goal or recorded start to reviewed source evidence.
    """
    if kind not in ('navigation', 'search', 'newsletter', 'navigation_context'):
        raise ValueError('Explicit plain native public-wording family required')
    selector={'navigation':'plain_navigation_revision','search':'plain_search_revision','newsletter':'plain_newsletter_revision','navigation_context':'recorded_navigation_context_revision'}[kind]
    spec = record[selector]
    if not isinstance(spec, dict) or set(spec) != {'original_contract', 'scope_review', 'inventory'}:
        raise ValueError('Exact plain navigation definition evidence required')
    original = json.loads(pinned(spec['original_contract']))
    if (original.get('task_text_changed') is not False or 'admission_result' in original
            or any(original.get(k) for k in ('query', 'cart', 'catalog', 'order', 'account_change',
                'membership', 'checkout', 'public_completion', 'public_navigation_revision'))):
        raise ValueError('An original plain native read/search contract is required')
    if kind in ('navigation', 'navigation_context'):
        completion = original.get('completion')
        if (not isinstance(completion, dict) or not completion
                or not set(completion) <= {'path_regex', 'heading_regex', 'title_regex', 'query_params'}
                or not completion.get('path_regex') or not completion.get('heading_regex')
                or original.get('search') or original.get('newsletter')):
            raise ValueError('An original plain native navigation contract is required')
    elif kind == 'newsletter':
        from .shopping_newsletter import validate_contract
        if (original.get('completion') or original.get('search')
                or any(original.get(k) for k in ('review_creation','submission','group_creation',
                    'issue_creation','forum_creation','todo','wiki','offline_training',
                    'preference_goal_state','native_csv_export','gitlab_native_read','reddit_native_read'))):
            raise ValueError('One original native newsletter contract required')
        validate_contract(original)
    else:
        from .site_search_rules import validate_contract
        if (original.get('domain') != 'shopping' or original.get('completion')
                or original.get('search', {}).get('kind') != 'advanced' or original.get('newsletter')):
            raise ValueError('An original native advanced-search contract is required')
        validate_contract(original)
    if spec['inventory']['path'] != str(base/'inventory.jsonl'):
        raise ValueError('Authoritative local inventory must be pinned')
    inventory = [json.loads(line) for line in pinned(spec['inventory']).decode().splitlines()]
    matches = [r for r in inventory if r.get('task_id') == original.get('source_task_id')]
    if len(matches) != 1:
        raise ValueError('Exactly one original source in inventory required')
    source = matches[0]
    if (source.get('domain') != original.get('domain') or source.get('goal') != original['goal']
            or source.get('heldout_quarantine') is not False
            or original.get('heldout_quarantine') is not False
            or original['start_path'] != local_path(source['recorded_start_urls'][0])):
        raise ValueError('Original source goal, declared first start and split must agree')
    report = json.loads(pinned(spec['scope_review']))
    scopes = [r for r in report.get('records', []) if r.get('source_task_id') == original['source_task_id']]
    if len(scopes) != 1:
        raise ValueError('One independently reviewed source scope required')
    scope = scopes[0]
    if (scope.get('task_contract') != original or scope.get('start_path') != original['start_path']
            or scope.get('actual_prompt_and_trajectory_read') is not True
            or scope.get('new_actor_required_for_definition') is not True
            or scope.get('original_benchmark_equivalence_claimed') is not False
            or not isinstance(scope.get('revision_reason'), str) or not scope['revision_reason'].strip()):
        raise ValueError('Explicit public-goal review must preserve the native starting state')
    context_revision=kind=='navigation_context'
    expected = deepcopy(original)
    expected.update(task_id=candidate.get('task_id'), original_goal=original['goal'],
        recorded_start_urls=deepcopy(source['recorded_start_urls']),
        recorded_start_paths=[local_path(u) for u in source['recorded_start_urls']],
        source_trace_ids=deepcopy(source['source_trace_ids']))
    if context_revision:
        selected=scope.get('proposed_start_path')
        if (scope.get('proposed_public_goal') != original['goal']
                or selected not in expected['recorded_start_paths'] or selected==original['start_path']):
            raise ValueError('Only a reviewed different recorded start with unchanged goal is allowed')
        expected.update(start_path=selected,task_text_changed=False,
            start_revision={'version':'reviewed-recorded-navigation-context-v1',
                'original_start':original['start_path'],'derived_start':selected,
                'reason':scope['revision_reason'],'equivalent_to_original_evaluation':False})
    else:
        expected.update(goal=scope['proposed_public_goal'],task_text_changed=True,
            goal_revision={'version':'reviewed-plain-'+kind+'-wording-v1',
                'original_goal':original['goal'],'derived_goal':scope['proposed_public_goal'],
                'reason':scope['revision_reason'],'equivalent_to_original_evaluation':False})
    if (plain(candidate) != expected or candidate.get('task_id') == original['task_id']
            or not isinstance(candidate.get('task_id'), str) or not candidate['task_id'].strip()
            or (candidate.get('goal') == original['goal'] and not context_revision)
            or candidate.get('eligible_for_training') is not False
            or any(candidate.get(k) is True for k in ('training_admitted', 'normal_gate_passed'))):
        raise ValueError('Only the explicitly reviewed wording/start and source mapping may change')
    binding(candidate)
    return original, report, scope


class PublicCompletionAuthority(Authority):
    def __init__(self, base, wave, selected, spec, spec_sha, *, terminal_query):
        self.base = Path(base).resolve(); self.wave = Path(wave).resolve()
        self.spec_sha = spec_sha; self.superseded = {}; self.artifacts = {}; self.leases = []
        self.reason = 'reviewed_public_completion_revision'
        self.previous_attempts = 0
        if (spec.get('version') != VERSION or spec.get('reason') != self.reason
                or spec.get('wave') != str(self.wave) or self.wave.parent != self.base):
            raise ValueError('Explicit reviewed public revision scope required')
        chosen = {c['source_task_id']: c for c in selected}
        records = spec.get('sources', [])
        if (len(chosen) != len(selected) or len(records) != len(chosen)
                or {r['source_task_id'] for r in records} != set(chosen)):
            raise ValueError('History must cover exactly the selected sources')
        for record in records:
            sid = record['source_task_id']; candidate = chosen[sid]
            selectors={'plain_navigation_revision':'navigation','plain_search_revision':'search',
                'plain_newsletter_revision':'newsletter','recorded_navigation_context_revision':'navigation_context'}
            chosen_kinds=[kind for key,kind in selectors.items() if key in record]
            if chosen_kinds:
                if len(chosen_kinds)!=1:
                    raise ValueError('One explicit plain public revision family required')
                original, report, scope = _plain_navigation_scope(candidate, record, self.base, kind=chosen_kinds[0])
            else:
                adapter = navigation_revision if navigation_revision.FIELD in candidate else runtime
                field = navigation_revision.FIELD if adapter is navigation_revision else 'public_completion'
                if not adapter.enabled(candidate):
                    raise ValueError('A reviewed public revision contract is required')
                adapter._review(candidate)
                original = candidate[field]['original_contract']
                report = adapter._pinned(candidate[field]['scope_review'])
                scope = next(r for r in report['records'] if r['source_task_id'] == sid)
            if (record.get('candidate_fingerprint') != fingerprint(candidate)
                    or record.get('historical_result_disposition') != 'retained_not_reclassified'):
                raise ValueError('Exact new definition and preserved old outcomes required')
            histories = record.get('history', [])
            if not histories or len({r['actor_directory'] for r in histories}) != len(histories):
                raise ValueError('Distinct retained historical attempts required')
            for history in histories:
                old = Path(history['old_wave'])
                if old.parent != self.base or old == self.wave or not old.is_dir():
                    raise ValueError('Exact old sibling wave required')
                if old.is_symlink() and (history.get('old_wave_resolved') != str(old.resolve())
                        or history.get('old_wave_symlink') != os.readlink(old)):
                    raise ValueError('Historical offload mapping must be explicitly pinned')
                directory = Path(history['actor_directory'])
                if (directory.resolve().parent.parent != old.resolve()/'actor'
                        or any(p.is_symlink() for p in (directory, directory.parent, old/'actor'))
                        or directory.name != original['task_id']
                        or directory.parent.parent != old/'actor'
                        or not (directory.parent.name.isdecimal() or re.fullmatch(
                            re.escape(original['domain'])+r'-[0-9]+', directory.parent.name))):
                    raise ValueError('Exact original worker/task directory required')
                values, artifacts = _history_files(history, directory, original['task_id'])
                marker = values['attempt-started.json']; job = str(history['job_id'])
                if marker != {'job': job, 'task': original['task_id'], 'scripted': False}:
                    raise ValueError('Historical source or job marker differs')
                states = terminal_query(job)
                if (not states or states != history.get('terminal_states')
                        or any(s not in TERMINAL for s in states.values())):
                    raise ValueError('Historical job is not confirmed terminal')
                result = values['result.json']; trajectory = values['trajectory.json']
                generation = values['generation-000.json']
                inputs = [json.loads(m['content']) for m in generation['messages'] if m['role'] == 'user']
                if (len(inputs) != 1 or inputs[0].get('goal') != original['goal']
                        or local_path(inputs[0].get('url', '')) != original['start_path']
                        or trajectory.get('task_instruction') != original['goal']
                        or trajectory.get('task_id') != original['task_id']
                        or result.get('task_id') != original['task_id']
                        or result.get('domain') != original['domain']
                        or result.get('actor_attempts') != 1 or type(result.get('actor_attempts')) is not int):
                    raise ValueError('Actual original public goal, start or execution identity differs')
                if (str(directory/'result.json') != scope['actor_result']
                        or result.get('evaluation', {}).get('status') != scope['saved_outcome']
                        or result.get('evaluation', {}).get('checks') != scope['saved_checks']):
                    raise ValueError('Original result differs from the independent scope review')
                for name in ('result.json', 'trajectory.json', 'generation-000.json'):
                    path = str(directory/name)
                    if report['input_sha256'].get(path) != artifacts[name]['sha256']:
                        raise ValueError('Historical review no longer binds the raw execution evidence')
                manifests = history.get('manifests', [])
                if not manifests:
                    raise ValueError('Exact original reservation manifests required')
                for item in manifests:
                    path = Path(item['path'])
                    if (path.parent.parent != self.base or path.parent == self.wave
                            or path.suffix != '.jsonl' or not path.name.startswith(('contracts', 'tasks'))):
                        raise ValueError('Only source-bound original manifests may be superseded')
                    matching = [plain(c) for c in map(json.loads, pinned(item).decode().splitlines())
                                if c.get('source_task_id', c['task_id']) == sid]
                    if not matching or any(c != original for c in matching):
                        raise ValueError('Original manifest changed its native source contract')
                    self.superseded.setdefault(path.resolve(), set()).add(sid)
                self.artifacts[directory.resolve()] = artifacts
                self.previous_attempts += 1
            # Packaging and the new task's display ID cannot authorize another
            # run of the same reviewed public goal and native completion scope.
            identity = {'source': sid, 'goal': candidate['goal'], 'start': candidate['start_path'],
                        'original_native_contract': fingerprint(original)}
            key = sha((VERSION+'\n'+json.dumps(identity, sort_keys=True)).encode())
            lease = self.base/'answer-protocol-repair-leases'/key
            owner = {'version': VERSION, 'wave': str(self.wave), 'authorization_sha256': spec_sha,
                     'source_task_id': sid, 'candidate_fingerprint': fingerprint(candidate)}
            self.leases.append((lease, owner))
        self.require_lease_owners()
