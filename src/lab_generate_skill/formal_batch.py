"""Metadata-only formal queue, reusing the qualified single-source lifecycle.

Code qualification belongs to a frozen build. Scanning checks task bindings,
evidence references and ownership; it never runs website controls or models.
One batch authorization covers its selected sources. Concurrent source budgets
are disjoint reservations in that authorization, not independent spending caps.
"""
from contextlib import contextmanager
from copy import deepcopy
import csv
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path


def require(value, message):
    if not value:
        raise ValueError(message)


def pin(path):
    path = Path(path).resolve()
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            digest.update(block)
    return dict(path=str(path), sha256=digest.hexdigest())


def read(ref):
    require(pin(ref['path']) == ref, 'Pinned batch input changed: ' + ref['path'])
    return json.loads(Path(ref['path']).read_text())


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    return pin(path)


def money(value):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
            'Finite nonnegative dollar amount required')
    return float(value)


def prepared_registered_goal(plan, contract):
    if plan.get('native_source_adapter') == 'registered_gitlab_native_goal_v1':
        from . import native_goal_dispatch, gitlab_boundary_goal_runtime, gitlab_persisted_goal_runtime
        modules = {'gitlab_boundary_goal':gitlab_boundary_goal_runtime, 'gitlab_persisted_goal':gitlab_persisted_goal_runtime}
        catalog=read(plan['source_binding_catalog']); source=plan['sources'][0]
        require(catalog['version']=='registered-gitlab-native-goal-sft-bindings-v1'
                and catalog['training_pointer']==plan['training_pointer'], 'Native GitLab goal registration differs')
        binding=catalog['sources'][source['source_task_id']]
        require(all(source[k]==binding[k] for k in ('source_task_id','active_task_id','runtime_task_id','domain',
                'native_contract','admission','profile','evaluator_version')), 'Prepared native GitLab goal source differs')
        native=read(source['native_contract']); module=native_goal_dispatch.protocol(native)
        require(module is modules.get(binding['protocol']) and module.enabled(native)
                and native['source_task_id']==source['source_task_id'] and native['task_id']==source['runtime_task_id']
                and native['domain']==source['domain']=='gitlab' and source['evaluator_version']==module.VERSION,
                'Native GitLab goal identity/evaluator differs')
        require(contract['public_goal']==binding['actor_goal']==native_goal_dispatch.public_goal(native)
                and binding['public_goal'] in (native['goal'],binding['actor_goal']), 'Native GitLab public interface differs')
        return binding['public_goal']
    if plan.get('native_source_adapter') == 'registered_shopping_read_v1':
        from . import native_goal_dispatch, shopping_cart_view_runtime, shopping_page_visit_runtime, shopping_complete_training_query_runtime
        modules = {'shopping_cart_view':shopping_cart_view_runtime, 'shopping_page_visit':shopping_page_visit_runtime,
                   'shopping_complete_query':shopping_complete_training_query_runtime}
        catalog=read(plan['source_binding_catalog']); source=plan['sources'][0]
        require(catalog['version']=='registered-shopping-native-read-sft-bindings-v1'
                and catalog['training_pointer']==plan['training_pointer'], 'Native Shopping reading registration differs')
        binding=catalog['sources'][source['source_task_id']]
        require(all(source[k]==binding[k] for k in ('source_task_id','active_task_id','runtime_task_id','domain',
                'native_contract','admission','profile','evaluator_version')), 'Prepared native Shopping reading source differs')
        native=read(source['native_contract']); module=native_goal_dispatch.protocol(native)
        require(module is modules.get(binding['protocol']) and module.enabled(native)
                and native['source_task_id']==source['source_task_id'] and native['task_id']==source['runtime_task_id']
                and native['domain']==source['domain']=='shopping' and source['evaluator_version']==module.VERSION,
                'Native Shopping reading identity/evaluator differs')
        require(contract['public_goal']==binding['actor_goal']==module.public_goal(native)
                and binding['public_goal'] in (native['goal'],binding['actor_goal']), 'Native Shopping public interface differs')
        return binding['public_goal']
    if plan.get('native_source_adapter') == 'registered_map_finite_v1':
        from . import map_history_layer_runtime as finite_runtime
        catalog = read(plan['source_binding_catalog']); source = plan['sources'][0]
        require(catalog['version'] == 'registered-map-finite-sft-bindings-v1'
                and catalog['training_pointer'] == plan['training_pointer'], 'Finite Map registration differs')
        binding = catalog['sources'][source['source_task_id']]
        require(all(source[k] == binding[k] for k in ('source_task_id', 'active_task_id', 'runtime_task_id',
                'domain', 'native_contract', 'admission', 'profile', 'evaluator_version')), 'Prepared finite Map source differs')
        native = read(source['native_contract']); finite_runtime.validate(native)
        require(native['source_task_id'] == source['source_task_id'] and native['task_id'] == source['runtime_task_id']
                and native['domain'] == source['domain'] == 'map' and binding['protocol'] == 'map_history_layer'
                and not native.get('heldout_quarantine') and native.get('split', 'train') == 'train'
                and source['evaluator_version'] == finite_runtime.VERSION, 'Finite Map identity differs')
        require(contract['public_goal'] == binding['actor_goal'] == finite_runtime.public_goal(native)
                and binding['public_goal'] in (native['goal'], binding['actor_goal']), 'Finite Map public interface differs')
        return binding['public_goal']
    if plan.get('native_source_adapter') == 'registered_map_facts_v1':
        from . import map_native_facts_runtime as facts_runtime
        from .site_query_rules import VERSION as query_version
        catalog = read(plan['source_binding_catalog']); source = plan['sources'][0]
        require(catalog['version'] == 'registered-map-native-facts-sft-bindings-v1'
                and catalog['training_pointer'] == plan['training_pointer'], 'Map facts registration differs')
        binding = catalog['sources'][source['source_task_id']]
        require(all(source[k] == binding[k] for k in ('source_task_id', 'active_task_id', 'runtime_task_id',
                'domain', 'native_contract', 'admission', 'profile', 'evaluator_version')), 'Prepared Map facts source differs')
        native = read(source['native_contract']); facts_runtime.validate(native)
        version = query_version if native['protocol']['kind'] in facts_runtime.facts.DOCS else facts_runtime.facts.VERSION
        require(native['source_task_id'] == source['source_task_id'] and native['task_id'] == source['runtime_task_id']
                and native['domain'] == source['domain'] == 'map' and binding['protocol'] == 'map_native_facts'
                and source['evaluator_version'] == version, 'Native Map facts identity differs')
        require(contract['public_goal'] == binding['actor_goal'] == facts_runtime.public_goal(native)
                and binding['public_goal'] in (native['goal'], binding['actor_goal']), 'Prepared Map facts public interface differs')
        return binding['public_goal']
    if plan.get('native_source_adapter') == 'registered_map_export_v1':
        from .map_export_normal import public_goal, VERSION
        catalog = read(plan['source_binding_catalog']); source = plan['sources'][0]
        require(catalog['version'] == 'registered-map-export-sft-bindings-v1'
                and catalog['training_pointer'] == plan['training_pointer'], 'Map export registration differs')
        binding = catalog['sources'][source['source_task_id']]
        require(all(source[k] == binding[k] for k in ('source_task_id', 'active_task_id', 'runtime_task_id',
                'domain', 'native_contract', 'admission', 'profile', 'evaluator_version')),
                'Prepared Map export source differs')
        native = read(source['native_contract'])
        require(native['source_task_id'] == source['source_task_id'] and native['task_id'] == source['runtime_task_id']
                and native['domain'] == source['domain'] == 'map' and not native.get('heldout_quarantine')
                and binding['protocol'] == 'map_export' and source['evaluator_version'] == VERSION,
                'Native Map export identity differs')
        require(contract['public_goal'] == binding['actor_goal'] == public_goal(native)
                and binding['public_goal'] in (native['goal'], binding['actor_goal']),
                'Prepared Map export public interface differs')
        return binding['public_goal']
    if plan.get('native_source_adapter') == 'registered_shopping_offline_v1':
        from .native_goal_dispatch import public_goal
        from .shopping_offline_training_runtime import VERSION
        catalog = read(plan['source_binding_catalog']); source = plan['sources'][0]
        require(catalog['version'] == 'registered-shopping-offline-sft-bindings-v1'
                and catalog['training_pointer'] == plan['training_pointer'], 'Reading registration catalog differs')
        binding = catalog['sources'][source['source_task_id']]
        require(all(source[k] == binding[k] for k in ('source_task_id', 'active_task_id', 'runtime_task_id',
                'domain', 'native_contract', 'admission', 'profile', 'evaluator_version')),
                'Prepared reading source differs')
        native = read(source['native_contract'])
        require(native['source_task_id'] == source['source_task_id'] and native['task_id'] == source['runtime_task_id']
                and native['domain'] == source['domain'] == 'shopping' and not native.get('heldout_quarantine')
                and binding['protocol'] == 'shopping_offline_training' and source['evaluator_version'] == VERSION,
                'Prepared native reading identity differs')
        require(contract['public_goal'] == binding['actor_goal'] == public_goal(native)
                and binding['public_goal'] == binding['actor_goal'],
                'Prepared reading public interface differs')
        return binding['public_goal']
    if plan.get('native_source_adapter') == 'registered_reddit_native_v1':
        from .reddit_remaining_runtime import public_goal, VERSION
        catalog = read(plan['source_binding_catalog']); source = plan['sources'][0]
        require(catalog['version'] == 'registered-reddit-native-issued-sft-bindings-v1'
                and catalog['training_pointer'] == plan['training_pointer'], 'Reading registration catalog differs')
        binding = catalog['sources'][source['source_task_id']]
        require(all(source[k] == binding[k] for k in ('source_task_id', 'active_task_id', 'runtime_task_id',
                'domain', 'native_contract', 'admission', 'profile', 'evaluator_version')),
                'Prepared reading source differs')
        native = read(source['native_contract'])
        require(native['source_task_id'] == source['source_task_id'] and native['task_id'] == source['runtime_task_id']
                and native['domain'] == source['domain'] == 'reddit' and not native.get('heldout_quarantine')
                and binding['protocol'] == 'reddit_native_task' and source['evaluator_version'] == VERSION,
                'Prepared native reading identity differs')
        require(contract['public_goal'] == binding['actor_goal'] == public_goal(native)
                and binding['public_goal'] in (native['goal'], binding['actor_goal']),
                'Prepared reading public interface differs')
        return binding['public_goal']
    if plan.get('native_source_adapter') == 'registered_gitlab_read_v1':
        from .gitlab_native_read_runtime import public_goal, VERSION
        catalog = read(plan['source_binding_catalog']); source = plan['sources'][0]
        require(catalog['version'] == 'registered-gitlab-native-read-sft-bindings-v1'
                and catalog['training_pointer'] == plan['training_pointer'], 'Reading registration catalog differs')
        binding = catalog['sources'][source['source_task_id']]
        require(all(source[k] == binding[k] for k in ('source_task_id', 'active_task_id', 'runtime_task_id',
                'domain', 'native_contract', 'admission', 'profile', 'evaluator_version')),
                'Prepared reading source differs')
        native = read(source['native_contract'])
        require(native['source_task_id'] == source['source_task_id'] and native['task_id'] == source['runtime_task_id']
                and native['domain'] == source['domain'] == 'gitlab' and not native.get('heldout_quarantine')
                and binding['protocol'] == 'gitlab_native_read' and source['evaluator_version'] == VERSION,
                'Prepared native reading identity differs')
        require(contract['public_goal'] == binding['actor_goal'] == public_goal(native)
                and binding['public_goal'] in (native['goal'], binding['actor_goal']),
                'Prepared reading public interface differs')
        return binding['public_goal']
    if plan.get('native_source_adapter') == 'registered_reading_v1':
        from .reddit_final_read_runtime import public_goal, original, maximum
        catalog = read(plan['source_binding_catalog']); source = plan['sources'][0]
        require(catalog['version'] == 'registered-reddit-reading-sft-bindings-v1'
                and catalog['training_pointer'] == plan['training_pointer'], 'Reading registration catalog differs')
        binding = catalog['sources'][source['source_task_id']]
        require(all(source[k] == binding[k] for k in ('source_task_id', 'active_task_id', 'runtime_task_id',
                'domain', 'native_contract', 'admission', 'profile', 'evaluator_version')),
                'Prepared reading source differs')
        native = read(source['native_contract'])
        require(native['source_task_id'] == source['source_task_id'] and native['task_id'] == source['runtime_task_id']
                and native['domain'] == source['domain'] == 'reddit' and not native.get('heldout_quarantine')
                and binding['protocol'] == 'reddit_final_read' and source['evaluator_version'] == (maximum.VERSION if 'reddit_maximum_query' in native else original.VERSION),
                'Prepared native reading identity differs')
        require(contract['public_goal'] == binding['actor_goal'] == public_goal(native)
                and binding['public_goal'] in (native['goal'], binding['actor_goal']),
                'Prepared reading public interface differs')
        return binding['public_goal']
    if plan.get('native_source_adapter') == 'registered_route_v1':
        from .map_native_route_runtime import public_goal, OPEN_CHOICE_VERSION
        from .map_route_normal_runtime import VERSION
        catalog = read(plan['source_binding_catalog']); source = plan['sources'][0]
        require(catalog['version'] == 'registered-map-route-sft-bindings-v1'
                and catalog['training_pointer'] == plan['training_pointer'], 'Route registration catalog differs')
        binding = catalog['sources'][source['source_task_id']]
        require(all(source[k] == binding[k] for k in ('source_task_id', 'active_task_id', 'runtime_task_id',
                'domain', 'native_contract', 'admission', 'profile', 'evaluator_version')),
                'Prepared route source differs')
        native = read(source['native_contract'])
        require(native['source_task_id'] == source['source_task_id'] and native['task_id'] == source['runtime_task_id']
                and native['domain'] == source['domain'] == 'map' and not native.get('heldout_quarantine')
                and binding['protocol'] == 'map_native_route' and source['evaluator_version'] == (OPEN_CHOICE_VERSION if native['endpoint_request']['kind'] == 'two_actor_chosen_distinct_points' else VERSION),
                'Prepared native route identity differs')
        require(contract['public_goal'] == binding['actor_goal'] == public_goal(native)
                and binding['public_goal'] in (native['goal'], binding['actor_goal']),
                'Prepared route public interface differs')
        return binding['public_goal']
    if plan.get('native_source_adapter') == 'registered_grouped_v1':
        from .gitlab_grouped_goal_runtime import public_goal, VERSION
        catalog = read(plan['source_binding_catalog']); source = plan['sources'][0]
        require(catalog['version'] == 'registered-gitlab-grouped-sft-bindings-v1'
                and catalog['training_pointer'] == plan['training_pointer'], 'Grouped registration catalog differs')
        binding = catalog['sources'][source['source_task_id']]
        require(all(source[k] == binding[k] for k in ('source_task_id', 'active_task_id', 'runtime_task_id',
                'domain', 'native_contract', 'admission', 'profile', 'evaluator_version')),
                'Prepared grouped source differs')
        native = read(source['native_contract'])
        require(native['source_task_id'] == source['source_task_id'] and native['task_id'] == source['runtime_task_id']
                and native['domain'] == source['domain'] == 'gitlab' and not native.get('heldout_quarantine')
                and binding['protocol'] == 'gitlab_grouped_goal' and source['evaluator_version'] == VERSION,
                'Prepared native grouped identity differs')
        require(contract['public_goal'] == binding['actor_goal'] == public_goal(native)
                and binding['public_goal'] in (native['goal'], binding['actor_goal']),
                'Prepared grouped public interface differs')
        return binding['public_goal']
    if plan.get('native_source_adapter') == 'registered_admin_legacy_v1':
        from .admin_pilot import actor_goal, VERSION
        catalog = read(plan['source_binding_catalog']); source = plan['sources'][0]
        require(catalog['version'] == 'registered-admin-legacy-native-sft-bindings-v1'
                and catalog['training_pointer'] == plan['training_pointer'], 'Native Admin catalog differs')
        binding = catalog['sources'][source['source_task_id']]
        require(source['profile'] == 'registered_admin_legacy_v1'
                and all(source[k] == binding[k] for k in ('source_task_id', 'active_task_id',
                    'runtime_task_id', 'domain', 'native_contract', 'admission', 'source_row', 'evaluator_version')),
                'Prepared native Admin source differs')
        native, row = (read(source[k]) for k in ('native_contract', 'source_row'))
        kind = native['spec']['kind']
        require(kind in ('navigation', 'query', 'update', 'comment', 'typed_query')
                and native['source_task_id'] == row['source_task_id'] == source['source_task_id']
                and native.get('runtime_task_id', source['source_task_id']) == row['runtime_task_id'] == source['runtime_task_id']
                and source['domain'] == row['domain'] == 'shopping_admin'
                and source['evaluator_version'] == native['evaluator_version']
                    == ('admin-typed-query-v1' if kind == 'typed_query' else VERSION)
                and native['goal'] == row['goal']
                and contract['public_goal'] == binding['actor_goal'] == actor_goal(native)
                and binding['public_goal'] in (native['goal'], binding['actor_goal']),
                'Prepared native Admin public interface or identity differs')
        return binding['public_goal']
    if plan.get('native_source_adapter') == 'registered_admin_declarative_v1':
        from .admin_contract_rules import goal
        catalog = read(plan['source_binding_catalog']); source = plan['sources'][0]
        require(catalog['version'] == 'registered-admin-declarative-sft-bindings-v2'
                and catalog['training_pointer'] == plan['training_pointer'], 'Declarative catalog differs')
        binding = catalog['sources'][source['source_task_id']]
        require(source['profile'] == 'registered_admin_declarative_v1'
                and all(source[k] == binding[k] for k in ('source_task_id', 'active_task_id',
                    'runtime_task_id', 'domain', 'native_contract', 'admission', 'source_row', 'evaluator_version')),
                'Prepared declarative source differs')
        native, row = (read(source[k]) for k in ('native_contract', 'source_row'))
        require(native['source_task_id'] == row['source_task_id'] == source['source_task_id']
                and native.get('runtime_task_id', source['source_task_id'])
                    == row['runtime_task_id'] == source['runtime_task_id']
                and native['spec']['kind'] == 'admin_contract'
                and source['domain'] == row['domain'] == 'shopping_admin'
                and native['goal'] == row['goal']
                and contract['public_goal'] == binding['actor_goal'] == goal(native)
                and binding['public_goal'] in (native['goal'], binding['actor_goal']),
                'Prepared declarative public interface or source identity differs')
        return binding['public_goal']
    if plan.get('native_source_adapter') != 'registered_query_v1':
        return contract['public_goal']
    from .site_query_rules import query_goal
    catalog = read(plan['source_binding_catalog']); source = plan['sources'][0]
    require(catalog['version'] == 'registered-ordinary-query-sft-bindings-v1'
            and catalog['training_pointer'] == plan['training_pointer'], 'Query registration catalog differs')
    binding = catalog['sources'][source['source_task_id']]
    require(all(source[k] == binding[k] for k in ('source_task_id', 'active_task_id', 'runtime_task_id',
            'domain', 'native_contract', 'admission', 'profile', 'evaluator_version')), 'Prepared query source differs')
    native = read(source['native_contract'])
    require(native['source_task_id'] == source['source_task_id'] and native['task_id'] == source['runtime_task_id']
            and native['domain'] == source['domain'] and not native.get('heldout_quarantine')
            and binding['protocol'] == 'query', 'Prepared native query identity differs')
    actor_goal = query_goal(native)
    require(contract['public_goal'] == binding['actor_goal'] == actor_goal
            and binding['public_goal'] in (native['goal'], actor_goal), 'Prepared public query interface differs')
    return binding['public_goal']


def scan(pointer_ref, coverage_ref, builds, claim_root, output_root):
    """Read the entire training manifest once; old outcome labels grant no target."""
    pointer = read(pointer_ref)
    table = dict(path=pointer['tasks'], sha256=pointer['tasks_sha256'])
    require(pin(table['path']) == table, 'Training registration changed')
    with Path(table['path']).open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    require(len({r['source_task_id'] for r in rows}) == len(rows), 'Duplicate training source')
    coverage_review = read(coverage_ref)
    require(coverage_review.get('passed') is True, 'Existing coverage review missing')
    cref = coverage_review['output_pins']['coverage.jsonl']
    require(pin(cref['path']) == cref, 'Coverage inventory changed')
    coverage = {r['source_task_id']: r for r in
                map(json.loads, Path(cref['path']).read_text().splitlines())}
    require(set(coverage) == {r['source_task_id'] for r in rows}, 'Coverage and registry differ')
    candidates = {}
    for build_ref in builds:
        build = read(build_ref)
        require(build.get('passed') is True, 'Source preparation is incomplete')
        for item in build['sources']:
            sid = item['source_task_id']
            require(sid not in candidates, 'Ambiguous prepared source')
            candidates[sid] = dict(item, build=build_ref)
    require(set(candidates) <= set(coverage), 'Prepared source is outside training register')
    result = []
    for row in sorted(rows, key=lambda r: r['source_task_id']):
        sid = row['source_task_id']; old = coverage[sid]
        require(row['split'] == 'train' and row['status'] in ('success', 'failure'),
                'Only registered training sources may enter the queue')
        require(all(row[k] == old[k] for k in
                    ('source_task_id', 'active_task_id', 'runtime_task_id', 'domain', 'split', 'status'))
                and row['current_goal'] == old['current_goal'], 'Training identity or literal goal changed')
        item = dict(source_task_id=sid, active_task_id=row['active_task_id'],
                    runtime_task_id=row['runtime_task_id'], domain=row['domain'],
                    registration_status=row['status'], compatibility_group=old['compatibility_group'],
                    existing_sft_coverage=old['sft_coverage'], ready=False, missing=[])
        prepared = candidates.get(sid)
        if prepared:
            item['prepared'] = prepared
            if prepared.get('passed') is not True:
                item['missing'].append(prepared.get('reason', 'source_preparation_incomplete'))
            else:
                plan = read(prepared['source_plan_draft'])
                source = plan['sources'][0]
                require(len(plan['sources']) == 1 and all(source[k] == row[k] for k in
                        ('source_task_id', 'active_task_id', 'runtime_task_id', 'domain')),
                        'Prepared source binding differs')
                contract = read(plan['local_contract'])
                require(prepared_registered_goal(plan, contract) == row['current_goal'], 'Prepared goal differs')
                require(plan['training_pointer'] == pointer_ref and plan['construction_only'] is True,
                        'Expected an unreleased plan bound to this registry')
                item['runtime'] = plan['capsule']
        else:
            if old['sft_coverage'] == 'sft_protocol_adapter_not_implemented':
                item['missing'].append('sft_protocol_adapter')
            elif old['sft_coverage'] == 'shared_implementation_requires_source_binding':
                item['missing'].append('source_binding')
            item['missing'].append('qualified_formal_plan')
            item['existing_native_admission'] = old['native_admission']
        if (Path(claim_root) / sid).exists():
            item['missing'].append('existing_formal_claim_requires_recovery_or_audit')
        if (Path(output_root) / sid).exists():
            item['missing'].append('existing_output_requires_reconciliation')
        item['ready'] = not item['missing']
        result.append(item)
    return dict(version='formal-training-queue-v1', training_pointer=pointer_ref,
                coverage_review=coverage_ref, builds=builds, sources=result,
                ready_source_ids=[r['source_task_id'] for r in result if r['ready']],
                total_sources=len(result), code_tests_repeated=0, website_controls_repeated=0,
                model_calls=0, formal_targets=0, authorization_created=False)


class QueueState:
    """One durable controller; a crash during submission is never a new attempt."""
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def locked(self):
        with (self.directory / 'queue.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            path = self.directory / 'state.json'
            state = json.loads(path.read_text()) if path.exists() else None
            yield state

    def save(self, state):
        temp = self.directory / 'state.json.tmp'
        with temp.open('w') as stream:
            json.dump(state, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, self.directory / 'state.json')
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)


def initial_state(queue_ref, authorization_ref):
    queue, auth = read(queue_ref), read(authorization_ref)
    require(auth['queue'] == queue_ref and auth['basis'] == 'explicit_user_cli_submit'
            and auth['user_api_authorized'] is True
            and auth['source_task_ids'] == queue['ready_source_ids'], 'Batch authorization differs')
    require(money(auth['teacher_cost_stop_usd']) > 0 and
            0 < money(auth['source_budget_usd']) <= auth['teacher_cost_stop_usd'], 'Invalid source reservation')
    require(type(auth['max_concurrent_sources']) is int and auth['max_concurrent_sources'] >= 1,
            'Positive isolated-source concurrency required')
    return dict(version='formal-training-queue-state-v1', queue=queue_ref,
                authorization=authorization_ref, sources={}, pilot_passed=False,
                stopped_reason=None, reserved_or_spent_usd=0.)


def reserve_next(state, *, source_ids=None):
    queue, auth = read(state['queue']), read(state['authorization'])
    if state['stopped_reason']:
        return None
    active = [r for r in state['sources'].values() if r['status'] in ('submitting', 'submitted')]
    limit = auth['max_concurrent_sources'] if state['pilot_passed'] else 1
    if len(active) >= limit or (not state['pilot_passed'] and state['sources']):
        return None
    amount = money(auth['source_budget_usd'])
    committed = sum(money(r['charged_or_reserved_usd']) for r in state['sources'].values())
    state['reserved_or_spent_usd'] = committed
    if committed + amount > auth['teacher_cost_stop_usd']:
        return None
    sid = next((sid for sid in queue['ready_source_ids'] if sid not in state['sources']
                and (source_ids is None or sid in source_ids)), None)
    if sid is None:
        return None
    state['sources'][sid] = dict(status='submitting', allowance_usd=amount,
        charged_or_reserved_usd=amount, automatic_retry=False)
    state['reserved_or_spent_usd'] = committed + amount
    return next(r for r in queue['sources'] if r['source_task_id'] == sid)


def settle(state, sid, *, export_summary):
    row = state['sources'][sid]
    require(row['status'] == 'submitted', 'Only an owned submitted source can settle')
    summary = read(export_summary)
    require(summary.get('complete') is True and summary.get('training_data') is True,
            'Independent single-source export required')
    audits = read(summary['audit'])
    require(len(audits) == 1 and audits[0].get('passed') is True
            and audits[0]['source_task_id'] == sid
            and audits[0]['source_plan'] == row['release']['source_plan'], 'Completed audit belongs to another source')
    audit = audits[0]
    cost = money(audit['teacher_reported_cost_usd'])
    actual_teacher_calls = len(audit['teacher_requests'])
    row.update(status='complete', charged_or_reserved_usd=cost,
               reported_cost_usd=cost, export_summary=export_summary)
    if cost > row['allowance_usd']:
        state['stopped_reason'] = 'reported_cost_exceeded_reserved_estimate'
    # A successfully audited all-failed method is a complete pilot with zero targets.
    if not state['pilot_passed']:
        if actual_teacher_calls < 1:
            state['stopped_reason'] = 'pilot_has_no_audited_real_teacher_call'
        else:
            state['pilot_passed'] = True
    state['reserved_or_spent_usd'] = sum(r['charged_or_reserved_usd'] for r in state['sources'].values())


def tick(store, template_ref, key_file, submit, job_states):
    """Reconcile known jobs and refill free slots. No source/test is rerun.

    The caller polls Slurm no more often than once per minute. An incomplete
    submission receipt stays reserved; only committed job IDs may be resumed.
    """
    terminal = {'COMPLETED', 'FAILED', 'CANCELLED', 'TIMEOUT', 'OUT_OF_MEMORY',
                'NODE_FAIL', 'PREEMPTED', 'BOOT_FAIL', 'DEADLINE'}
    with store.locked() as state:
        require(state is not None, 'Batch has not been authorized')
        for sid, row in state['sources'].items():
            if row['status'] == 'submitting' and row.get('release'):
                release = row['release']; path = Path(release['submission_path'])
                if path.is_file():
                    receipt_ref = pin(path); receipt = read(receipt_ref)
                    workflow = read(release['workflow'])
                    if receipt.get('complete') is True:
                        require(receipt['plan'] == release['workflow']['path']
                                and receipt['plan_sha256'] == release['workflow']['sha256']
                                and set(receipt['stages']) == {s['id'] for s in workflow['stages']}
                                and all(r.get('status') == 'submitted' and str(r.get('job_id', '')).isdecimal()
                                        for r in receipt['stages'].values()), 'Original submission receipt differs')
                        row.update(status='submitted', submission=receipt_ref)
                        store.save(state)
            if row['status'] != 'submitted':
                continue
            receipt = read(row['submission'])
            relevant = row['release'].get('relevant_stage_ids', list(receipt['stages']))
            require(bool(relevant) and set(relevant) <= set(receipt['stages']), 'Source stages missing')
            jobs = [receipt['stages'][name]['job_id'] for name in relevant]
            if not all(job_states.get(job) in terminal for job in jobs):
                continue
            summary = store.directory / 'sources' / sid / 'export/summary.json'
            if summary.exists() and all(job_states[job] == 'COMPLETED' for job in jobs):
                settle(state, sid, export_summary=pin(summary))
            else:
                retain_unknown(state, sid, 'source_or_independent_export_incomplete')
            store.save(state)
        while True:
            item = reserve_next(state)
            if item is None:
                store.save(state)
                return state
            sid = item['source_task_id']; row = state['sources'][sid]
            store.save(state)  # Reserve before creating files or calling sbatch.
            items = [item]
            try:
                # Eligibility is opt-in on the qualified runtime and template.
                # Every member still consumes the original source slot/budget.
                if state['pilot_passed'] and read(template_ref).get('map_batch'):
                    from .formal_map_batch_release import compatible_remaining, prepare_map_release
                    candidates = compatible_remaining(state, item)
                    while candidates and len(items) < 4:
                        extra = reserve_next(state, source_ids=candidates)
                        if extra is None:
                            break
                        items.append(extra); candidates.remove(extra['source_task_id'])
                        store.save(state)
                if len(items) > 1:
                    releases = prepare_map_release(items, store.directory, state, key_file, template_ref)
                    for source_id, released in releases.items():
                        state['sources'][source_id]['release'] = released
                    release = releases[sid]
                else:
                    release = prepare_release(item, store.directory / 'sources' / sid,
                        row['allowance_usd'], state['authorization'], key_file, template_ref)
                    row['release'] = release
                store.save(state)
                receipt = submit(Path(release['workflow']['path']), Path(release['submission_path']))
                require(receipt.get('complete') is True, 'Submission receipt is incomplete')
                for selected in items:
                    state['sources'][selected['source_task_id']].update(
                        status='submitted', submission=pin(release['submission_path']))
                store.save(state)
            except BaseException:
                # sbatch may have accepted a job even if the client lost its reply.
                # Keep the pre-submission reservation and never submit again here.
                for selected in items:
                    state['sources'][selected['source_task_id']]['submission_uncertain'] = True
                store.save(state)
                raise


def aggregate(state):
    """Publish an evidence-bound accumulation index, never relabel it train/dev."""
    outputs = []
    for sid, row in state['sources'].items():
        if row['status'] != 'complete':
            continue
        summary = read(row['export_summary'])
        read(summary['audit'])
        require(pin(summary['candidates']['path']) == summary['candidates'], 'Candidate export changed')
        outputs.append(dict(source_task_id=sid, summary=row['export_summary'],
                            targets=summary['formal_training_targets'], candidates=summary['candidates']))
    return dict(version='formal-batch-accumulation-v1', sources=outputs,
                formal_training_targets=sum(x['targets'] for x in outputs),
                train_dev_release=False, parameter_training_complete=False,
                reserved_or_spent_usd=state['reserved_or_spent_usd'])


def submit_accumulation(store, template_ref, submit):
    """One offline grouped export per immutable set of completed source exports."""
    with store.locked() as state:
        index = aggregate(state)
        if not index['sources']:
            return None
        signature = hashlib.sha256(json.dumps(index['sources'], sort_keys=True).encode()).hexdigest()
        directory = store.directory / 'exports' / signature
        if directory.exists():
            # The existing submitter owns any committed/ambiguous scheduler reply.
            return submit(directory / 'workflow.json', directory / 'submission.json')
        template = read(template_ref)['aggregate_export']
        directory.mkdir(parents=True)
        index_ref = write_new(directory / 'input.json', index)
        spec = dict(template, input=index_ref, output_directory=str(directory / 'data'))
        spec_ref = write_new(directory / 'binding.json', spec)
        stage = dict(id='aggregate_export', execution='gpu', script=template['script'],
            args=[template['program']['path'], template['program']['sha256'], spec_ref['path'], spec_ref['sha256']],
            inputs=[spec_ref, template_ref, template['program'], *template['inputs']],
            resources=dict(partition='a40', gres='gpu:a40:1', cpus=16, time='00:30:00', exclude='a1621'),
            state_isolation='single_instance', exclusive_scopes=[str(directory / 'data')],
            output=str(directory / 'export-%j.log'))
        write_new(directory / 'workflow.json', dict(version='stage-submission-v2', stages=[stage]))
        return submit(directory / 'workflow.json', directory / 'submission.json')


def retain_unknown(state, sid, reason):
    row = state['sources'][sid]
    row.update(status='unknown', reason=reason)
    if not state['pilot_passed']:
        state['stopped_reason'] = 'first_formal_acceptance_incomplete'


def prepare_release(item, destination, allowance, batch_authorization_ref, key_file, template_ref,
                    *, shared_workflow=None):
    """Parameterize the already-tested source/export workflow; create no claim."""
    template = read(template_ref)
    plan = read(item['prepared']['source_plan_draft'])
    sid = item['source_task_id']; destination = Path(destination)
    auth = read(batch_authorization_ref)
    require(auth['basis'] == 'explicit_user_cli_submit' and auth['user_api_authorized'] is True
            and sid in auth['source_task_ids'] and allowance == auth['source_budget_usd'],
            'Source is not covered by the batch invocation')
    require(not (Path(template['claim_root']) / sid).exists(), 'Formal source already claimed')
    destination.mkdir(exist_ok=False)
    plan.update(construction_only=False, formal_source_execution_ready=True,
                result_directory=str(destination / 'execution/source'))
    pref = write_new(destination / 'source-plan.json', plan)
    fingerprint = lambda v: hashlib.sha256(json.dumps(v, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    aref = write_new(destination / 'authorization.json', dict(
        version='native-stage1-training-authorization-v1', source_plan=pref,
        user_api_authorized=True, local_pilot_reported=True, source_task_ids=[sid],
        teacher_settings_sha256=fingerprint(plan['teacher_settings']), teacher_cost_stop_usd=allowance,
        local_pilot_review=template['local_pilot_review'], batch_authorization=batch_authorization_ref,
        basis='allocation_from_explicit_batch_authorization'))
    launch = deepcopy(template['launch'])
    launch.update(source_plan=pref, authorization=aref, runtime_build=item['prepared']['build'],
        credential_file=str(key_file), workflow_path=str(destination / 'workflow.json'),
        submission_path=str(destination / 'submission.json'))
    if shared_workflow is not None:
        launch.update(workflow_path=shared_workflow['workflow_path'],
                      submission_path=shared_workflow['submission_path'], stage_id='map_batch')
    # Rebind callback source files to immutable copies in the frozen build.
    launch['review_binding']['helpers']['require_claim'] = item['prepared']['claim_helper']
    inputs = [pref, aref, template_ref, item['prepared']['build'], batch_authorization_ref,
              launch['bootstrap_source'], launch['dispatch_source'],
              *launch['helpers'].values(), *launch['helper_dependencies'].values(),
              *launch['review_binding']['helpers'].values(),
              *launch['review_binding']['helper_dependencies'].values()]
    launch['inputs'] = list({r['path']: r for r in inputs}.values())
    lref = write_new(destination / 'launch.json', launch)
    eref = write_new(destination / 'export-plan.json', dict(source_plan=pref, launch=lref,
        dispatch_source=launch['dispatch_source'], execution_path=str(destination / 'execution/completed-execution.json'),
        output_directory=str(destination / 'export')))
    workflow = deepcopy(template['workflow'])
    for stage, mode, ref, label in zip(workflow['stages'], ('execute', 'export'), (lref, eref), ('source', 'export')):
        stage['args'] = [mode, ref['path'], ref['sha256'], launch['bootstrap_source']['sha256'], launch['dispatch_source']['sha256']]
        stage['inputs'] = [ref, lref] + launch['inputs']
        stage['output'] = str(destination / (label + '-%j.log'))
        stage['exclusive_scopes'] = [str(destination / ('execution' if mode == 'execute' else 'export'))]
        if mode == 'execute': stage['exclusive_scopes'].append(str(Path(template['claim_root']) / sid))
    if shared_workflow is not None:
        workflow['stages'][0]['id'] = 'map_batch'
        workflow['stages'][1].update(id='export_'+sid, after=[dict(stage='map_batch', condition='afterany')])
        return dict(source_plan=pref, authorization=aref, launch=lref, stages=workflow['stages'])
    wref = write_new(destination / 'workflow.json', workflow)
    return dict(source_plan=pref, authorization=aref, launch=lref, workflow=wref,
                submission_path=str(destination / 'submission.json'))
