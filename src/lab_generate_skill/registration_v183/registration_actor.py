"""Bind the reviewed registration-only endpoint to the unchanged ordinary runner."""
from contextlib import contextmanager
from copy import deepcopy
from io import BytesIO
from pathlib import Path, PurePosixPath
import hashlib
import json
import tarfile

from lab_generate_skill.frozen_signup_document_adapter import FrozenSignupDocumentAdapter
from lab_generate_skill.reviewed_protocol_bundle import ReviewedProtocolBundle
from lab_generate_skill import native_goal_dispatch
from lab_generate_skill.source_revision_binding import fingerprint
from lab_generate_skill.provider_review_catalog import identity
from .registration_hooks import RegistrationHooks

SOURCE = '01ccdfd9a75d86f713e4'
ADMISSION = 'native-registration-confirm-admission-v183'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def checked_sft_shared_update(update, *, project, original_capsule_ref, read):
    names={'src/lab_generate_skill/'+n+'.py' for n in ('stage1_services','stage1','sft_train','gobrowse_runtime')}
    names |= {'scripts/map_surfaces/'+n+'.py' for n in ('repaired_input_phase','control_cycle','catalog')}
    names |= {'scripts/map_route_location/'+n+'.py' for n in ('control_cycle','catalog')}
    require(update.get('version')=='registration-sft-shared-runtime-v1' and update.get('source_task_id')==SOURCE
        and update.get('original_runtime_capsule')==original_capsule_ref and set(update.get('changes',{}))==names,
        'Exact registration runtime and nine qualified shared members required')
    previous=read(original_capsule_ref);qualified=read(update['qualified_runtime'])
    controls=read(update['qualification']);memory=read(update['optional_memory_delta'])
    require(controls.get('passed') is True and controls.get('capsule')==update['qualified_runtime']
        and controls.get('method_checks')==3, 'Qualified existing SFT method runtime required')
    require(memory.get('passed') is True and memory.get('remaining_ast_identical') is True
        and memory.get('required_actor_memory_policy') is None and memory.get('native_predicates_changed') is False,
        'Unchanged default Actor behavior required')
    for name,change in update['changes'].items():
        require(set(change)=={'original','qualified'} and previous['members'][name]['sha256']==change['original']
            and qualified['members'][name]['sha256']==change['qualified'], 'Shared runtime provenance differs')
        read(dict(path=str(Path(project)/name),sha256=change['qualified']),json_value=False)
    change=update['changes']['src/lab_generate_skill/gobrowse_runtime.py']
    require(memory['original']['sha256']==change['original'] and memory['qualified']['sha256']==change['qualified'],
        'Optional Actor memory delta differs')
    return deepcopy(update['changes'])


class RegistrationCatalog:
    def __init__(self, config, *, project):
        require(config.get("version") == "registration-current-entry-v183", "Exact current registration entry required")
        self.entry_config = deepcopy(config)
        authority = config["authority"]
        self.files = {}
        self.closed = False
        self.config = self.read(authority)
        cfg = self.config
        require(cfg['version'] == 'registration-first-actor-authority-v183', 'Explicit registration authority required')
        self.authority = deepcopy(authority)
        for ref in cfg['dependencies']:
            self.read(ref, json_value=False)
        contracts = self.read(cfg['contracts'])
        require(len(contracts['tasks']) == 1, 'One exact registration source required')
        self.candidate = contracts['tasks'][0]
        c = self.candidate
        require(c['source_task_id'] == SOURCE and c['candidate_completion']['completion_semantics'] == 'register_confirm_account_v1', 'Wrong completion scope')
        require(c['candidate_completion']['requires_native_session_identity'] is False, 'Session persistence is outside this scope')
        review = self.read(cfg['native_review'])
        require(review['version'] == 'registration-native-independent-reader-v183-r2'
                and review['source_task_id'] == SOURCE and review['passed'] is True
                and review['actor_calls'] == review['model_inference_calls'] == review['training_admissions'] == 0,
                'Current source native and input review required')
        require(all(review[k] is True for k in ['full_protection_and_cold_reset_verified', 'original_start_verified',
                    'ordinary_public_input_qualified', 'logout_still_success', 'active_session_then_healthy_cold_rejection']),
                'Required native/reset/public input evidence absent')
        require(review['unconfirmed_status'] == 'failure' and review['ordinary_public_input_replay']['passed'] is True
                and review['retained_negative_controls']['passed'] is True, 'Incomplete control coverage')
        require(review['plan'] == cfg['native_plan'] and review['full_native_baseline'] == contracts['baseline'], 'Native source baseline differs')
        plan = self.read(cfg['native_plan'])
        require(plan['runtime_capsule'] == cfg['runtime_capsule'], 'Control/runtime binding differs')
        pins = {r['path']: r['sha256'] for r in plan['candidate_files']}
        require(pins.get(cfg['contracts']['path']) == cfg['contracts']['sha256'], 'Controls used a different contract')
        for ref in cfg['tested_modules']:
            require(pins.get(ref['path']) == ref['sha256'], 'Registration module was not tested')
            self.read(ref, json_value=False)
        from . import registration_hooks, registration_terminal
        for mod, ref in zip([registration_hooks, registration_terminal], cfg['tested_modules']):
            actual = Path(mod.__file__).resolve()
            require(actual.parent == Path(__file__).resolve().parent and actual.name == Path(ref['path']).name, 'Registration module shadowed')
            payload = actual.read_bytes().replace(b'from .registration_terminal import', b'from registration_terminal import')
            require(hashlib.sha256(payload).hexdigest() == ref['sha256'], 'Native registration implementation changed')
            self.read(dict(path=str(actual), sha256=hashlib.sha256(actual.read_bytes()).hexdigest()), json_value=False)
        self.archive(review['archive'], review['archive_index'])
        negative = review['retained_negative_controls']
        self.archive(negative['archive'], negative['archive_index'])
        capsule = self.read(cfg['runtime_capsule'])
        sft_updates = {}
        if config.get('reviewed_sft_shared_update') is not None:
            sft_updates = checked_sft_shared_update(self.read(config['reviewed_sft_shared_update']),
                project=project, original_capsule_ref=cfg['runtime_capsule'], read=self.read)
        legacy_dependency_read = self.read
        if config.get('reviewed_final_map_update') is not None:
            final_update = self.read(config['reviewed_final_map_update'])
            helper = final_update['helper']
            require(helper['relative'] == 'src/lab_generate_skill/map_final_v191/registration_compat.py',
                    'Exact final Map compatibility helper required')
            self.read(dict(path=str(Path(project)/helper['relative']),sha256=helper['sha256']),json_value=False)
            from ..map_final_v191.registration_compat import require_update as require_final_update
            legacy_dependency_read = require_final_update(final_update,source=SOURCE,project=project,read=self.read)
        scope_updates = {}
        if config.get('reviewed_native_scope_update') is not None:
            update = self.read(config['reviewed_native_scope_update'])
            helper = update['helper']
            require(helper['relative'] == 'src/lab_generate_skill/map_scope_v190/registration_compat.py',
                    'Exact registration scope compatibility helper required')
            self.read(dict(path=str(Path(project)/helper['relative']), sha256=helper['sha256']), json_value=False)
            from ..map_scope_v190.registration_compat import require_update, previous_registry
            scope_updates = require_update(update, source=SOURCE, project=project, read=legacy_dependency_read)
        extension = config.get('runtime_metadata_changes', {})
        require(set(extension) <= {'src/lab_generate_skill/reviewed_map_registry.py', 'configs/task-dataset-current.json', 'configs/data-active-scope.json'}, 'Only reviewed registry addition and dataset metadata may differ')
        reviewed_updates = {}
        if config.get('reviewed_public_interface_update') is not None:
            update = self.read(config['reviewed_public_interface_update'])
            require(update.get('version') == 'registration-compatible-public-interface-v184'
                    and update.get('passed') is True and update.get('source_task_id') == SOURCE
                    and update.get('original_runtime_capsule') == cfg['runtime_capsule'],
                    'Exact source/runtime interface review required')
            require(set(update.get('changes', {})) == {'src/lab_generate_skill/ax_observation.py',
                    'scripts/run_registered_admin_batch.py', 'scripts/run_archived_admin_actor.py'},
                    'Only reviewed native option display and unrelated Admin dispatch may differ')
            for name, change in update['changes'].items():
                require(change['old_sha256'] == capsule['members'][name]['sha256'], 'Original runtime hash differs')
                reviewed_updates[name] = change['current_sha256']
            compatibility = self.read(update['dispatch_review'])
            require(compatibility.get('old_source_dispatch_ast_unchanged') is True,
                    'Prior Admin dispatch must remain identical outside the new source branch')
            observation = self.read(update['registration_observation_review'])
            require(observation.get('passed') is True and observation.get('all_actual_frames_have_no_blank_option') is True
                    and observation.get('source_task_id') == SOURCE, 'Registration observation compatibility missing')
            generic = self.read(update['generic_option_review'])
            require(generic.get('passed') is True and generic.get('passed_tests') == 57
                    and generic.get('candidate', {}).get('sha256') == reviewed_updates['src/lab_generate_skill/ax_observation.py'],
                    'Tested generic native option repair required')
        if config.get('reviewed_lossless_interface_update') is not None:
            update = self.read(config['reviewed_lossless_interface_update'])
            require(update.get('version') == 'registration-lossless-interface-v185-candidate'
                    and update.get('passed') is True and update.get('source_task_id') == SOURCE
                    and update.get('original_runtime_capsule') == cfg['runtime_capsule'], 'Exact lossless interface source/runtime review required')
            names = {'src/lab_generate_skill/'+name+'.py' for name in ('adaptive_observation','actor_protocol','public_read_memory','runtime_profile')}
            require(set(update.get('changes', {})) == names, 'Only the four reviewed shared observation modules may differ')
            for name, change in update['changes'].items():
                require(change['old_sha256'] == capsule['members'][name]['sha256'], 'Original shared interface hash differs')
                reviewed_updates[name] = change['current_sha256']
            helper = update['helper']
            require(helper['relative'] == 'src/lab_generate_skill/lossless_ax_rows.py', 'Unexpected shared helper')
            self.read(dict(path=str(Path(project)/helper['relative']),sha256=helper['sha256']),json_value=False)
            evidence = self.read(update['registration_observation_review'])
            require(evidence.get('passed') is True and evidence.get('source_task_id') == SOURCE
                    and evidence.get('all_actual_frames_unchanged_by_compaction') is True, 'Retained registration observations differ')
            regression = self.read(update['shared_regression'])
            require(regression.get('passed') is True and regression.get('changed_files') == update['changes_current'], 'Shared regression identity differs')
        if config.get('reviewed_public_intake_update') is not None:
            update = self.read(config['reviewed_public_intake_update'])
            require(update.get('passed') is True and update.get('source_task_id') == SOURCE, 'Exact source intake evolution required')
            require(set(update['changes']) == {'src/lab_generate_skill/admin_catalog_current.py', 'scripts/native_gitlab/retained_topics/retained_topic_registry_v154.py'}, 'Only two unrelated intake gates may differ')
            for name, change in update['changes'].items():
                require(change['old_sha256'] == capsule['members'][name]['sha256'], 'Original unrelated intake identity differs')
                reviewed_updates[name] = change['current_sha256']
            self.read(update['review'])
        registry_additions = ()
        if config.get('reviewed_saved_reader_update') is not None:
            update = self.read(config['reviewed_saved_reader_update'])
            names = {'scripts/run_site_navigation_once.py'} | {'src/lab_generate_skill/' + n + '.py'
                for n in ('site_worker', 'website_batch_profile', 'native_goal_dispatch',
                          'reviewed_protocol_bundle', 'reviewed_map_registry')}
            require(update.get('version') == 'registration-saved-reader-interface-v188'
                    and update.get('source_task_id') == SOURCE and update.get('passed') is True
                    and update.get('original_runtime_capsule') == cfg['runtime_capsule'],
                    'Exact registration saved/reader compatibility required')
            delta = self.read(update['dispatch_review'])
            require(delta.get('passed') is True and delta.get('old_source_dispatch_ast_unchanged') is True
                    and set(delta['changes']) == names and update['changes'] == delta['changes'],
                    'Exact additive dispatch projection required')
            for name, change in update['changes'].items():
                require(change.get('old_branches_ast_equal') is True, 'Old branches must be preserved')
                if name != 'src/lab_generate_skill/reviewed_map_registry.py':
                    require(change['old_sha256'] == capsule['members'][name]['sha256'],
                            'Registration shared dependency baseline differs')
                reviewed_updates[name] = change['current_sha256']
            metadata = update.get('metadata_updates', {})
            require(not metadata or set(metadata) == {'scripts/map_route_location/offline-review.json',
                    'scripts/map_surfaces/offline-review.json'}, 'Only the two reviewed Map dependency inventories may differ')
            for name, change in metadata.items():
                require(change['old_sha256'] == capsule['members'][name]['sha256'],
                        'Original dependency inventory differs')
                evidence = self.read(change['review'])
                require(evidence.get('passed') is True and evidence.get('original_native_evidence_modified') is False
                        and evidence['previous']['sha256'] == change['old_sha256']
                        and evidence['current']['sha256'] == change['current_sha256']
                        and evidence['shared_delta'] == update['dispatch_review'],
                        'Exact dependency inventory compatibility required')
                require(bool(evidence['changes']), 'Dependency inventory change must be explained')
                for relative, pair in evidence['changes'].items():
                    require(relative in delta['changes'] and pair == {k: delta['changes'][relative][k]
                            for k in ('old_sha256', 'current_sha256')}, 'Dependency inventory exceeds reviewed shared delta')
                reviewed_updates[name] = change['current_sha256']
            registry_additions = (
                b"    'reader_diaries_v187': ('map_reader_v187.catalog', 'ReaderCatalog', 'map_reader_v187.adapter', 'ReaderAdapter'),\n",
                b"    'saved_content_v187': ('map_saved_content_v187.catalog', 'SaveCatalog', 'map_saved_content_v187.adapter', 'SaveAdapter'),\n")
        if config.get('reviewed_offered_route_registry_update') is not None:
            update = self.read(config['reviewed_offered_route_registry_update'])
            relative = 'src/lab_generate_skill/reviewed_map_registry.py'
            added = b"    'website_offered_routes_v189': ('map_offered_route_v189.catalog', 'OfferedRouteCatalog', 'map_offered_route_v189.adapter', 'AdmittedScopeRouteAdapter'),\n"
            require(update.get('version') == 'registration-offered-route-registry-v189'
                    and update.get('source_task_id') == SOURCE and update.get('passed') is True
                    and update['previous_registry_sha256'] == reviewed_updates.get(relative),
                    'Exact prior registration registry identity required')
            actual_digest = scope_updates.get(relative, {}).get('current_sha256', update['current_registry_sha256'])
            raw = legacy_dependency_read(dict(path=str(Path(project)/relative), sha256=actual_digest), json_value=False)
            if scope_updates:
                raw = previous_registry(raw)
                require(hashlib.sha256(raw).hexdigest() == update['current_registry_sha256'],
                        'Previous offered-route registry identity must remain exact')
            require(raw.count(added) == 1 and hashlib.sha256(raw.replace(added, b'')).hexdigest() == update['previous_registry_sha256'],
                    'Only the declared unrelated offered-route family may differ')
            reviewed_updates[relative] = update['current_registry_sha256']
            registry_additions += (added,)
        family_line = b"    'registration_confirm_v183': ('registration_v183.registration_actor', 'RegistrationCatalog', 'registration_v183.registration_actor', 'RegistrationAdapter'),\n"
        for name, ref in capsule['members'].items():
            # The outer frozen capsule pins this recursive publication pointer.
            if name == 'configs/site-runtime-current.json': continue
            path = Path(project)/name
            wanted = reviewed_updates.get(name, extension.get(name, ref['sha256']))
            if name in scope_updates:
                change = scope_updates[name]
                require(wanted == change['previous_sha256'], 'Scope update must extend the exact prior dependency')
                wanted = change['current_sha256']
            if name in sft_updates:
                require(wanted == sft_updates[name]['original'], 'SFT runtime must extend exact prior dependency')
                wanted = sft_updates[name]['qualified']
            data = legacy_dependency_read({'path': str(path), 'sha256': wanted}, json_value=False)
            if name == 'src/lab_generate_skill/reviewed_map_registry.py' and scope_updates:
                data = previous_registry(data)
            if name == 'src/lab_generate_skill/reviewed_map_registry.py':
                for added_line in registry_additions:
                    require(data.count(added_line) == 1, 'Exact unrelated family addition required')
                    data = data.replace(added_line, b'')
                require(data.count(family_line) == 1 and hashlib.sha256(data.replace(family_line,b'')).hexdigest() == ref['sha256'], 'Existing registry dispatch must remain byte-identical')
        actor_review = self.read(config['actual_actor_review'])
        require(actor_review.get('passed') is True and actor_review.get('source_task_id') == SOURCE and actor_review.get('actor_attempts') == 1
                and actor_review.get('source_contract') == c and actor_review.get('evaluation_status') in ('success','failure'), 'Independent actual registration Actor required for current entry')
        actor_plan = self.read(actor_review['plan'])
        require(actor_plan['authority'] == authority and actor_plan['capsule'] == cfg['runtime_capsule'], 'Actual Actor used another source/runtime')
        self.baseline = contracts['baseline']
        self.descriptor = dict(version=ADMISSION, source_task_id=SOURCE, authority=authority,
                               contract_sha256=fingerprint(c), native_review=cfg['native_review'])
        self.admission = dict(version=ADMISSION, source_task_id=SOURCE, passed=True,
            baseline=self.baseline, registration_confirmation_verified=True,
            original_anonymous_start_verified=True, full_cold_reset_verified=True,
            actual_ordinary_input_verified=True, session_persistence_required=False,
            actor_executed=False, training_admitted=False)
        self.sources = {SOURCE: deepcopy(dict(candidate=self.candidate, baseline=self.baseline, admission=self.admission))}
        self.descriptors = {SOURCE: deepcopy(self.descriptor)}
        self.check()

    def require_current(self): self.check()

    def close(self): self.closed = True

    def read(self, ref, *, json_value=True):
        p = Path(ref['path'])
        require(p.is_absolute() and p.is_file() and not p.is_symlink(), 'Regular absolute pinned file required')
        before = identity(p)
        raw = p.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == ref['sha256'] and identity(p) == before, 'Pinned file changed: '+str(p))
        self.files[p] = before
        return json.loads(raw) if json_value else raw

    def archive(self, archive, index):
        raw = self.read(archive, json_value=False)
        declared = self.read(index)
        require(declared['archive_sha256'] == archive['sha256'] and declared['writer_termination_confirmed'] is True, 'Closed native archive required')
        seen = set()
        with tarfile.open(fileobj=BytesIO(raw)) as stream:
            for member in stream:
                path = PurePosixPath(member.name)
                require(member.isfile() and not path.is_absolute() and '..' not in path.parts
                        and member.name in declared['members'] and member.name not in seen, 'Unsafe or unexpected native member')
                data = stream.extractfile(member).read()
                require({'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()} == declared['members'][member.name], 'Native member changed')
                seen.add(member.name)
        require(seen == set(declared['members']), 'Native archive incomplete')

    def check(self):
        require(not self.closed and all(identity(p) == val for p, val in self.files.items()), 'Reviewed evidence/runtime changed or closed')

    def resolve(self, source, descriptor):
        self.check()
        require(source == SOURCE and descriptor == self.descriptor, 'Exact new-scope source descriptor required')
        return deepcopy(dict(candidate=self.candidate, baseline=self.baseline, admission=self.admission))


class RegistrationAdapter(FrozenSignupDocumentAdapter):
    FEEDBACK_VERSIONS = ('native-register-confirm-terminal-v183',)

    def verified(self, c, descriptor):
        candidate = self.canonical(c)
        source = self.resolve(candidate['source_task_id'], descriptor)
        a = source['admission']
        require(source['candidate'] == candidate and a.get('version') == ADMISSION
                and a.get('source_task_id') == SOURCE and a.get('baseline') == source['baseline']
                and a.get('session_persistence_required') is False
                and all(a.get(k) is True for k in ['passed', 'registration_confirmation_verified',
                    'original_anonymous_start_verified', 'full_cold_reset_verified', 'actual_ordinary_input_verified']),
                'Registration-only admission is incomplete or mismatched')
        return source

    def NativeReadHooks(self, c, descriptor, directory):
        source = self.verified(c, descriptor)
        return RegistrationHooks(self.canonical(c), directory, baseline=source['baseline'])

    def feedback(self, judgment):
        require(judgment.get('version') in self.FEEDBACK_VERSIONS, 'Wrong registration feedback version')
        return dict(status=judgment['status'], reward=judgment['reward'],
            checks=[dict(condition=k, passed=v) for k, v in judgment['checks'].items() if type(v) is bool],
            private_reference_values_provided=False, action_sequence_provided=False)


@contextmanager
def bound(catalog):
    adapter = RegistrationAdapter(resolve_proof=catalog.resolve)
    bundle = ReviewedProtocolBundle([(adapter, [catalog.candidate])])
    name = 'registration_confirm_actor_v183'
    native_goal_dispatch.register_protocol(name, bundle)
    try:
        require(native_goal_dispatch.protocol(catalog.candidate) is bundle, 'Ambiguous source dispatch')
        yield bundle
        catalog.check()
    finally:
        native_goal_dispatch.unregister_protocol(name, bundle)
