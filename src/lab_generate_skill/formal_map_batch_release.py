"""Metadata-only grouping of explicitly qualified Map source runtimes."""
from copy import deepcopy
import json
from pathlib import Path

from .formal_map_batch_profiles import EXTENSION, standard_profile, supported_profile, community_manifest_family, raster_profile
from .formal_batch import read, require, write_new, prepare_release


def batch_key(item):
    if item['domain'] != 'map':
        return None
    build = read(item['prepared']['build'])
    if build.get('map_batch_ready') is not True or build.get('passed') is not True:
        return None
    plan = read(item['prepared']['source_plan_draft'])
    require(plan['capsule'] == build['capsule'], 'Qualified Map batch runtime differs')
    require(len(plan['sources']) == 1, 'One prepared source required')
    source = plan['sources'][0]; profile = source['profile']
    require(source['source_task_id'] == item['source_task_id'] and source['domain'] == 'map',
            'Prepared Map identity differs')
    if not supported_profile(profile):
        return None
    if not standard_profile(profile) and not raster_profile(profile) and build.get('map_batch_profile_extension') != EXTENSION:
        return None
    extra = {}
    if raster_profile(profile):
        route_png = (plan.get('native_source_adapter') == 'registered_map_route_family_v1'
                     and build.get('map_batch_route_png_extension') == 'native-route-png-v1')
        surface_png = (plan.get('native_source_adapter') == 'registered_map_surface_v1'
                       and build.get('map_batch_surface_extension') == 'native-surface-v1')
        if not route_png and not surface_png and (plan.get('native_source_adapter') != 'registered_map_raster_v1'
                             or build.get('map_batch_raster_extension') != 'native-raster-v1'):
            return None
        catalog = read(plan['source_binding_catalog'])
        binding = catalog['sources'][source['source_task_id']]
        require(all(source[k] == binding[k] for k in ('native_contract', 'admission', 'profile',
                'source_task_id', 'active_task_id', 'runtime_task_id', 'domain', 'evaluator_version')),
                'Prepared raster differs from its original source binding')
        if route_png:
            require(binding['native_goal_kind'] == 'route_png' and profile['optional'] ==
                    dict(map_raster_export=True, map_raster_query_policy='stable-scan'),
                    'Route PNG requires its original stable-scan renderer profile')
            extra['route_png_renderer'] = profile['optional']
        elif surface_png:
            require(binding['native_goal_kind'] in ('initial_png', 'named_png') and profile['optional'] ==
                    dict(map_raster_export=True, map_raster_query_policy='stable-scan'),
                    'Surface PNG requires its original stable-scan renderer profile')
            extra['surface_png_renderer'] = profile['optional']
        else:
            extra['raster_startup'] = {k: binding[k] for k in ('runner_arguments', 'protected_baseline_sha256',
                'renderer_profile', 'render_query_policy', 'file_format')}
    if plan.get('native_source_adapter') == 'registered_map_route_family_v1':
        if build.get('map_batch_route_family_extension') != 'native-route-family-v1':
            return None
        catalog = read(plan['source_binding_catalog'])
        binding = catalog['sources'][source['source_task_id']]
        require(all(source[k] == binding[k] for k in ('native_contract', 'admission', 'profile',
                'source_task_id', 'active_task_id', 'runtime_task_id', 'domain', 'evaluator_version')),
                'Prepared route differs from its original source binding')
        extra['route_startup'] = {k: binding[k] for k in ('runner_arguments', 'native_asset_manifest',
            'protected_baseline_sha256', 'browser_capabilities')}
    if plan.get('native_source_adapter') == 'registered_map_typed_v1':
        if build.get('map_batch_typed_extension') != 'native-typed-v1':
            return None
        catalog = read(plan['source_binding_catalog'])
        binding = catalog['sources'][source['source_task_id']]
        require(all(source[k] == binding[k] for k in ('native_contract', 'admission', 'profile',
                'source_task_id', 'active_task_id', 'runtime_task_id', 'domain', 'evaluator_version')),
                'Prepared typed source differs from its original source binding')
        extra['typed_startup'] = {k: binding[k] for k in ('profile', 'protected_baseline_sha256')}
    if plan.get('native_source_adapter') == 'registered_map_link_v1':
        if build.get('map_batch_link_extension') != 'native-link-v1':
            return None
        catalog = read(plan['source_binding_catalog'])
        binding = catalog['sources'][source['source_task_id']]
        require(all(source[k] == binding[k] for k in ('native_contract', 'admission', 'profile',
                'source_task_id', 'active_task_id', 'runtime_task_id', 'domain', 'evaluator_version')),
                'Prepared link differs from its original source binding')
        extra['link_startup'] = {k: binding[k] for k in ('runner_arguments', 'protected_baseline_sha256')}
    if plan.get('native_source_adapter') == 'registered_map_overlay_v1':
        if build.get('map_batch_overlay_extension') != 'frozen-overlay-v1':
            return None
        catalog = read(plan['source_binding_catalog'])
        binding = catalog['sources'][source['source_task_id']]
        require(all(source[k] == binding[k] for k in ('native_contract', 'admission', 'profile',
                'source_task_id', 'active_task_id', 'runtime_task_id', 'domain', 'evaluator_version')),
                'Prepared overlay differs from its original source binding')
        extra['overlay_startup'] = {k: binding[k] for k in ('native_proof', 'runner_arguments',
            'environment_binding', 'protected_baseline_sha256')}
    if plan.get('native_source_adapter') == 'registered_map_surface_v1':
        if build.get('map_batch_surface_extension') != 'native-surface-v1':
            return None
        catalog = read(plan['source_binding_catalog'])
        binding = catalog['sources'][source['source_task_id']]
        require(all(source[k] == binding[k] for k in ('native_contract', 'admission', 'profile',
                'source_task_id', 'active_task_id', 'runtime_task_id', 'domain', 'evaluator_version')),
                'Prepared surface differs from its original source binding')
        extra['surface_startup'] = {k: binding[k] for k in ('native_proof', 'runner_arguments',
            'environment_binding', 'protected_baseline_sha256')}
        png = binding['native_goal_kind'] in ('initial_png', 'named_png')
        require(png == raster_profile(profile) and binding['runner_arguments'] ==
                ['--map-instances', '1'] + ([] if png else ['--map-share-observer']),
                'Original surface observer/renderer startup arguments required')
    if plan.get('native_source_adapter') == 'registered_map_provider_v1':
        if build.get('map_batch_provider_extension') != 'frozen-provider-v1':
            return None
        catalog = read(plan['source_binding_catalog'])
        binding = catalog['sources'][source['source_task_id']]
        require(all(source[k] == binding[k] for k in ('native_contract', 'admission', 'profile',
                'source_task_id', 'active_task_id', 'runtime_task_id', 'domain', 'evaluator_version')),
                'Prepared provider differs from its original source binding')
        extra['provider_startup'] = {k: binding[k] for k in ('provider_profile', 'runner_arguments',
            'environment_binding', 'protected_baseline_sha256')}
    if not standard_profile(profile):
        contract = read(source['native_contract'])
        require(contract['source_task_id'] == source['source_task_id'], 'Native Map identity differs')
        extra['community_manifest_family'] = community_manifest_family(contract)
    return json.dumps(dict(profile=profile, **extra, **{k: plan[k] for k in
        ('root', 'capsule', 'source_binding_catalog', 'native_source_adapter', 'generator_settings')}), sort_keys=True)


def compatible_remaining(state, first):
    key = batch_key(first)
    if key is None:
        return set()
    queue = read(state['queue']); ready = set(queue['ready_source_ids'])
    result = set()
    for item in queue['sources']:
        sid = item['source_task_id']
        if sid not in ready or sid in state['sources'] or item['domain'] != 'map':
            continue
        if batch_key(item) == key:
            result.add(sid)
        if len(result) == 3:
            break
    return result


def prepare_map_release(items, directory, state, key_file, template_ref):
    """One shared execution, original per-source authorization and offline export."""
    require(state['pilot_passed'] and 2 <= len(items) <= 4, 'Passed pilot and bounded Map batch required')
    keys = [batch_key(item) for item in items]
    require(keys[0] is not None and len(set(keys)) == 1, 'Map batch sources are incompatible')
    template = read(template_ref); extension = template['map_batch']
    require(extension['version'] == 'formal-map-batch-template-v1', 'Unknown Map batch template')
    pilots = [r['export_summary'] for r in state['sources'].values() if r['status'] == 'complete'
              and read(read(r['export_summary'])['audit'])[0]['teacher_requests']]
    require(pilots, 'Audited real Teacher pilot required')
    batch_dir = Path(directory)/'map-batches'/items[0]['source_task_id']
    batch_dir.mkdir(parents=True, exist_ok=False)
    paths = dict(workflow_path=str(batch_dir/'workflow.json'), submission_path=str(batch_dir/'submission.json'))
    shared_template = deepcopy(template)
    shared_template['launch'].update(bootstrap_source=extension['bootstrap_source'],
                                     dispatch_source=extension['dispatch_source'])
    for stage in shared_template['workflow']['stages']:
        stage['script'] = extension['script']
    shared_ref = write_new(batch_dir/'source-template.json', shared_template)
    releases = {}
    for item in items:
        sid = item['source_task_id']; allowance = state['sources'][sid]['allowance_usd']
        releases[sid] = prepare_release(item, Path(directory)/'sources'/sid, allowance,
            state['authorization'], key_file, shared_ref, shared_workflow=paths)
    launches = [r['launch'] for r in releases.values()]
    launch_values = [read(ref) for ref in launches]
    seconds = sum(v['source_seconds'] for v in launch_values)
    require(all(type(v['source_seconds']) is int and 0 < v['source_seconds'] <= 7200 for v in launch_values),
            'Existing bounded source deadlines required')
    batch = dict(version='formal-map-batch-launch-v1', source_launches=launches,
        batch_authorization=state['authorization'], pilot_export=pilots[0],
        bootstrap_source=extension['bootstrap_source'], dispatch_source=extension['dispatch_source'],
        credential_file=str(key_file), encoding_cache_directory=launch_values[0]['encoding_cache_directory'],
        scratch_minimum_bytes=max(v['scratch_minimum_bytes'] for v in launch_values),
        stage_id='map_batch', result_directory=str(batch_dir/'execution'), **paths)
    bref = write_new(batch_dir/'batch-launch.json', batch)
    source_stage = deepcopy(next(iter(releases.values()))['stages'][0])
    source_stage['args'] = ['execute_map_batch', bref['path'], bref['sha256'],
                           extension['bootstrap_source']['sha256'], extension['dispatch_source']['sha256']]
    inputs = [bref, template_ref, *launches]
    scopes = [batch['result_directory']]
    exports = []
    for value in releases.values():
        inputs.extend(value['stages'][0]['inputs'])
        scopes.extend(value['stages'][0]['exclusive_scopes'])
        exports.append(value['stages'][1])
    source_stage.update(inputs=list({r['path']:r for r in inputs}.values()),
        exclusive_scopes=list(dict.fromkeys(scopes)), output=str(batch_dir/'source-%j.log'))
    allocation = seconds+1800
    source_stage['resources']['time'] = f'{allocation//3600:02d}:{allocation%3600//60:02d}:{allocation%60:02d}'
    wref = write_new(batch_dir/'workflow.json', dict(version='stage-submission-v2', stages=[source_stage,*exports]))
    for sid, value in releases.items():
        value.pop('stages')
        value.update(workflow=wref, submission_path=paths['submission_path'],
                     relevant_stage_ids=['map_batch', 'export_'+sid], batch_launch=bref)
    return releases
