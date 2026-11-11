"""Independent formal closure/Actor review using the existing evidence helpers.

This module creates no launch, claim, authorization, website or model. A trusted
CPU caller supplies pinned helper functions and an already-loaded tokenizer-only
Actor renderer. Formal native judgments, Generator/Teacher requests and export
remain the responsibility of native_training.audit_native_training_source.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tarfile
from types import SimpleNamespace

from lab_generate_skill.native_training import callback_pin, pin, require
from lab_generate_skill.stage1_local import read_pinned_json

FORMAL_CLAIM_ROOT = Path('/anvme/workspace/r102bf10-lab-generate-skill/claims/sft-formal-native-stage1')


def reconstruct_declared_actor(*, reconstruct, actor_memory_policy, scope, trace, **kwargs):
    """The released source, execution scope and actual memory must agree."""
    require(scope.get('actor_memory_policy') == actor_memory_policy,
            'Actual Actor memory policy differs from formal source plan')
    if actor_memory_policy is None:
        require('actor_memory_evidence' not in trace['task_output'], 'Undeclared Actor memory mode')
        return reconstruct(trace=trace, **kwargs)
    from .actor_request_review import reconstruct as reconstruct_memory
    return reconstruct_memory(trace=trace, actor_memory_policy=actor_memory_policy, **kwargs)


def _review_execution(binding, plan, source_plan_ref, outer, *, require_claim, sbatch_command, consume, capture):
    """Only new formal job/claim/closed-writer bindings; no models or native replay."""
    source, job = plan['sources'][0], binding['execution_job_id']
    # Formal has its own stable source phase, separate from the prior local
    # trial. Neither a new plan hash nor a new output creates another claim key.
    workflow = consume(binding['workflow']); receipt = consume(binding['submission'])
    require(receipt['plan'] == binding['workflow']['path']
            and receipt['plan_sha256'] == binding['workflow']['sha256'], 'Submission workflow differs')
    stages = [row for row in workflow['stages'] if row['id'] == binding['stage_id']]
    rows = {key: value for key, value in receipt['stages'].items() if value.get('status') == 'submitted'}
    require(len(stages) == 1 and source_plan_ref in stages[0]['inputs']
            and rows[binding['stage_id']]['job_id'] == job
            and rows[binding['stage_id']]['command'] == sbatch_command(stages[0], rows),
            'Actual formal source job/command differs')
    authorization = consume(binding['authorization'])
    require(authorization['source_plan'] == source_plan_ref
            and authorization['source_task_ids'] == [source['source_task_id']], 'Actual formal authorization differs')
    owner = require_claim(source_plan_ref, binding['authorization'], job)
    require(owner['phase'] == 'formal-native-stage1' and owner['source_plan'] == source_plan_ref
            and owner['authorization'] == binding['authorization'] and owner['capsule'] == plan['capsule']
            and all(owner[key] == source[key] for key in ('source_task_id','active_task_id','runtime_task_id'))
            and owner['job_id'] == job and owner['result_directory'] == plan['result_directory']
            and owner['automatic_retry'] is False, 'Canonical formal source claim differs')
    owner_path = FORMAL_CLAIM_ROOT/source['source_task_id']/'owner.json'
    require(binding['claim_owner']['path'] == str(owner_path)
            and consume(binding['claim_owner']) == owner, 'Original formal owner record differs')

    started = capture(outer/'started.json'); termination = capture(outer/'termination.json')
    completed = capture(outer/'completed.json'); watchdog = capture(outer/'watchdog.json')
    require(started['source_plan'] == source_plan_ref and started['job_id'] == job
            and started['source'] == source['source_task_id'] and started['capsule'] == plan['capsule']
            and completed['source_plan'] == source_plan_ref and completed['job_id'] == job
            and completed['passed'] is True and completed['returncode'] == 0,
            'Original formal source completion differs')
    require(termination['confirmed'] is True and termination['returncode'] == 0
            and termination['group']['process_group'] == watchdog['pid']
            and termination['group']['live_members'] == []
            and termination['scope']['live_scratch_references'] == []
            and termination['scope']['unreadable_same_uid_pids'] == [],
            'Original evidence writers were not proved quiescent')
    require(not any((outer/name).exists() for name in
            ('closure-error.json', 'watchdog.timeout.json', 'watchdog.exit.json')),
            'An unresolved runtime/closure error remains')



def make_closed_source_reviewer(*, execution_ref, runtime, actor_backend,
        require_claim, sbatch_command, verify_archive, select_archive, reconstruct):
    """Bind actual execution evidence in the trusted caller, never in a record.

    The returned ordinary function matches the existing complete-source callback
    signature and can be source-pinned by native_training.callback_pin. Imported
    helpers are supplied explicitly; no callback is imported from saved data.
    """
    helpers = dict(require_claim=require_claim, sbatch_command=sbatch_command,
        verify_archive=verify_archive, select_archive=select_archive, reconstruct=reconstruct)
    execution_ref = deepcopy(execution_ref)
    runtime = Path(runtime).resolve()

    def review_closed_source(base, source_plan_ref):
        require(os.environ.get('SLURM_JOB_ID') and os.environ.get('CUDA_VISIBLE_DEVICES') == '-1',
                'Scheduled CPU review required')
        binding = read_pinned_json(execution_ref)
        plan = read_pinned_json(source_plan_ref)
        base = Path(base).resolve(); outer = base.parent
        require(binding['version'] == 'formal-native-completed-execution-v1'
                and binding['source_plan'] == source_plan_ref
                and str(base) == plan['result_directory'] == binding['result_directory']
                and plan['purpose'] == 'training' and plan['training_data'] is True,
                'Original formal execution binding differs')
        source = plan['sources'][0]; job = binding['execution_job_id']
        require(len(plan['sources']) == 1 and source['source_task_id'] == binding['source_task_id']
                and plan['capsule'] == binding['capsule'] and isinstance(job, str) and job.isdecimal(),
                'Actual source, capsule or execution job differs')
        files = [execution_ref, source_plan_ref]
        def consume(ref):
            value = read_pinned_json(ref); files.append(ref); return value
        def capture(path):
            path = Path(path)
            require(path.is_file() and not path.is_symlink(), 'Regular original evidence required')
            return consume(pin(path))
        for name, callback in helpers.items():
            expected = binding['helpers'][name]
            callback_pin(callback, expected); files.append(expected)
        for name, callback in [('candidate_layout', select_archive.__globals__['candidate_layout']),
                               ('archive_sha', verify_archive.__globals__['sha'])]:
            expected = binding['helper_dependencies'][name]
            callback_pin(callback, expected); files.append(expected)

        _review_execution(binding, plan, source_plan_ref, outer, require_claim=require_claim,
            sbatch_command=sbatch_command, consume=consume, capture=capture)

        # Load only the actual frozen runtime supplied by the CPU caller.
        from run_formal_native_source import qualified_inputs, initial_binding, orchestration_binding
        from local_pilot_evidence_group6 import attest_runtime
        from lab_generate_skill.stage1_live_binding import validate_qualified_capture
        from lab_generate_skill.stage1_execution_steps import METRIC, selection_steps
        from lab_generate_skill.config import GenerationSettings
        from lab_generate_skill.llm import TransformersChatBackend
        from lab_generate_skill.observation_budget import fit_actor_messages
        from lab_generate_skill.action_history import observed_targets
        from lab_generate_skill.gobrowse_runtime import validate_upload_action
        from lab_generate_skill.generator_sft import fingerprint
        from lab_generate_skill.runtime_profile import PROFILE
        from run_site_navigation_skill_once import task_actor_protocol
        capsule = consume(plan['capsule'])
        attestation = attest_runtime(runtime, plan['capsule'], plan['entries'])
        for name, module in list(sys.modules.items()):
            if not name.startswith('lab_generate_skill'): continue
            filename = getattr(module, '__file__', None)
            require(filename is not None and Path(filename).resolve().is_relative_to(runtime),
                    'Imported project module escaped the executed capsule')
        for name, digest in binding['runtime_request_members'].items():
            require(capsule['members'][name]['sha256'] == digest, 'Actor reconstruction runtime differs')
        contract = consume(plan['local_contract'])
        prepared = qualified_inputs(SimpleNamespace(plan=plan, source=source, contract=contract))
        context = capture(base/'stage1/context.json'); start = context['start']
        result = capture(base/'stage1/result.json'); attempts = result['attempts']
        require(context['refs'] == prepared['refs'] and capture(base/'retrieval.json') == prepared['retrieval_proof'],
                'Original qualified retrieval evidence differs')
        require(capture(base/'current-start.json') == start, 'Recorded actual initial state differs')
        actual_capture = capture(base/'prepared-context.json')
        require(initial_binding(plan, prepared, actual_capture, base)
                == capture(base/'qualified-initial-binding.json'), 'Actual initial capture differs')
        declarative = plan.get('native_source_adapter') in ('registered_admin_declarative_v1', 'registered_admin_legacy_v1')
        admin = declarative or plan.get('native_source_adapter') == 'registered_admin_navigation_v1'
        reddit_native = plan.get('native_source_adapter') == 'registered_reddit_native_v1'
        shopping_offline = plan.get('native_source_adapter') == 'registered_shopping_offline_v1'
        gitlab_read = plan.get('native_source_adapter') == 'registered_gitlab_read_v1'
        reading = plan.get('native_source_adapter') == 'registered_reading_v1'
        map_export = plan.get('native_source_adapter') == 'registered_map_export_v1'
        map_view = plan.get('native_source_adapter') == 'registered_map_view_v1'
        reddit_retained_reading = plan.get('native_source_adapter') == 'registered_reddit_retained_reading_v1'
        reddit_explicit = plan.get('native_source_adapter') == 'registered_reddit_explicit_v1'
        reddit_reviewed = plan.get('native_source_adapter') == 'registered_reddit_reviewed_v1'
        gitlab_native_goal = plan.get('native_source_adapter') == 'registered_gitlab_native_goal_v1'
        shopping_read = plan.get('native_source_adapter') == 'registered_shopping_read_v1'
        map_route_family = plan.get('native_source_adapter') == 'registered_map_route_family_v1'
        map_account = plan.get('native_source_adapter') == 'registered_map_account_v1'
        map_content = plan.get('native_source_adapter') == 'registered_map_content_v1'
        map_node = plan.get('native_source_adapter') == 'registered_map_node_v1'
        map_raster = plan.get('native_source_adapter') == 'registered_map_raster_v1'
        map_link = plan.get('native_source_adapter') == 'registered_map_link_v1'
        map_overlay = plan.get('native_source_adapter') == 'registered_map_overlay_v1'
        map_surface = plan.get('native_source_adapter') == 'registered_map_surface_v1'
        map_typed = plan.get('native_source_adapter') == 'registered_map_typed_v1'
        gitlab_browser_artifact = plan.get('native_source_adapter') == 'registered_gitlab_browser_artifact_v1'
        gitlab_artifact = plan.get('native_source_adapter') == 'registered_gitlab_artifact_v1'
        gitlab_document = plan.get('native_source_adapter') == 'registered_gitlab_document_v1'
        map_provider = plan.get('native_source_adapter') == 'registered_map_provider_v1'
        map_finite = plan.get('native_source_adapter') == 'registered_map_finite_v1'
        map_facts = plan.get('native_source_adapter') == 'registered_map_facts_v1'
        route = plan.get('native_source_adapter') == 'registered_route_v1'
        grouped = plan.get('native_source_adapter') == 'registered_grouped_v1'
        query = (plan.get('native_source_adapter') == 'registered_query_v1'
                 or ((map_typed or map_surface or grouped or map_export or shopping_read or map_finite or map_facts or route or reading or reddit_native) and bool(prepared['source_binding']['answer_fields']))
                 or (declarative and bool(prepared['native'].get('answer_fields'))))
        if admin:
            from .admin_pilot import actor_goal
            native_goal = actor_goal(prepared['native'])
        elif reddit_native:
            from reddit_native_sft_binding import public_interface
            native_goal = public_interface(prepared['native'])
        elif shopping_offline:
            from shopping_offline_sft_binding import public_interface
            native_goal = public_interface(prepared['native'])
        elif gitlab_read:
            from gitlab_read_sft_binding import public_interface
            native_goal = public_interface(prepared['native'])
        elif reading:
            from reading_sft_binding import public_interface
            native_goal = public_interface(prepared['native'])
        elif map_export:
            from map_export_sft_binding import public_interface
            native_goal = public_interface(prepared['native'])
        elif gitlab_native_goal:
            from gitlab_native_goal_sft_binding import public_interface
            native_goal = public_interface(prepared['native'])
        elif shopping_read:
            from shopping_read_sft_binding import public_interface
            native_goal = public_interface(prepared['native'])
        elif map_facts:
            from map_facts_sft_binding import public_interface
            native_goal = public_interface(prepared['native'])
        elif map_route_family:
            from map_route_family_sft_binding import public_interface
            native_goal = public_interface(prepared['native'])
        elif map_account:
            from map_account_sft_binding import public_interface
            native_goal = public_interface(prepared['native'])
        elif map_content:
            from map_content_sft_binding import public_interface
            native_goal = public_interface(prepared['native'])
        elif map_node:
            from map_node_sft_binding import public_interface
            native_goal = public_interface(prepared['native'])
        elif map_raster:
            from map_raster_sft_binding import public_interface
            native_goal = public_interface(prepared['native'])
        elif map_link:
            from map_link_sft_binding import public_interface
            native_goal = public_interface(prepared['native'])
        elif map_overlay:
            from map_overlay_sft_binding import public_interface
            native_goal = public_interface(prepared['native'])
        elif gitlab_browser_artifact:
            from gitlab_browser_artifact_sft_binding import public_interface
            native_goal = public_interface(prepared['native'])
        elif map_typed:
            from map_typed_sft_binding import public_interface
            native_goal = public_interface(prepared['native'])
        elif map_surface:
            from map_surface_sft_binding import public_interface
            native_goal = public_interface(prepared['native'])
        elif gitlab_artifact:
            from gitlab_artifact_sft_binding import public_interface
            native_goal = public_interface(prepared['native'])
        elif gitlab_document:
            from gitlab_document_sft_binding import public_interface
            native_goal = public_interface(prepared['native'])
        elif map_provider:
            from map_provider_sft_binding import public_interface
            native_goal = public_interface(prepared['native'])
        elif map_finite:
            from map_finite_sft_binding import public_interface
            native_goal = public_interface(prepared['native'])
        elif route:
            from route_sft_binding import public_interface
            native_goal = public_interface(prepared['native'])
        elif grouped:
            from grouped_sft_binding import public_interface
            native_goal = public_interface(prepared['native'])
        elif query:
            from query_sft_binding import public_interface
            native_goal = public_interface(prepared['native'])
        else:
            native_goal = prepared['native']['goal']
        require(start['task'] == contract['public_goal'] == native_goal
                and start['website_snapshot_id'] == prepared['baseline'], 'Actual public goal/snapshot differs')

        index = capture(outer/'closed-episode-archive.json')
        archive = dict(path=str(outer/'closed-episode-diagnostics.tar.gz'), sha256=index['archive_sha256'])
        verify_archive(archive['path'], index['members'], archive['sha256']); files.append(archive)
        # Existing reader validates safe inventory and the complete 4+1..3
        # candidate layout, then selects the original raw Actor records.
        selected = select_archive(archive, index, attempts, source['runtime_task_id'])
        for name, path in [('current-start.json', base/'current-start.json'),
                ('initial-context/'+source['runtime_task_id']+'/prepared-context.json', base/'prepared-context.json')]:
            require(index['members'][name] == dict(bytes=path.stat().st_size, sha256=pin(path)['sha256']),
                    'Actual initial evidence is not bound to the closed archive')
        if plan.get('native_source_adapter') is not None:
            if admin:
                if declarative:
                    from admin_declarative_initial import FILES
                else:
                    from admin_sft_initial import FILES
                initial_files = FILES
            elif reddit_native:
                from reddit_native_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
            elif shopping_offline:
                from shopping_offline_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
            elif gitlab_read:
                from gitlab_read_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
            elif reading:
                from reading_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
            elif map_export:
                from map_export_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
                initial_files.update({name: name for name in capture(base/'initial-native/map-export-native-evidence.json')['raw_members']})
            elif reddit_retained_reading:
                from reddit_retained_reading_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
            elif reddit_explicit:
                from reddit_explicit_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
            elif reddit_reviewed:
                from reddit_reviewed_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
            elif map_view:
                from map_view_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
            elif gitlab_native_goal:
                from gitlab_native_goal_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
                initial_files.update({name: name for name in capture(base/'initial-native/gitlab-native-goal-terminal-reads.json')['raw_members']})
            elif shopping_read:
                from shopping_read_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
                initial_files.update({name: name for name in capture(base/'initial-native/shopping-read-terminal-reads.json')['raw_members']})
            elif map_facts:
                from map_facts_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
                initial_files.update({name: name for name in capture(base/'initial-native/map-facts-native-evidence.json')['raw_members']})
            elif map_route_family:
                from map_route_family_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
                initial_files.update({name: name for name in capture(base/'initial-native/map-route-native-evidence.json')['raw_members']})
            elif map_account:
                from map_account_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
                initial_files.update({name: name for name in capture(base/'initial-native/map-account-native-evidence.json')['raw_members']})
            elif map_content:
                from map_content_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
                initial_files.update({name: name for name in capture(base/'initial-native/map-content-native-evidence.json')['raw_members']})
            elif map_node:
                from map_node_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
                initial_files.update({name: name for name in capture(base/'initial-native/map-node-native-evidence.json')['raw_members']})
            elif map_raster:
                from map_raster_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
                initial_files.update({name: name for name in capture(base/'initial-native/map-raster-native-evidence.json')['raw_members']})
            elif map_link:
                from map_link_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
                initial_files.update({name: name for name in capture(base/'initial-native/map-link-native-evidence.json')['raw_members']})
            elif map_overlay:
                from map_overlay_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
                initial_files.update({name: name for name in capture(base/'initial-native/map-overlay-native-evidence.json')['raw_members']})
            elif gitlab_browser_artifact:
                from gitlab_browser_artifact_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
                initial_files.update({name: name for name in capture(base/'initial-native/gitlab-browser-artifact-evidence.json')['raw_members']})
            elif map_typed:
                from map_typed_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
                initial_files.update({name: name for name in capture(base/'initial-native/map-typed-native-evidence.json')['raw_members']})
            elif map_surface:
                from map_surface_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
                initial_files.update({name: name for name in capture(base/'initial-native/map-surface-native-evidence.json')['raw_members']})
            elif gitlab_artifact:
                from gitlab_artifact_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
                initial_files.update({name: name for name in capture(base/'initial-native/gitlab-artifact-native-evidence.json')['raw_members']})
            elif gitlab_document:
                from gitlab_document_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
                initial_files.update({name: name for name in capture(base/'initial-native/gitlab-document-native-evidence.json')['raw_members']})
            elif map_provider:
                from map_provider_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
                initial_files.update({name: name for name in capture(base/'initial-native/map-provider-native-evidence.json')['raw_members']})
            elif map_finite:
                from map_finite_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
                initial_files.update({name: name for name in capture(base/'initial-native/map-finite-native-evidence.json')['raw_members']})
            elif route:
                from route_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
                initial_files.update({name: name for name in capture(base/'initial-native/route-native-evidence.json')['raw_members']})
            elif grouped:
                from grouped_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
            elif query:
                from query_sft_initial import names as initial_names
                initial_files = initial_names('query', domain=source['domain'], binding=prepared['source_binding'])
            elif plan.get('native_source_adapter') == 'registered_stateful_v1':
                from stateful_sft_initial import names as initial_names
                initial_files = initial_names(prepared['native'])
            elif plan.get('native_source_adapter') == 'registered_catalog_v1':
                from catalog_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding'])
            else:
                from ordinary_sft_initial import names as initial_names
                initial_files = initial_names(prepared['source_binding']['protocol'], domain=source['domain'])
            for name in initial_files.values():
                path = base/'initial-native'/name
                require(index['members']['initial-context/'+source['runtime_task_id']+'/'+name]
                        == dict(bytes=path.stat().st_size, sha256=pin(path)['sha256']),
                        'Actual initial native evidence differs from the closed archive')
                files.append(pin(path))
        require({path.name for path in (base/'evidence').iterdir()} == {str(i) for i in range(len(attempts))},
                'Unretained candidate evidence tail')
        expected_stage = {'context.json', 'result.json'} | {
            attempt['source']+'-'+str(attempt['index'])+'-trajectory.json' for attempt in attempts}
        require({path.name for path in (base/'stage1').iterdir()} == expected_stage, 'Unretained stage evidence tail')
        require({path.name for path in base.glob('teacher-*-actual-input.json')}
                == {'teacher-'+str(attempt['index'])+'-actual-input.json' for attempt in attempts[4:]},
                'Unretained Teacher input sidecar')

        actor_settings = GenerationSettings(backend='transformers', model=binding['actor_model'],
            temperature=0, enable_thinking=False, max_input_tokens=16384, max_new_tokens=512, dtype='bfloat16')
        require(isinstance(actor_backend, TransformersChatBackend) and actor_backend._model is None
                and actor_backend._tokenizer is not None and actor_backend.model_name == binding['actor_model']
                and actor_backend.settings == actor_settings, 'Tokenizer-only original Actor renderer required')
        require({Path(ref['path']).name for ref in binding['tokenizer_files']}
                == {'config.json','generation_config.json','tokenizer.json','tokenizer_config.json','vocab.json','merges.txt'}
                and len(binding['tokenizer_files']) == 6
                and all(Path(ref['path']).parent == Path(binding['actor_model']) for ref in binding['tokenizer_files'])
                and actor_backend._tokenizer.name_or_path == binding['actor_model'], 'Original Actor tokenizer binding incomplete')
        for ref in binding['tokenizer_files']:
            require(pin(ref['path']) == ref, 'Pinned Actor tokenizer differs'); files.append(ref)
        def count(messages): return len(actor_backend._tokenizer(actor_backend._render(messages))['input_ids'])
        proofs = []
        for number, attempt in enumerate(attempts):
            stem = 'candidate-'+str(number)+'/'+source['runtime_task_id']+'/'
            def get(name): return selected[stem+name]
            def records(prefix):
                names = sorted(name for name in selected if name.startswith(stem+prefix) and name.endswith('.json'))
                require(names == [stem+prefix+('%03d.json'%i) for i in range(len(names))], 'Nonconsecutive raw records')
                return [selected[name] for name in names]
            trace_ref = dict(path=attempt['validation']['trajectory_path'], sha256=attempt['validation']['trajectory_sha256'])
            require(Path(trace_ref['path']).resolve() == base/'stage1'/(attempt['source']+'-'+str(attempt['index'])+'-trajectory.json'),
                    'Candidate trajectory escaped the original source')
            normalized = deepcopy(consume(trace_ref)); execution = normalized['provenance'].pop('local_execution_evidence')
            require(Path(execution['path']).resolve() == base/'evidence'/str(number)/'receipt.json', 'Candidate receipt differs')
            native_receipt = consume(execution); inner = consume(native_receipt['archive'])
            require(native_receipt['contract_sha256'] == plan['local_contract']['sha256']
                    and native_receipt['runtime_capsule_sha256'] == plan['capsule']['sha256']
                    and native_receipt['source_task_id'] == source['source_task_id']
                    and native_receipt['task_id'] == source['active_task_id']
                    and native_receipt['runtime_task_id'] == source['runtime_task_id']
                    and native_receipt['website_snapshot_id'] == start['website_snapshot_id'], 'Formal native receipt differs')
            verify_archive(inner['path'], inner['members'], inner['archive_sha256'])
            files.append(dict(path=inner['path'], sha256=inner['archive_sha256']))
            require({name[len(stem):]: member for name, member in index['members'].items() if name.startswith(stem)}
                    == inner['members'] and normalized == get('trajectory.json'), 'Whole native candidate archive differs')
            # The new owner records formal pins, without the local-only files key.
            # This member is not copied into the durable artifact subset; read
            # it directly from its already fully verified candidate archive.
            with tarfile.open(inner['path'], 'r:gz') as stream:
                raw = stream.extractfile('batch-orchestration.json').read()
            require(json.loads(raw) == orchestration_binding(plan, source_plan_ref),
                    'Actual formal orchestration binding differs')
            for key in ('task_id','domain','seed','task_instruction','model','rounds','messages','generation_finish_reasons'):
                require(get('rollout-raw.json')[key] == get('trajectory.json')[key], 'Native scoring changed request evidence')
            budget = get('actor-budget.json'); scope = selected['candidate-'+str(number)+'/scope.json']
            require(budget['max_new_tokens'] == (PROFILE['query_max_output_tokens'] if query else 512)
                    and budget['basis'] == ('public_query_interface' if query else 'browser_actions')
                    and budget['private_reference_used'] is False
                    and scope['runtime_profile'] == PROFILE and scope['max_steps'] == 20
                    and scope['scripted'] is False and scope['api_calls'] == 0, 'Original Actor protocol/budget differs')
            selected_reconstruct = reconstruct
            if reddit_native:
                require(consume(native_receipt['artifacts']['prepared_reset'])
                        == capture(base/'initial-native/reddit-native-source-reset.json'),
                        'Candidate native Reddit reset differs from actual source context')
            if shopping_offline:
                require(consume(native_receipt['artifacts']['prepared_reset'])
                        == capture(base/'initial-native/shopping-offline-source-reset.json'),
                        'Candidate native document reset differs from actual source context')
            if gitlab_read:
                require(consume(native_receipt['artifacts']['prepared_reset'])
                        == capture(base/'initial-native/gitlab-read-source-reset.json'),
                        'Candidate native document reset differs from actual source context')
            if reading:
                require(consume(native_receipt['artifacts']['prepared_reset'])
                        == capture(base/'initial-native/reading-source-reset.json'),
                        'Candidate reading native reset differs from actual source context')
            if map_export:
                require(consume(native_receipt['artifacts']['prepared_reset'])
                        == capture(base/'initial-native/map-export-source-reset.json'),
                        'Candidate export reset differs from actual source context')
            if reddit_retained_reading:
                require(consume(native_receipt['artifacts']['prepared_reset'])
                        == capture(base/'initial-native/retained-reading-source-reset.json'),
                        'Candidate explicit native Reddit native reset differs from actual source context')
            if reddit_explicit:
                require(consume(native_receipt['artifacts']['prepared_reset'])
                        == capture(base/'initial-native/reddit-explicit-source-reset.json'),
                        'Candidate explicit native Reddit native reset differs from actual source context')
            if reddit_reviewed:
                require(consume(native_receipt['artifacts']['prepared_reset'])
                        == capture(base/'initial-native/reddit-reviewed-source-reset.json'),
                        'Candidate reviewed Reddit native reset differs from actual source context')
            if map_view:
                require(consume(native_receipt['artifacts']['prepared_reset'])
                        == capture(base/'initial-native/map-view-source-reset.json'),
                        'Candidate map view native reset differs from actual source context')
            if shopping_read:
                require(consume(native_receipt['artifacts']['prepared_reset'])
                        == capture(base/'initial-native/shopping-read-source-reset.json'),
                        'Candidate Shopping reading native reset differs from actual source context')
                from shopping_read_sft_public_order import enabled as order_enabled, validate as validate_order, FILE as order_file
                if order_enabled(prepared['source_binding']):
                    validate_order(consume(native_receipt['artifacts']['initial_public_order']),
                                   prepared['native'], capture=False,
                                   source=capture(base/'initial-native'/order_file))
            if map_facts:
                require(consume(native_receipt['artifacts']['prepared_reset'])
                        == capture(base/'initial-native/map-facts-source-reset.json'),
                        'Candidate Map facts native reset differs from actual source context')
            elif map_route_family:
                require(consume(native_receipt['artifacts']['prepared_reset'])
                        == capture(base/'initial-native/map-route-source-reset.json'),
                        'Candidate Map route-family native reset differs from actual source context')
            elif map_account:
                require(consume(native_receipt['artifacts']['prepared_reset'])
                        == capture(base/'initial-native/map-account-source-reset.json'),
                        'Candidate Map account native reset differs from actual source context')
            elif map_content:
                require(consume(native_receipt['artifacts']['prepared_reset'])
                        == capture(base/'initial-native/map-content-source-reset.json'),
                        'Candidate Map content native reset differs from actual source context')
            elif map_node:
                require(consume(native_receipt['artifacts']['prepared_reset'])
                        == capture(base/'initial-native/map-node-source-reset.json'),
                        'Candidate Map node native reset differs from actual source context')
            elif map_raster:
                require(consume(native_receipt['artifacts']['prepared_reset'])
                        == capture(base/'initial-native/map-raster-source-reset.json'),
                        'Candidate Map raster native reset differs from actual source context')
            elif map_link:
                require(consume(native_receipt['artifacts']['prepared_reset'])
                        == capture(base/'initial-native/map-link-source-reset.json'),
                        'Candidate Map link native reset differs from actual source context')
            elif map_overlay:
                require(consume(native_receipt['artifacts']['prepared_reset'])
                        == capture(base/'initial-native/map-overlay-source-reset.json'),
                        'Candidate Map overlay native reset differs from actual source context')
            elif map_surface:
                require(consume(native_receipt['artifacts']['prepared_reset'])
                        == capture(base/'initial-native/map-surface-source-reset.json'),
                        'Candidate Map surface native reset differs from actual source context')
            elif gitlab_artifact:
                require(consume(native_receipt['artifacts']['prepared_reset'])
                        == capture(base/'initial-native/gitlab-artifact-source-reset.json'),
                        'Candidate GitLab artifact native reset differs from actual source context')
            elif gitlab_document:
                require(consume(native_receipt['artifacts']['prepared_reset'])
                        == capture(base/'initial-native/gitlab-document-source-reset.json'),
                        'Candidate GitLab document native reset differs from actual source context')
            elif map_provider:
                require(consume(native_receipt['artifacts']['prepared_reset'])
                        == capture(base/'initial-native/map-provider-source-reset.json'),
                        'Candidate Map provider native reset differs from actual source context')
            elif map_finite:
                require(consume(native_receipt['artifacts']['prepared_reset'])
                        == capture(base/'initial-native/map-finite-source-reset.json'),
                        'Candidate Map finite native reset differs from actual source context')
            if route:
                require(consume(native_receipt['artifacts']['prepared_reset'])
                        == capture(base/'initial-native/route-source-reset.json'),
                        'Candidate route native reset differs from actual source context')
            if grouped:
                require(consume(native_receipt['artifacts']['prepared_reset'])
                        == capture(base/'initial-native/grouped-source-reset.json'),
                        'Candidate grouped native reset differs from actual source context')
            if plan.get('native_source_adapter') == 'registered_stateful_v1':
                require(consume(native_receipt['artifacts']['prepared_protection'])
                        == capture(base/'initial-native/selected-state-integrity.json')
                        and consume(native_receipt['artifacts']['prepared_references'])
                        == capture(base/'initial-native/stateful-references-before.json'),
                        'Candidate stateful baseline differs from the actual source context')
            if plan.get('native_source_adapter') == 'registered_catalog_v1':
                require(consume(native_receipt['artifacts']['prepared_protection'])
                        == capture(base/'initial-native/selected-state-integrity.json'),
                        'Candidate catalog baseline differs from actual source context')
                if prepared['source_binding']['protection_algorithm']=='native_full22':
                    require(consume(native_receipt['artifacts']['prepared_selected'])
                            == capture(base/'initial-native/search-selected-before.json'),
                            'Candidate selected catalog state differs from actual source context')
            if admin:
                from .admin_actor_request_review import reconstruct as admin_reconstruct
                require(consume(native_receipt['artifacts']['prepared_context']) == actual_capture,
                        'Admin candidate did not retain the actual source initial capture')
                if declarative:
                    require(consume(native_receipt['artifacts']['prepared_public_controls'])
                            == capture(base/'initial-native/initial-public-controls.json'),
                            'Admin candidate public controls differ from the source initial capture')
                def selected_reconstruct(**kwargs):
                    from .browser_assets import upload_file_metadata
                    resources = upload_file_metadata(prepared['native']['spec'].get('upload_resources', [])) if declarative else []
                    public_controls = (dict(prepared=consume(native_receipt['artifacts']['prepared_public_controls']),
                        actual=consume(native_receipt['artifacts']['public_controls'])) if declarative else None)
                    return admin_reconstruct(prepared_context=actual_capture, query=query,
                                             upload_files=resources, public_controls=public_controls, **kwargs)
            elif plan.get('native_source_adapter') is not None:
                from .ordinary_actor_request_review import reconstruct as ordinary_reconstruct
                def selected_reconstruct(**kwargs):
                    return ordinary_reconstruct(domain=source['domain'], query=query, **kwargs)
            if admin:
                from .runtime_profile import actor_protocol
                protocol = actor_protocol(answer_fields=prepared['native'].get('answer_fields') if declarative else None)
            else:
                protocol = task_actor_protocol(actor_backend, prepared['native'])
            proof = reconstruct_declared_actor(reconstruct=selected_reconstruct,
                actor_memory_policy=plan.get('actor_memory_policy'),scope=scope,
                trace=get('rollout-raw.json'),steps=records('step-'),generations=records('generation-'),
                skill=attempt['skill'],goal=start['task'],task_id=source['runtime_task_id'],snapshot_id=start['website_snapshot_id'],
                model_path=binding['actor_model'],protocol=protocol,count_tokens=count,
                fit_messages=fit_actor_messages,observed_targets=observed_targets,validate_upload_action=validate_upload_action,
                skill_fingerprint=fingerprint,initial_guard=get('initial-request-binding.json'),initial_observation=start['initial_observation'])
            require(attempt['selection_metric'] == METRIC and type(attempt['steps']) is int
                    and selection_steps(get('rollout-raw.json')) == selection_steps(get('trajectory.json')) == proof['executed_actions'] == attempt['steps']
                    and attempt['generation_rounds'] == get('trajectory.json')['rounds'], 'Actual action-count selection differs')
            proofs.append(dict(candidate_index=number, trajectory=trace_ref, **proof))
        requests = sorted((base/'requests').iterdir())
        require(requests and all(path.is_file() and not path.is_symlink() and path.suffix == '.json' for path in requests),
                'Unexpected model request ledger inventory')
        for path in requests: require(capture(path)['status'] == 'complete', 'Unresolved model request')
        for ref in files: require(pin(ref['path']) == ref, 'Original source evidence changed during review')
        unique = {ref['path']: ref for ref in files}
        return dict(passed=True, source_plan=source_plan_ref, source_task_id=source['source_task_id'],
            capsule=plan['capsule'], execution_job_id=job, closure_verified=True, claim_verified=True,
            initial_qualification_verified=True, whole_archive_verified=True, full_actual_requests_verified=True,
            unresolved_model_requests=0, unresolved_actor_episodes=0, candidates=proofs,
            actual_actor_requests_verified=sum(row['requests_verified'] for row in proofs),
            files=[unique[path] for path in sorted(unique)], runtime_capsule_members_verified=len(attestation['members']),
            model_request_semantics='Validated separately by native_training.validate_model_requests',
            tokenizer_scope='Exact messages and counts with pinned original tokenizer; historical input_ids were not recorded')
    return review_closed_source
