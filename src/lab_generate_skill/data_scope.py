"""One provenance-checked retrieval view for generation and saved SFT inputs.

Original banks remain immutable audit artifacts. Explicit hash-verified aliases
allow existing cluster arguments to select the current filtered view.
"""
import hashlib
import json
import unicodedata
from pathlib import Path


FIELDS = ('title', 'principle', 'when_to_apply')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def norm(text):
    return ' '.join(unicodedata.normalize('NFKC', text).casefold().split())


def member_skill_ids(row):
    """Bank representatives and their original candidate members share policy."""
    members = {row['skill_id']} if row.get('skill_id') else set()
    for generation_id in row.get('source_generation_ids', []):
        members.add('candidate_' + hashlib.sha256(generation_id.encode()).hexdigest()[:20])
    return members


def filter_bank(rows, blocked_ids, reserved_goals, *, excluded_skill_ids=()):
    kept = []
    removed = []
    excluded_skill_ids = set(excluded_skill_ids)
    for row in rows:
        ids = set(row.get('source_task_ids', []))
        if not ids:
            raise ValueError('Missing skill task provenance: ' + str(row.get('skill_id')))
        matching = sorted(ids & blocked_ids)
        goals = [goal for goal in row.get('source_goals', [])
                 if (row['domain'], norm(goal)) in reserved_goals]
        skills = sorted(member_skill_ids(row) & excluded_skill_ids)
        if matching or goals or skills:
            record = {'skill': row, 'blocked_source_task_ids': matching,
                      'heldout_source_goals': goals,
                      'rule': 'remove_entire_cluster_if_any_source_is_blocked'}
            if skills:
                record.update(excluded_member_skill_ids=skills,
                              rule='remove_entire_cluster_if_any_member_is_excluded')
            removed.append(record)
        else:
            kept.append(row)
    return kept, removed


def active_bank_path(root=None, requested=None, *, pointer=None):
    pointer = Path(pointer or Path(__file__).resolve().parents[2] / 'configs/data-active-scope.json')
    cfg = json.loads(pointer.read_text())
    bank = Path(cfg['bank'])
    if requested is not None and Path(requested).resolve() != bank.resolve():
        aliases = {Path(path).resolve(): expected
                   for path, expected in cfg.get('accepted_bank_aliases', {}).items()}
        requested = Path(requested)
        expected = aliases.get(requested.resolve())
        if expected is None:
            raise ValueError('Use the active filtered skill bank: ' + str(bank))
        if digest(requested) != expected:
            raise ValueError('Historical bank alias changed; rebuild the runtime view')
    if digest(bank) != cfg['bank_sha256']:
        raise ValueError('Active bank hash mismatch')
    for path, expected in cfg['policy_hashes'].items():
        if digest(path) != expected:
            raise ValueError('Data exclusion policy changed; rebuild active scope before generation')
    manifest = Path(cfg['scope_manifest'])
    if digest(manifest) != cfg['scope_manifest_sha256']:
        raise ValueError('Scope manifest changed')
    scope = json.loads(manifest.read_text())
    selection_path = cfg.get('runtime_skill_selection_policy')
    if selection_path:
        if selection_path not in cfg['policy_hashes']:
            raise ValueError('Runtime skill selection policy must be hash-bound')
        selected = set(json.loads(Path(selection_path).read_text())['excluded_skill_ids'])
        if not selected.issubset(scope.get('excluded_skill_ids', [])):
            raise ValueError('Scope omitted reviewed skill exclusions')
    rows = [json.loads(line) for line in bank.open() if line.strip()]
    _, removed = filter_bank(rows, set(scope['blocked_bank_source_task_ids']),
                             {tuple(value) for value in scope['reserved_goal_keys']},
                             excluded_skill_ids=scope.get('excluded_skill_ids', []))
    if removed:
        raise ValueError('Blocked provenance or candidate remains in active bank')
    return bank


def load_runtime_bank(root=None, requested=None, *, pointer=None):
    path = active_bank_path(root, requested, pointer=pointer)
    return [json.loads(line) for line in path.open() if line.strip()]


def require_runtime_references(refs, *, bank):
    """Reject stale retrieval context; do not silently change a verified input.

    Stage-1 refs retain IDs, whereas the actual generator chat has only the three
    text fields. Check both representations against the same active bank.
    """
    by_id = {row['skill_id']: row for row in bank}
    signatures = {tuple(row[field] for field in FIELDS) for row in bank}
    if not isinstance(refs, list) or len(refs) != 6:
        raise ValueError('Exactly six active runtime references are required')
    for ref in refs:
        if not isinstance(ref, dict) or any(not isinstance(ref.get(field), str) for field in FIELDS):
            raise ValueError('Malformed retrieved skill')
        signature = tuple(ref[field] for field in FIELDS)
        if ref.get('skill_id'):
            active = by_id.get(ref['skill_id'])
            if active is None or tuple(active[field] for field in FIELDS) != signature:
                raise ValueError('Saved retrieval references a skill outside the active runtime bank: '
                                 + str(ref['skill_id']))
            for field in ('source_task_ids', 'source_goals', 'source_generation_ids'):
                if field in ref and ref[field] != active.get(field):
                    raise ValueError('Saved retrieval provenance changed: ' + ref['skill_id'])
        elif signature not in signatures:
            raise ValueError('Saved retrieval text is outside the active runtime bank')


def require_sft_runtime_references(records, *, bank):
    """Validate saved chat inputs before training can load a model or GPU."""
    for record in records:
        users = [message for message in record['messages'] if message.get('role') == 'user']
        if len(users) != 1:
            raise ValueError('SFT input must contain one generator user message')
        try:
            body = json.loads(users[0]['content'])
        except (ValueError, TypeError) as exc:
            raise ValueError('SFT generator user message must be structured JSON') from exc
        require_runtime_references(body.get('retrieved_skills'), bank=bank)
