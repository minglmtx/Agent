"""One reviewed reattempt after a public structured-answer transport conflict.

This does not authorize retries of ordinary model failures. The old complete
archive must show the incompatible system instruction. The task, native proof
requirements and evaluator are unchanged; only the public answer interface is
repaired. Old results and claims remain intact, with a separate exclusive lease.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path, PurePosixPath
import tarfile

VERSION = 'public-answer-protocol-repair-v1'
DESCRIPTION_VERSION = 'public-description-revision-repair-v1'
TERMINAL_VERSION = 'terminal-classification-repair-v1'
CAPABILITY_VERSION = 'actor-capability-repair-v1'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def regular(path):
    path = Path(path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise ValueError('An absolute regular repair evidence file is required')
    return path.read_bytes()


def pinned(record):
    data = regular(record['path'])
    if sha(data) != record['sha256']:
        raise ValueError('Pinned repair evidence changed')
    return data


def plain(contract):
    return {k: v for k, v in contract.items() if k != 'admission_result'}


def archive_values(record):
    """Verify the entire closed archive, retaining only diagnostic JSON inputs."""
    index = json.loads(pinned(record['index']))
    path = Path(record['archive'])
    if path.is_symlink() or not path.is_file():
        raise ValueError('Original complete actor archive is required')
    if index.get('archival_status') != 'complete_member_archive_saved':
        raise ValueError('Incomplete actor archive cannot authorize repair')
    values = {}; seen = set()
    class Reader:
        def __init__(self, file): self.file = file; self.digest = hashlib.sha256()
        def read(self, size=-1):
            data = self.file.read(size); self.digest.update(data); return data
    with path.open('rb') as file:
        reader = Reader(file)
        with tarfile.open(fileobj=reader, mode='r|gz') as stream:
            for member in stream:
                name = member.name; relative = PurePosixPath(name)
                if (name in seen or name not in index['members'] or not member.isfile()
                        or relative.is_absolute() or '..' in relative.parts or '\\' in name):
                    raise ValueError('Invalid original actor archive member')
                seen.add(name)
                if member.size > 256 * 1024**2:
                    raise ValueError('Oversized repair evidence member')
                data = stream.extractfile(member).read(member.size + 1)
                if index['members'][name] != {'bytes': len(data), 'sha256': sha(data)}:
                    raise ValueError('Original actor archive member changed')
                if name in ('attempt-started.json', 'result.json', 'native-private-receipt.json',
                            'gps-terminal.json', 'terminal-page.json', 'trajectory.json',
                            'native-export-transport.json') or name.startswith(('generation-', 'step-')):
                    values[name] = json.loads(data)
        while reader.read(1024*1024): pass
        if reader.digest.hexdigest() != index['archive_sha256'] or seen != set(index['members']):
            raise ValueError('Incomplete or changed original actor archive')
    return index, values


def require_conflict(contract, index, values, review, current_fields, *, original_contract=None):
    if original_contract is not None:
        from .description_revision_qualification import require_revision
        require_revision(original_contract, plain(contract))
    old_contract = contract if original_contract is None else original_contract
    declaration = contract.get('public_parameters', {}).get('description_format')
    if (not isinstance(declaration, dict) or not declaration
            or any(v != 'ordered records with operation and ui_label' for v in declaration.values())
            or current_fields != {name: 'record_set' for name in declaration}):
        raise ValueError('An explicit public record-array declaration and repaired interface are required')
    receipt = values['native-private-receipt.json']; result = values['result.json']
    if (receipt['contract'] != plain(old_contract) or result.get('task_id') != old_contract['task_id']
            or result.get('actor_attempts') != 1 or result.get('error') is not None
            or result.get('evaluation', {}).get('status') != 'failure'):
        raise ValueError('Exact original failed attempt and unchanged task are required')
    if (review.get('archive_sha256') != index['archive_sha256']
            or review.get('members_verified') != len(index['members'])
            or review.get('independent_terminal_recheck_passed') is not True
            or review.get('attribution', {}).get('owner') != 'codebase'
            or review['attribution'].get('eligible_as_actor_failure') is not False):
        raise ValueError('Independent codebase-conflict review is required')
    generations = [v for k, v in values.items() if k.startswith('generation-')]
    conflicts = ['never an object, array or serialized JSON']
    if original_contract is not None:
        conflicts.append('Return values only, without UI labels or explanatory prefixes.')
    if not generations or any(not any(conflict in v['messages'][0]['content']
            for conflict in conflicts) for v in generations):
        raise ValueError('Actual old system instruction does not demonstrate the public format conflict')


class Authority:
    def __init__(self, base, wave, selected, spec, spec_sha, *, terminal_query, fields):
        revision = spec.get('version') == DESCRIPTION_VERSION
        terminal_repair = spec.get('version') == TERMINAL_VERSION
        capability_repair = spec.get('version') == CAPABILITY_VERSION
        reason = 'actor_capability_conflict' if capability_repair else ('terminal_classification' if terminal_repair else ('public_description_contract_revision' if revision else 'public_answer_protocol_conflict'))
        if spec.get('version') not in (VERSION, DESCRIPTION_VERSION, TERMINAL_VERSION, CAPABILITY_VERSION) or spec.get('reason') != reason:
            raise ValueError('Unsupported codebase repair authority')
        self.base = Path(base).resolve(); self.wave = Path(wave).resolve()
        self.spec_sha = spec_sha; self.superseded = {}; self.artifacts = {}; self.leases = []
        self.original_variants = []
        chosen = {c.get('source_task_id', c['task_id']): c for c in selected}
        entries = spec.get('sources', [])
        if len(chosen) != len(selected) or {r['source_task_id'] for r in entries} != set(chosen) or len(entries) != len(chosen):
            raise ValueError('Repair must cover exactly the selected distinct sources')
        self.reason = reason
        if revision:
            expanded = []
            for source in entries:
                history = source.get('history')
                if not isinstance(history, list) or not history:
                    raise ValueError('A complete pinned previous-attempt history is required')
                if any(r.get('source_task_id') != source['source_task_id'] for r in history):
                    raise ValueError('Historical attempts belong to another source')
                if len({r['archive'] for r in history}) != len(history):
                    raise ValueError('Duplicate historical actor archive')
                expanded.extend(dict(r, _last_history_record=i == len(history)-1)
                                for i, r in enumerate(history))
            entries = expanded
        self.previous_attempts = len(entries)
        for record in entries:
            sid = record['source_task_id']; contract = chosen[sid]
            old_contract = json.loads(pinned(record['original_contract'])) if revision else contract
            if revision:
                from .description_revision_qualification import require_revision
                require_revision(old_contract, plain(contract))
            old = Path(record['old_wave']).resolve()
            if old.parent != self.base or old == self.wave:
                raise ValueError('Original repair source must be a distinct sibling wave')
            states = terminal_query(str(record['old_job_id']))
            if not states or any(s not in ('COMPLETED', 'FAILED', 'CANCELLED', 'TIMEOUT',
                    'OUT_OF_MEMORY', 'NODE_FAIL', 'PREEMPTED') for s in states.values()):
                raise ValueError('Historical actor job is not terminal')
            binding = json.loads(pinned(record['old_bundle_binding']))
            bundle = Path(binding['bundle'])
            if bundle.parent != self.base/'actor-bundles' or sha(regular(bundle/'plan.json')) != binding['plan_sha256']:
                raise ValueError('Original actor bundle binding changed')
            expected = bundle/'task-checkpoints'/old.name/old_contract['task_id']
            if Path(record['archive']) != expected/'diagnostic-data.tar.gz' or Path(record['index']['path']) != expected/'diagnostic-members.json':
                raise ValueError('Archive belongs to a different source or wave')
            index, values = archive_values(record)
            if values.get('attempt-started.json') != {'job': str(record['old_job_id']),
                    'task': old_contract['task_id'], 'scripted': False}:
                raise ValueError('Original actor attempt belongs to another job or task')
            review = json.loads(pinned(record['review']))
            if capability_repair:
                from .actor_capability_repair import require_conflict as require_capability_conflict
                require_capability_conflict(contract, index, values, review)
            elif terminal_repair:
                from .terminal_classification_repair import require_conflict as require_terminal_conflict
                require_terminal_conflict(contract, index, values, review, record)
            else:
                require_conflict(contract, index, values, review, fields(contract),
                                 original_contract=old_contract if revision else None)
            found = False
            for manifest in set(old.glob('contracts*.jsonl')) | set(old.glob('tasks*.jsonl')):
                matching = [json.loads(line) for line in manifest.read_text().splitlines()
                            if json.loads(line).get('source_task_id', json.loads(line)['task_id']) == sid]
                if matching:
                    if any(plain(c) != plain(old_contract) for c in matching):
                        raise ValueError('Original wave task differs from repair task')
                    found = True
                    self.superseded.setdefault(manifest.resolve(), set()).add(sid)
            if not found:
                raise ValueError('Original source manifest is missing')
            if terminal_repair and (old/'distinct-start-variant.json').exists():
                from .distinct_start_variant import load as load_variant
                variant = load_variant(self.base, old, [plain(old_contract)])
                if not variant.lease.is_dir():
                    raise ValueError('Original independently reserved start variant required')
                self.original_variants.append(variant)
            directory = Path(record.get('actor_directory', old/'actor/0'/old_contract['task_id']))
            if (directory != directory.resolve() or directory.name != old_contract['task_id']
                    or directory.parent.parent != old/'actor'
                    or any(p.is_symlink() for p in (directory, directory.parent))):
                raise ValueError('Original actor directory must be an exact worker/task path')
            members = dict(index['members'])
            pointer = directory/'attempt-archive.json'
            if pointer.exists():
                raw = regular(pointer); value = json.loads(raw)
                partition_raw = regular(directory.parent/'diagnostic-members.json')
                partition = json.loads(partition_raw)
                expected_part = dict(prefix=old_contract['task_id'], archive=record['archive'],
                    manifest=record['index']['path'], archive_sha256=index['archive_sha256'],
                    manifest_sha256=record['index']['sha256'])
                if (value.get('version') != 'site-actor-node-local-archive-v1'
                        or value.get('task_id') != old_contract['task_id']
                        or value.get('archive_path') != record['archive']
                        or value.get('archive_sha256') != index['archive_sha256']
                        or value.get('raw_member_count') != len(index['members'])
                        or value.get('member_prefix') != ''
                        or value.get('partition_index_sha256') != sha(partition_raw)
                        or partition.get('version') != 'private-node-local-diagnostic-partition-index-v2'
                        or [p for p in partition.get('parts', [])
                            if p.get('prefix') == old_contract['task_id']] != [expected_part]):
                    raise ValueError('Existing actor archive pointer differs from verified original')
                members[pointer.name] = {'bytes': len(raw), 'sha256': sha(raw)}
            self.artifacts[directory] = members
            if revision and not record['_last_history_record']:
                continue
            key = sha((sid+'\n'+index['archive_sha256']).encode())
            if revision:
                from .source_revision_binding import fingerprint
                # One attempt for this specific revised contract, independent
                # of how its historical evidence was packaged or ordered.
                key = sha((DESCRIPTION_VERSION+'\n'+sid+'\n'+fingerprint(plain(contract))).encode())
            lease = self.base/('terminal-classification-repair-leases' if terminal_repair else 'answer-protocol-repair-leases')/key
            owner = {'version': spec['version'], 'wave': str(self.wave), 'authorization_sha256': spec_sha,
                     'source_task_id': sid, 'original_archive_sha256': index['archive_sha256']}
            self.leases.append((lease, owner))
        self.require_lease_owners()

    def require_lease_owners(self):
        for variant in getattr(self, 'original_variants', ()):
            variant.check_lease()
        for lease, owner in self.leases:
            if lease.exists() and (lease.is_symlink() or json.loads(regular(lease/'owner.json')) != owner):
                raise ValueError('This original attempt already has a different repair reservation')

    def permits_original_sibling(self, path, contract):
        return any(v.permits_sibling(path, contract) for v in self.original_variants)

    def original_sibling_sources(self):
        return set().union(*(v.family - {v.source} for v in self.original_variants))

    def permits_existing_artifact(self, file):
        file = Path(file)
        members = self.artifacts.get(file.parent.resolve())
        if members is None or file.name not in members:
            return False
        data = regular(file)
        return members[file.name] == {'bytes': len(data), 'sha256': sha(data)}

    def acquire(self):
        # mkdir is exclusive; an incomplete lease is not silently reclaimed.
        from .io_utils import atomic_write_json
        for lease, owner in self.leases:
            lease.parent.mkdir(exist_ok=True)
            lease.mkdir()
            atomic_write_json(lease/'owner.json', owner)


def load(base, wave, selected, *, terminal_query, fields):
    candidates = [Path(wave)/name for name in ('answer-protocol-repair.json', 'terminal-classification-repair.json', 'public-completion-revision.json', 'query-capture-repair.json')]
    present = [p for p in candidates if p.exists()]
    if not present: return None
    if len(present) != 1: raise ValueError('Only one explicit repair reason per wave')
    file = present[0]
    raw = regular(file)
    spec = json.loads(raw)
    from .query_capture_repair import VERSION as CAPTURE_VERSION, QueryCaptureAuthority
    if (spec.get('version') == CAPTURE_VERSION) != (file.name == 'query-capture-repair.json'):
        raise ValueError('Query capture repair file and reason do not match')
    if spec.get('version') == CAPTURE_VERSION:
        return QueryCaptureAuthority(base, wave, selected, spec, sha(raw), terminal_query=terminal_query)
    from .public_completion_attempt import VERSION as PUBLIC_COMPLETION_VERSION, PublicCompletionAuthority
    if (spec.get('version') == PUBLIC_COMPLETION_VERSION) != (file.name == 'public-completion-revision.json'):
        raise ValueError('Public-completion revision file and reason do not match')
    if spec.get('version') == PUBLIC_COMPLETION_VERSION:
        return PublicCompletionAuthority(base, wave, selected, spec, sha(raw), terminal_query=terminal_query)
    if (spec.get('version') == TERMINAL_VERSION) != (file.name == 'terminal-classification-repair.json'):
        raise ValueError('Repair file and reason do not match')
    from .task_definition_replacement import VERSION as REPLACEMENT_VERSION, DefinitionReplacementAuthority
    if spec.get('version') == REPLACEMENT_VERSION:
        return DefinitionReplacementAuthority(base, wave, selected, spec, sha(raw),
                                              terminal_query=terminal_query)
    return Authority(base, wave, selected, spec, sha(raw),
                     terminal_query=terminal_query, fields=fields)
