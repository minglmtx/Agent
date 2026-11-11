"""One explicit derived-task attempt after a terminal historical reservation.

Missing historical outputs remain missing; this never certifies zero inference,
rewrites a score, or reuses the old admission for the revised task. The ordinary
launcher still validates new controls, heldout aliases and other reservations.
"""
import json
from pathlib import Path
from .answer_protocol_repair import Authority, pinned, plain, regular, sha
from .source_revision_binding import binding, fingerprint

VERSION = 'reviewed-task-definition-replacement-v1'
TERMINAL = {'COMPLETED', 'FAILED', 'CANCELLED', 'TIMEOUT', 'OUT_OF_MEMORY', 'NODE_FAIL', 'PREEMPTED'}


def require_mapping(old, new):
    binding(old); binding(new)
    for key in ('source_task_id', 'domain', 'original_goal', 'source_trace_ids', 'heldout_quarantine'):
        if old[key] != new[key]:
            raise ValueError('Replacement changed original source or split binding')
    for key in ('recorded_start_urls', 'recorded_start_paths'):
        if sorted(old[key]) != sorted(new[key]):
            raise ValueError('Replacement changed the recorded source starts')
    if (old['task_id'] == new['task_id'] or old['goal'] == new['goal']
            or new.get('task_text_changed') is not True):
        raise ValueError('A separately named, explicitly changed public goal is required')
    for key in ('training_admitted', 'normal_gate_passed', 'eligible_for_training'):
        if new.get(key) is True:
            raise ValueError('Definition replacement cannot grant training admission')


class DefinitionReplacementAuthority(Authority):
    def __init__(self, base, wave, selected, spec, spec_sha, *, terminal_query):
        self.base = Path(base).resolve(); self.wave = Path(wave).resolve()
        self.spec_sha = spec_sha; self.superseded = {}; self.artifacts = {}; self.leases = []
        self.reason = 'reviewed_task_definition_replacement'
        # Deliberately unknown, rather than inferred from absent raw files.
        self.previous_attempts = None
        if (spec.get('version') != VERSION or spec.get('reason') != self.reason
                or spec.get('wave') != str(self.wave) or self.wave.parent != self.base):
            raise ValueError('Exact replacement scope and version required')
        chosen = {c['source_task_id']: plain(c) for c in selected}
        records = spec.get('sources', [])
        if (len(chosen) != len(selected) or len(records) != len(chosen)
                or {r['source_task_id'] for r in records} != set(chosen)):
            raise ValueError('Replacement must cover exactly the selected sources')
        for record in records:
            sid = record['source_task_id']; candidate = chosen[sid]
            original = json.loads(pinned(record['original_contract']))
            require_mapping(original, candidate)
            if (record.get('candidate_contract_sha256') != fingerprint(candidate)
                    or record.get('old_result_disposition') != 'retained_not_reclassified'
                    or record.get('historical_inference_count') is not None):
                raise ValueError('Exact revised contract and unchanged historical result required')
            review = json.loads(pinned(record['review']))
            if (review.get('source_task_id') != sid
                    or review.get('old_contract_sha256') != fingerprint(original)
                    or review.get('new_contract_sha256') != fingerprint(candidate)
                    or review.get('equivalent_to_original_evaluation') is not False
                    or not review.get('reason') or not review.get('historical_evidence')):
                raise ValueError('Source-bound definition and historical review required')
            if original['start_path'] != candidate['start_path']:
                change = review.get('start_change', {})
                if (change.get('old_start') != original['start_path']
                        or change.get('new_start') != candidate['start_path']
                        or change.get('equivalent_to_original_start') is not False
                        or not change.get('reason')):
                    raise ValueError('Changed historical start requires an explicit mapping')
            for evidence in review['historical_evidence']:
                pinned(evidence)
            old = Path(record['old_wave'])
            if (old != old.resolve() or old.parent != self.base or old == self.wave
                    or old.is_symlink()):
                raise ValueError('Exact old sibling wave required')
            manifests = record.get('manifests', [])
            if not manifests:
                raise ValueError('Original source reservations must be pinned')
            for pin in manifests:
                path = Path(pin['path'])
                if (path.parent != old or not path.name.endswith('.jsonl')
                        or not path.name.startswith(('contracts', 'tasks'))):
                    raise ValueError('Only exact old reservation manifests can be superseded')
                matches = [plain(json.loads(line)) for line in pinned(pin).decode().splitlines()
                           if json.loads(line).get('source_task_id', json.loads(line)['task_id']) == sid]
                if not matches or any(c != original for c in matches):
                    raise ValueError('Old reservation changed its original contract')
                self.superseded.setdefault(path.resolve(), set()).add(sid)
            histories = record.get('historical_jobs', [])
            if not histories or len({h['job_id'] for h in histories}) != len(histories):
                raise ValueError('Distinct historical jobs required')
            for history in histories:
                job = history['job_id']
                if not isinstance(job, str) or not job.isdecimal():
                    raise ValueError('Exact historical job ID required')
                actual = terminal_query(job)
                if actual != {job: history['terminal_state']} or history['terminal_state'] not in TERMINAL:
                    raise ValueError('Historical job is live, missing, or changed')
                receipt = json.loads(pinned(history['submission']))
                if str(receipt.get('job_id')) != job:
                    raise ValueError('Historical submission job differs')
                plan_path = Path(history['plan']['path'])
                if plan_path.name != 'plan.json' or plan_path.parent.parent != self.base/'actor-bundles':
                    raise ValueError('Historical actor bundle required')
                command = receipt.get('command', [])
                if (str(plan_path.parent) not in command or history['plan']['sha256'] not in command):
                    raise ValueError('Submission does not bind the historical plan')
                plan = json.loads(pinned(history['plan']))
                waves = [w for w in plan.get('waves', []) if w.get('wave') == str(old)]
                if len(waves) != 1:
                    raise ValueError('Historical plan does not own the old wave')
                w = waves[0]
                if (sha(regular(w['manifest'])) != w['manifest_sha256']
                        or not any(p.get('source_task_id', p.get('task_id')) == sid
                                   and p['task_id'] == original['task_id'] for p in w['proofs'])):
                    raise ValueError('Historical plan does not own the original task')
            # No raw artifact exemption: any retained actor data still blocks
            # submission until independently reviewed by a supported mechanism.
            key = sha((VERSION+'\n'+sid+'\n'+fingerprint(candidate)).encode())
            lease = self.base/'answer-protocol-repair-leases'/key
            owner = {'version': VERSION, 'wave': str(self.wave),
                     'authorization_sha256': spec_sha, 'source_task_id': sid,
                     'original_contract_sha256': fingerprint(original),
                     'candidate_contract_sha256': fingerprint(candidate)}
            self.leases.append((lease, owner))
        self.require_lease_owners()
