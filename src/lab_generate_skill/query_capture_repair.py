"""One evidence-repair attempt for a legacy query that did not save references.

This preserves the historical score without treating it as independently
verified. Tasks with a saved reference, ordinary verified failures, changed
goals, live jobs, or another repair reservation cannot use this path.
"""
import ast
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from .answer_protocol_repair import Authority, pinned, plain, regular, sha
from .site_query_rules import require_query_admission
from .site_preferences_rules import require_preferences_admission
from .site_membership_rules import require_membership_admission
from .site_cart_rules import require_cart_admission

VERSION = 'query-reference-capture-repair-v1'
REASON = 'legacy_query_reference_not_persisted'
MISSING = {'query-baseline.json', 'query-state.json'}
PREFERENCE_MISSING = {'preferences-state.json'}
MEMBERSHIP_MISSING = {'membership-baseline.json', 'membership-state.json'}
CART_MISSING = {'cart-baseline.json', 'cart-state.json'}


def capture_fields(contract):
    """Only families with an implemented native-state collector can repair gaps."""
    if sum(bool(contract.get(k)) for k in ('query', 'preferences', 'membership', 'cart')) > 1:
        raise ValueError('Ambiguous reference capture family')
    if (contract.get('domain'), contract.get('query', {}).get('family')) in {
            ('gitlab', 'gitlab_project'), ('reddit', 'reddit_forum'),
            ('shopping', 'shopping_product'), ('shopping', 'shopping_cart'),
            ('shopping', 'shopping_order')}:
        return MISSING, require_query_admission
    if contract.get('domain') == 'reddit' and contract.get('preferences'):
        return PREFERENCE_MISSING, require_preferences_admission
    if contract.get('domain')=='reddit' and contract.get('membership',{}).get('collection')=='hidden_forums':
        from .reddit_hidden_membership import validate
        validate(contract)
        return MEMBERSHIP_MISSING, require_membership_admission
    if (contract.get('domain') == 'shopping'
            and contract.get('membership', {}).get('collection') in ('wishlist', 'compare')):
        return MEMBERSHIP_MISSING, require_membership_admission
    if contract.get('domain') in ('gitlab','reddit') and contract.get('membership'):
        membership = contract['membership']
        if ('collection' in membership or type(membership.get('object_id')) is not int
                or membership['object_id'] <= 0 or type(membership.get('desired_present')) is not bool
                or not isinstance(membership.get('object_name'), str)
                or membership.get('object_path') != ('/f/' if contract['domain']=='reddit' else '/') + membership['object_name']
                or any(part in ('', '.', '..') for part in membership['object_name'].split('/'))
                or (contract['domain']=='reddit' and '/' in membership['object_name'])
                or any(char in membership['object_name'] for char in ('?', '#', '\\'))):
            raise ValueError('Explicit native subscription or GitLab star membership required')
        return MEMBERSHIP_MISSING, require_membership_admission
    if (contract.get('domain') == 'shopping'
            and contract.get('cart', {}).get('operation') in ('add_products', 'remove_product', 'clear')):
        return CART_MISSING, require_cart_admission
    raise ValueError('No reviewed native reference collector for this family')

# Historical CPU-only clone validation, verified against Slurm's saved script.
# This pins execution provenance, not a task-specific evaluator exception.
CLONE_CPU_SCRIPT = 'f33ffe16176e6a6f30586e5ba8972c12442e1bd0ada9ec25a1ae0052ecc078b1'


def completed_cpu_manifests(base, wave, contract, records, terminal_query):
    """Release only an exact completed CPU reservation; preserve old evidence."""
    from legacy_selected_source_handoff import _actual_frozen_submission
    if not isinstance(records, list):
        raise ValueError('CPU reservations must be an explicit list')
    allowed = set()
    sid = contract.get('source_task_id', contract['task_id'])
    for record in records:
        old = Path(record['wave'])
        if (old.parent != base or old == wave or old != old.resolve()
                or not old.is_dir() or old.is_symlink()
                or any(old.glob('actor*')) or any(old.glob('*actor*claim*'))
                or (old/'first-actor-claim').exists()):
            raise ValueError('Exact CPU-only sibling without actor artifacts required')
        manifest = old/'contracts.jsonl'; script = old/'controls.sbatch'
        proof = old/'controls'/'gitlab'/'admissions'/(contract['task_id']+'.json')
        for key, path in (('manifest', manifest), ('script', script), ('proof', proof)):
            if record[key].get('path') != str(path):
                raise ValueError('CPU reservation evidence belongs to another wave')
            pinned(record[key])
        if manifest in allowed or sha(regular(script)) != CLONE_CPU_SCRIPT:
            raise ValueError('Duplicate or unreviewed historical CPU script')
        matching = [r for r in map(json.loads, regular(manifest).decode().splitlines())
                    if r.get('source_task_id', r.get('task_id')) == sid]
        if matching != [plain(contract)]:
            raise ValueError('CPU reservation changed the selected task')
        job = record.get('job_id')
        if (not isinstance(job, str) or not job.endswith('_2')
                or not job[:-2].isdecimal()
                or terminal_query(job) != {job: 'COMPLETED'}):
            raise ValueError('Exact completed GitLab CPU array child required')
        command, actual_script = _actual_frozen_submission(job)
        if command != ['sbatch', '--array=2', str(script)] or actual_script != regular(script):
            raise ValueError('CPU reservation differs from actual scheduler submission')
        require_query_admission(contract, json.loads(regular(proof)))
        allowed.add(manifest)
    return allowed


def require_collector(source, missing=None):
    """The tested current collector must save both actual reference objects."""
    missing = MISSING if missing is None else missing
    found = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id != 'atomic_write_json' or len(node.args) != 2:
            continue
        path = node.args[0]
        if (isinstance(path, ast.BinOp) and isinstance(path.op, ast.Div)
                and isinstance(path.left, ast.Name) and path.left.id == 'dest'
                and isinstance(path.right, ast.Constant) and path.right.value in missing):
            found[path.right.value] = ast.dump(node.args[1])
    expected = {
        'query-baseline.json': ast.dump(ast.parse('query_before', mode='eval').body),
        'query-state.json': ast.dump(ast.parse("{'initial':query_before,'final':query_after}", mode='eval').body),
        'preferences-state.json': ast.dump(ast.parse("{'initial':preferences_before,'final':preferences_after}", mode='eval').body),
        'membership-baseline.json': ast.dump(ast.parse('membership_before', mode='eval').body),
        'membership-state.json': ast.dump(ast.parse("{'initial':membership_before,'final':membership_after}", mode='eval').body),
    }
    expected.update({
        'cart-baseline.json': ast.dump(ast.parse('cart_before', mode='eval').body),
        'cart-state.json': ast.dump(ast.parse("{'initial':cart_before,'final':cart_after}", mode='eval').body),
    })
    expected = {name: expected[name] for name in missing}
    if found != expected:
        raise ValueError('Current collector must persist actual initial and final references')


def local_path(url):
    value = urlsplit(url)
    return value.path, value.query


def prior_revision_reservations(base, wave, contract, records, terminal_query):
    """Retain closed predecessor evidence when repairing an already-run revision.

    This grants no attempt for a different goal: the caller separately verifies
    an actual execution of the exact current contract and its missing captures.
    Only the predecessor's reservation/artifacts are acknowledged here.
    """
    from legacy_selected_source_handoff import _actual_frozen_submission
    from .public_completion_attempt import _history_files
    from .control_job_set import TERMINAL
    if not isinstance(records, list):
        raise ValueError('Explicit predecessor reservation records required')
    manifests = {}; artifacts = {}; attempts = 0
    sid = contract.get('source_task_id', contract['task_id'])
    for record in records:
        old = Path(record['wave']); file = old/'contracts.jsonl'
        if (old.parent != base or old == wave or not old.is_dir()
                or record['manifest']['path'] != str(file) or file.resolve() in manifests):
            raise ValueError('Distinct exact predecessor sibling required')
        if old.is_symlink() and (record.get('wave_resolved') != str(old.resolve())
                                 or record.get('wave_symlink') != os.readlink(old)):
            raise ValueError('Predecessor offload mapping must be pinned')
        matches = [plain(r) for r in map(json.loads, pinned(record['manifest']).decode().splitlines())
                   if r.get('source_task_id', r.get('task_id')) == sid]
        if len(matches) != 1:
            raise ValueError('One exact predecessor source contract required')
        before = matches[0]; after = plain(contract)
        if before.get('task_id') != sid or after.get('task_id') == sid:
            raise ValueError('Only a declared direct original-to-derived mapping qualifies')
        changed = {k for k in before.keys() | after.keys() if before.get(k) != after.get(k)}
        start = after.get('start_revision', {}); goal = after.get('goal_revision', {})
        if (changed <= {'task_id', 'start_path', 'start_revision'}
                and before['start_path'] != after['start_path']
                and start.get('original_start') == before['start_path']
                and isinstance(start.get('reason'), str) and start['reason'].strip()):
            pass
        elif (changed <= {'task_id', 'goal', 'source_goal', 'goal_revision', 'task_text_changed'}
                and before['goal'] != after['goal'] and after.get('source_goal') == before['goal']
                and after.get('task_text_changed') is True
                and goal.get('original_evaluation_equivalence_claimed') is False
                and isinstance(goal.get('reason'), str) and goal['reason'].strip()):
            pass
        else:
            raise ValueError('Predecessor changed more than the declared public goal or start')
        jobs = record.get('jobs', [])
        if not jobs or len({r['job_id'] for r in jobs}) != len(jobs):
            raise ValueError('Distinct real terminal predecessor jobs required')
        for job in jobs:
            states = terminal_query(str(job['job_id']))
            if not states or states != job.get('states') or any(s not in TERMINAL for s in states.values()):
                raise ValueError('Predecessor job remains live or changed')
            command, script = _actual_frozen_submission(str(job['job_id']))
            script_path = Path(job['script']['path'])
            if (script_path.parent != old or script_path.name not in ('controls.sbatch', 'online.sbatch')
                    or command != job['submit_command'] or not command or command[0] != 'sbatch'
                    or command[-1] != str(script_path) or script != pinned(job['script'])):
                raise ValueError('Predecessor job does not bind its actual frozen script')
        for history in record.get('actor_history', []):
            directory = Path(history['actor_directory'])
            if (directory.parent.parent != old/'actor' or directory.name != before['task_id']
                    or directory.resolve().parent.parent != old.resolve()/'actor'
                    or any(p.is_symlink() for p in (directory, directory.parent, old/'actor'))
                    or directory.resolve() in artifacts):
                raise ValueError('Exact distinct predecessor actor directory required')
            values, members = _history_files(history, directory, before['task_id'])
            marker = values['attempt-started.json']; result = values['result.json']; trace = values['trajectory.json']
            job = str(history['job_id']); states = terminal_query(job)
            inputs = [json.loads(m['content']) for m in values['generation-000.json']['messages'] if m['role'] == 'user']
            def same_goal(value):
                return isinstance(value, str) and (value == before['goal'] or value.startswith(before['goal']+'\n'))
            if (not states or states != history.get('states') or any(s not in TERMINAL for s in states.values())
                    or marker != {'job': job, 'task': before['task_id'], 'scripted': False}
                    or result.get('task_id') != before['task_id'] or result.get('actor_attempts') != 1
                    or not same_goal(trace.get('task_instruction')) or len(inputs) != 1
                    or not same_goal(inputs[0].get('goal'))
                    or local_path(trace.get('provenance', {}).get('start_url', '')) != local_path(before['start_path'])
                    or local_path(inputs[0].get('url', '')) != local_path(before['start_path'])):
                raise ValueError('Actual predecessor attempt identity or input changed')
            artifacts[directory.resolve()] = members; attempts += 1
        manifests[file.resolve()] = {sid}
    return manifests, artifacts, attempts


def closed_option_preview_manifests(base, wave, contract, records, terminal_query):
    """Release failed CPU-only option previews without erasing old evidence.

    Only documenting the existing any-valid native option policy may differ.
    Goal, target, quantity, start, split and every other contract field stay
    exact. This never exempts actor artifacts; the ordinary source guard still
    discovers and rejects any historical or newly-created actor attempt.
    """
    from copy import deepcopy
    from legacy_selected_source_handoff import _actual_frozen_submission
    from .control_job_set import TERMINAL
    if not isinstance(records, list):
        raise ValueError('Explicit closed CPU option previews required')
    if records and (contract.get('domain') != 'shopping'
            or contract.get('cart', {}).get('operation') != 'add_products'):
        raise ValueError('Only an unchanged native cart addition may release an option preview')
    sid = contract.get('source_task_id', contract['task_id']); allowed = {}
    for record in records:
        old = Path(record['wave'])
        if old.parent != base or old == wave or not old.is_dir():
            raise ValueError('Exact distinct predecessor sibling required')
        if old.is_symlink() and (record.get('wave_resolved') != str(old.resolve())
                or record.get('wave_symlink') != os.readlink(old)):
            raise ValueError('Closed preview offload mapping must be pinned')
        manifests = record.get('manifests', [])
        if not manifests or len({r['path'] for r in manifests}) != len(manifests):
            raise ValueError('Distinct original source reservation manifests required')
        before = None
        for item in manifests:
            file = Path(item['path'])
            if (file.parent != old or file.suffix != '.jsonl'
                    or not file.name.startswith(('contracts', 'tasks')) or file.resolve() in allowed):
                raise ValueError('Only exact original manifest reservations may be released')
            matches = [plain(c) for c in map(json.loads, pinned(item).decode().splitlines())
                       if c.get('source_task_id', c.get('task_id')) == sid]
            if len(matches) != 1 or before is not None and before != matches[0]:
                raise ValueError('One unchanged source contract across predecessor manifests required')
            before = matches[0]; allowed[file.resolve()] = {sid}
        after = plain(contract); normalized = deepcopy(after)
        note = normalized.pop('completion_scope_note', None)
        if not isinstance(note, str) or not note.strip():
            raise ValueError('The native option completion scope must be documented')
        products = normalized.get('cart', {}).get('products', [])
        if not products or any(p.pop('required_option_policy', None) != 'any_valid' for p in products):
            raise ValueError('Only documenting any-valid required options is permitted')
        if normalized != before or before.get('task_id') != contract['task_id']:
            raise ValueError('Closed option preview changed the native task')
        preview = record['failed_control']
        file = Path(preview['path'])
        if not file.resolve().is_relative_to(old.resolve()) or file.name != 'result.json':
            raise ValueError('Original failed native control must belong to the predecessor')
        failure = json.loads(pinned(preview))
        if (failure.get('task_id') != sid or failure.get('passed') is not False
                or failure.get('cycles') != [] or failure.get('api_calls') != 0
                or not failure.get('diagnostic')):
            raise ValueError('Incomplete failed CPU preview required; do not release a passed admission')
        jobs = record.get('jobs', [])
        if not jobs or len({j['job_id'] for j in jobs}) != len(jobs):
            raise ValueError('Distinct real predecessor CPU jobs required')
        for job in jobs:
            states = terminal_query(str(job['job_id']))
            if not states or states != job.get('states') or any(s not in TERMINAL for s in states.values()):
                raise ValueError('Predecessor CPU job is not confirmed terminal')
            command, script = _actual_frozen_submission(str(job['job_id']))
            script_file = Path(job['script']['path'])
            if (script_file.parent != old or not script_file.name.startswith('controls')
                    or script_file.suffix != '.sbatch' or command != job['submit_command']
                    or not command or command[0] != 'sbatch' or command[-1] != str(script_file)
                    or script != pinned(job['script']) or b'probe_site_cart_batch.py' not in script):
                raise ValueError('Closed CPU preview must bind its actual native control script')
        # Never use these manifests to hide an actor record or another live run.
        for root in old.glob('actor*'):
            if not root.is_dir(): continue
            selected = [root / sid] + [w / sid for w in root.iterdir() if w.is_dir()]
            if any(d.exists() for d in selected):
                raise ValueError('A CPU preview with source actor artifacts cannot be released')
    return allowed


class QueryCaptureAuthority(Authority):
    def __init__(self, base, wave, selected, spec, spec_sha, *, terminal_query):
        self.base = Path(base).resolve(); self.wave = Path(wave).resolve()
        self.spec_sha = spec_sha; self.superseded = {}; self.artifacts = {}
        self.leases = []; self.original_variants = []; self.reason = REASON
        if (spec.get('version') != VERSION or spec.get('reason') != REASON
                or spec.get('wave') != str(self.wave) or self.wave.parent != self.base):
            raise ValueError('Exact query capture repair scope required')
        chosen = {c.get('source_task_id', c['task_id']): c for c in selected}
        records = spec.get('sources', [])
        if (not chosen or len(chosen) != len(selected) or len(records) != len(chosen)
                or {r['source_task_id'] for r in records} != set(chosen)):
            raise ValueError('Repair must cover exactly the selected distinct sources')
        project = Path(__file__).resolve().parents[2]
        collector = regular(project/'scripts/run_site_navigation_once.py')
        if sha(collector) != spec.get('current_collector_sha256'):
            raise ValueError('Capture repair does not bind the current collector')
        review = json.loads(pinned(spec['review']))
        if review.get('version') != 'retained-query-capture-repair-intake-v1':
            raise ValueError('Independent capture-gap review required')
        self.previous_attempts = len(records)
        for record in records:
            sid = record['source_task_id']; c = chosen[sid]
            missing, require_admission = capture_fields(c)
            require_collector(collector, missing)
            if c.get('heldout_quarantine') or c.get('eligible_for_training'):
                raise ValueError('Only admitted non-heldout reference capture gaps qualify')
            proof = json.loads(regular(c['admission_result']))
            require_admission(c, proof)
            old = Path(record['old_wave'])
            directory = Path(record['actor_directory'])
            root_name = record.get('legacy_actor_root', 'actor')
            # Early Shopping collection workers used named actor roots. Keep
            # this explicit and source-bound; never discover arbitrary roots.
            if root_name != 'actor':
                import re
                if (missing not in (MEMBERSHIP_MISSING,CART_MISSING) or not isinstance(root_name, str)
                        or not re.fullmatch(r'actor-(?:[a-z]+(?:-[a-z]+)*-)?v[1-9][0-9]*', root_name)):
                    raise ValueError('Unreviewed legacy actor directory layout')
            actor_root = old/root_name
            relocated = old.is_symlink()
            if (old.parent != self.base or old == self.wave or not old.is_dir()
                    or directory.parent.parent != actor_root or directory.name != c['task_id']
                    or directory.resolve().parent.parent != old.resolve()/root_name
                    or any(p.is_symlink() for p in (directory, directory.parent, actor_root))):
                raise ValueError('Exact original sibling attempt required')
            if relocated and (record.get('old_wave_resolved') != str(old.resolve())
                              or record.get('old_wave_symlink') != os.readlink(old)):
                raise ValueError('Historical offload mapping must be explicitly pinned')
            states = terminal_query(str(record['old_job_id']))
            if (not states or states != record.get('terminal_states')
                    or any(s not in ('COMPLETED', 'FAILED', 'CANCELLED', 'TIMEOUT',
                                     'OUT_OF_MEMORY', 'NODE_FAIL', 'PREEMPTED') for s in states.values())):
                raise ValueError('Old query job must be confirmed terminal')
            from .capture_repair_history import read_history
            members, history, artifact_members = read_history(directory, record, MISSING | PREFERENCE_MISSING | MEMBERSHIP_MISSING | CART_MISSING)
            values = {name:json.loads(history[name])for name in ('result.json','trajectory.json','attempt-started.json','generation-000.json')if name in history}
            if len(values) != 4:
                raise ValueError('Original result, trace, claim and actual model input required')
            result, trace = values['result.json'], values['trajectory.json']
            if (values['attempt-started.json'] != {'job': str(record['old_job_id']), 'task': c['task_id'], 'scripted': False}
                    or result.get('task_id') != c['task_id'] or result.get('actor_attempts') != 1
                    or result.get('evaluation', {}).get('status') not in
                       (('failure', 'unknown', 'success') if missing in (MEMBERSHIP_MISSING,CART_MISSING,PREFERENCE_MISSING) else ('failure', 'unknown'))
                    or result.get('error') is not None or trace.get('error') is not None
                    or not isinstance(trace.get('task_instruction'), str)
                    or not (trace['task_instruction'] == c['goal'] or trace['task_instruction'].startswith(c['goal']+'\n'))
                    or local_path(trace.get('provenance', {}).get('start_url', '')) != local_path(c['start_path'])):
                raise ValueError('Executed unchanged legacy query without runtime error required')
            inputs = [json.loads(m['content']) for m in values['generation-000.json']['messages'] if m['role'] == 'user']
            if (len(inputs) != 1 or not (inputs[0].get('goal') == c['goal'] or inputs[0].get('goal', '').startswith(c['goal']+'\n'))
                    or local_path(inputs[0].get('url', '')) != local_path(c['start_path'])):
                raise ValueError('Original actual prompt and start differ from repair task')
            reviewed = [r for r in review.get('sources', []) if r.get('source_task_id') == sid]
            if (len(reviewed) != 1 or reviewed[0].get('review_disposition') != 'historical_score_not_independently_reproducible_without_actual_reference_capture'
                    or set(reviewed[0].get('missing_files', [])) != missing
                    or reviewed[0].get('current_goal') != c['goal']
                    or reviewed[0].get('old_result') != {'path': str(directory/'result.json'), 'sha256': members['result.json']['sha256']}
                    or reviewed[0].get('old_trace') != {'path': str(directory/'trajectory.json'), 'sha256': members['trajectory.json']['sha256']}
                    or reviewed[0].get('current_proof', {}).get('sha256') != sha(regular(c['admission_result']))
                    or reviewed[0].get('archived_history') != record.get('archived_history')):
                raise ValueError('Independent review must pin the exact missing-evidence attempt and proof')
            if missing in (MEMBERSHIP_MISSING,CART_MISSING) or (missing == PREFERENCE_MISSING and result['evaluation']['status'] == 'success'):
                row = reviewed[0]
                terminal = directory/'terminal-page.json'
                if (row.get('actor_directory') != str(directory)
                        or row.get('legacy_actor_root', 'actor') != root_name
                        or row.get('historical_status') != result['evaluation']['status']
                        or row.get('verified_outcome') is not False
                        or row.get('terminal_page') != {'path': str(terminal), 'sha256': sha(history['terminal-page.json'])}
                        or row.get('unverified_predicates') != ((['account_reference','target_hidden_membership','other_hidden_memberships_unchanged','forum_subscriptions_unchanged']if c.get('membership',{}).get('collection')=='hidden_forums'else ['target_membership', 'other_memberships_unchanged'] + (['other_collections_unchanged'] if c['domain'] == 'shopping' else [])) if missing == MEMBERSHIP_MISSING else ['requested_settings_saved', 'unrelated_settings_unchanged'] if missing == PREFERENCE_MISSING else {'add_products': ['requested_products_added', 'unrelated_items_unchanged', 'coupon_unchanged'], 'remove_product': ['requested_item_removed', 'unrelated_items_unchanged', 'coupon_unchanged'], 'clear': ['cart_empty', 'coupon_unchanged']}[c['cart']['operation']])):
                    raise ValueError('Missing native state evidence must not turn a verified success into a retry')
            found = False
            for manifest in set(old.glob('contracts*.jsonl')) | set(old.glob('tasks*.jsonl')):
                matches = [r for r in map(json.loads, manifest.read_text().splitlines())
                           if r.get('source_task_id', r.get('task_id')) == sid]
                if matches:
                    if any(plain(r) != plain(c) for r in matches):
                        raise ValueError('Task changed; capture repair cannot revise its definition')
                    found = True; self.superseded.setdefault(manifest.resolve(), set()).add(sid)
            if not found:
                raise ValueError('Original task contract is missing')
            for manifest in completed_cpu_manifests(self.base, self.wave, c,
                    record.get('completed_cpu_reservations', []), terminal_query):
                self.superseded.setdefault(manifest, set()).add(sid)
            for file, sources in closed_option_preview_manifests(self.base, self.wave, c,
                    record.get('closed_cpu_option_previews', []), terminal_query).items():
                self.superseded.setdefault(file, set()).update(sources)
            self.artifacts[directory.resolve()] = artifact_members
            predecessors, prior_artifacts, prior_attempts = prior_revision_reservations(
                self.base, self.wave, c, record.get('prior_revision_reservations', []), terminal_query)
            for manifest, sources in predecessors.items():
                self.superseded.setdefault(manifest, set()).update(sources)
            if self.artifacts.keys() & prior_artifacts.keys():
                raise ValueError('Predecessor attempt duplicates the capture-gap attempt')
            self.artifacts.update(prior_artifacts); self.previous_attempts += prior_attempts
            key = sha((VERSION+'\n'+sid+'\n'+members['result.json']['sha256']).encode())
            lease = self.base/'query-capture-repair-leases'/key
            owner = {'version': VERSION, 'wave': str(self.wave), 'authorization_sha256': spec_sha,
                     'source_task_id': sid, 'original_result_sha256': members['result.json']['sha256']}
            self.leases.append((lease, owner))
        from .identical_source_capture_repair import attach_identical_histories
        attach_identical_histories(self, chosen, spec, spec_sha, terminal_query=terminal_query, authority_type=QueryCaptureAuthority)
        self.require_lease_owners()
