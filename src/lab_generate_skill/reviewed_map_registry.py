"""Load reviewed Map families into one current runtime, never old code packets.

Manifest entries select only these built-in catalog/adapter pairs. Every catalog
retains its original full evidence and tested-code checks. Registration is all
or nothing; a changed dependency must be validated before it can be published.
"""
from collections import defaultdict
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path

from .provider_review_catalog import identity
from .reviewed_protocol_bundle import ReviewedProtocolBundle
from . import native_goal_dispatch as dispatch


FAMILIES = {
    'eiffel_search_v191': ('map_eiffel_v191.catalog', 'EiffelCatalog', 'map_eiffel_v191.bridge', 'EiffelAdapter'),
    'remaining_four_v191': ('map_final_v191.route_catalog', 'RouteCatalog', 'map_final_v191.bridge', 'RouteAdapter'),
    'saved_node_edit_v191': ('map_final_v191.edit_catalog', 'EditCatalog', 'map_final_v191.bridge', 'EditAdapter'),
    'gps_document_v190': ('map_scope_v190.catalog', 'GPSCatalog', 'map_scope_v190.adapter', 'GPSAdapter'),
    'public_overlays_v190': ('map_scope_v190.catalog', 'LayerCatalog', 'map_scope_v190.adapter', 'LayerAdapter'),
    'website_offered_routes_v189': ('map_offered_route_v189.catalog', 'OfferedRouteCatalog', 'map_offered_route_v189.adapter', 'AdmittedScopeRouteAdapter'),
    'reader_diaries_v187': ('map_reader_v187.catalog', 'ReaderCatalog', 'map_reader_v187.adapter', 'ReaderAdapter'),
    'saved_content_v187': ('map_saved_content_v187.catalog', 'SaveCatalog', 'map_saved_content_v187.adapter', 'SaveAdapter'),
    'registration_confirm_v183': ('registration_v183.registration_actor', 'RegistrationCatalog', 'registration_v183.registration_actor', 'RegistrationAdapter'),
    'route_device_location': ('route_location_catalog', 'RouteLocationCatalog', 'route_location_actor_adapter', 'RouteLocationAdapter'),
    'remaining_surfaces': ('remaining_surface_catalog', 'RemainingSurfaceCatalog', 'remaining_surface_actor_adapter', 'RemainingSurfaceAdapter'),
    'remaining_routes': ('remaining_route_catalog', 'RemainingRouteCatalog', 'remaining_route_actor_adapter', 'RemainingRouteAdapter'),
    'source_account_signup': ('map_account2_catalog', 'Account2Catalog', 'frozen_signup_document_adapter', 'FrozenSignupDocumentAdapter'),
    'source_account_login': ('map_account2_catalog', 'Account2Catalog', 'frozen_existing_account_actor_adapter', 'FrozenExistingAccountActorAdapter'),
    'provider_source_cycles': ('source_cycle_provider_catalog', 'SourceCycleProviderCatalog', 'frozen_provider_actor_adapter', 'FrozenProviderActorAdapter'),
    'initial_link': ('initial_link_review_catalog', 'InitialLinkReviewCatalog', 'frozen_initial_link_actor_adapter', 'FrozenInitialLinkActorAdapter'),
    'node': ('node_review_catalog', 'NodeReviewCatalog', 'frozen_node_actor_adapter', 'FrozenNodeActorAdapter'),
    'ordered_export': ('ordered_export_review_catalog', 'OrderedExportReviewCatalog', 'frozen_ordered_export_actor_adapter', 'FrozenOrderedExportActorAdapter'),
    'route_image': ('route_image_review_catalog', 'RouteImageReviewCatalog', 'frozen_route_image_actor_adapter', 'FrozenRouteImageActorAdapter'),
    'route_output': ('route_output_review_catalog', 'RouteOutputReviewCatalog', 'frozen_route_output_actor_adapter', 'FrozenRouteOutputActorAdapter'),
    'gps': ('gps_review_catalog', 'GPSReviewCatalog', 'frozen_gps_actor_adapter', 'FrozenGPSActorAdapter'),
    'comparison': ('comparison_review_catalog', 'ComparisonReviewCatalog', 'frozen_provider_actor_adapter', 'FrozenProviderActorAdapter'),
    'pdf': ('pdf_review_catalog', 'PdfReviewCatalog', 'frozen_raster_actor_adapter', 'FrozenRasterActorAdapter'),
    'raster': ('raster_review_catalog', 'RasterReviewCatalog', 'frozen_raster_actor_adapter', 'FrozenRasterActorAdapter'),
    'share': ('share_review_catalog', 'ShareReviewCatalog', 'frozen_share_actor_adapter', 'FrozenShareActorAdapter'),
    'short_route': ('short_route_review_catalog', 'ShortRouteReviewCatalog', 'frozen_short_route_actor_adapter', 'FrozenShortRouteActorAdapter'),
    'route': ('route_review_catalog', 'RouteReviewCatalog', 'frozen_route_actor_adapter', 'FrozenRouteActorAdapter'),
    'route_state': ('route_state_reuse_catalog', 'RouteStateReuseCatalog', 'frozen_route_actor_adapter', 'FrozenRouteActorAdapter'),
    'provider': ('provider_review_catalog', 'ProviderReviewCatalog', 'frozen_provider_actor_adapter', 'FrozenProviderActorAdapter'),
    'account': ('account_review_catalog', 'AccountReviewCatalog', 'frozen_account_actor_adapter', 'FrozenAccountActorAdapter'),
    'existing_account': ('existing_account_review_catalog', 'ExistingAccountReviewCatalog', 'frozen_existing_account_actor_adapter', 'FrozenExistingAccountActorAdapter'),
}


class ReviewedMapRegistry:
    def __init__(self, manifest, expected_sha256, *, project, selected_sources=None):
        self.project = Path(project).resolve()
        self.files = {}; self.catalogs = []; self.registered = []
        self.sources = {}; self.descriptors = {}; self.profiles = {}
        self.closed = False
        self.retained = None
        try:
            config = json.loads(self.read(manifest, expected_sha256))
            if config.get('version') != 'reviewed-map-registry-v1' or not (config.get('entries') or config.get('retained_native_sources')):
                raise ValueError('Explicit reviewed Map registry required')
            pins = config.get('runtime_files', {})
            for required in ('src/lab_generate_skill/reviewed_map_registry.py',
                             'src/lab_generate_skill/reviewed_protocol_bundle.py',
                             'src/lab_generate_skill/native_goal_dispatch.py',
                             'scripts/run_site_navigation_once.py'):
                if required not in pins:
                    raise ValueError('Registry and ordinary runner code must be pinned')
            for name, digest in pins.items():
                path = self.project / name
                if Path(name).is_absolute() or '..' in Path(name).parts or path.is_symlink():
                    raise ValueError('Regular project-relative runtime member required')
                self.read(path, digest)
            groups = defaultdict(list)
            for entry in config.get('entries', []):
                kind = entry['kind']
                if kind not in FAMILIES:
                    raise ValueError('Unregistered Map family')
                proof = entry['proof_config']
                proof_config = json.loads(self.read(proof['path'], proof['sha256']))
                cm, cn, am, an = FAMILIES[kind]
                catalog_class = getattr(importlib.import_module('lab_generate_skill.' + cm), cn)
                adapter_class = getattr(importlib.import_module('lab_generate_skill.' + am), an)
                if any(k in proof_config for k in ('_code_evolution', '_evidence_snapshots')):
                    raise ValueError('Code evolution must be declared by current registry')
                if entry.get('code_evolution') is not None:
                    required={'src/lab_generate_skill/'+n+'.py' for n in (
                        'reviewed_code_evolution','provider_review_catalog',
                        'route_review_catalog','pdf_review_catalog')}
                    if not required <= pins.keys():
                        raise ValueError('Code-evolution verification implementations must be pinned')
                    evolution = deepcopy(entry['code_evolution'])
                    evolution.update(project=str(self.project),source_ids=list(entry['source_ids']))
                    proof_config['_code_evolution'] = evolution
                if entry.get('evidence_snapshots') is not None:
                    required = {'src/lab_generate_skill/'+n+'.py' for n in (
                        'reviewed_evidence_snapshot','provider_review_catalog',
                        'route_review_catalog','pdf_review_catalog')}
                    if not required <= pins.keys():
                        raise ValueError('Publication snapshot readers must be pinned')
                    from .reviewed_evidence_snapshot import validate_snapshots
                    validate_snapshots(entry['evidence_snapshots'], self.project)
                    proof_config['_evidence_snapshots'] = deepcopy(entry['evidence_snapshots'])
                if kind == 'remaining_routes':
                    required = {'src/lab_generate_skill/reviewed_execution_binding.py',
                                'src/lab_generate_skill/remaining_route_catalog.py',
                                'src/lab_generate_skill/remaining_route_actor_adapter.py',
                                'scripts/map_readout_answers.py'}
                    required.update('scripts/map_routes/'+name for name in proof_config['execution_binding']['candidate_modules'])
                    if not required <= pins.keys():
                        raise ValueError('Complete remaining-route package must be pinned')
                if kind == 'route_device_location':
                    required = {'src/lab_generate_skill/route_location_catalog.py',
                                'src/lab_generate_skill/route_location_actor_adapter.py',
                                'src/lab_generate_skill/map_location_factory.py',
                                'src/lab_generate_skill/reviewed_execution_binding.py',
                                'src/lab_generate_skill/site_worker.py',
                                'src/lab_generate_skill/website_batch_profile.py',
                                'scripts/map_route_location/contract.json',
                                'scripts/map_route_location/offline-review.json',
                                'scripts/map_route_location/observer-check.js'}
                    required.update('scripts/map_route_location/'+name for name in proof_config['execution_binding']['candidate_modules'])
                    from .route_location_catalog import required_runtime_files
                    required.update(required_runtime_files(self.project))
                    if not required <= pins.keys():
                        raise ValueError('Complete location factory, proof and execution dependencies must be pinned')
                if kind == 'remaining_surfaces':
                    required = {'src/lab_generate_skill/remaining_surface_catalog.py',
                                'src/lab_generate_skill/remaining_surface_actor_adapter.py',
                                'scripts/map_surfaces/contracts.json', 'scripts/map_surfaces/offline-review.json'}
                    if proof_config.get('repaired_phase')is True:required.add('src/lab_generate_skill/repaired_surface_execution.py')
                    binding = proof_config['execution_binding']
                    required.update('scripts/map_surfaces/'+name for name in binding['candidate_modules'])
                    required.update('scripts/map_routes/'+name for name in binding['shared_route_lifecycle']['candidate_modules'])
                    required.update(binding['native_renderer_files'])
                    if not required <= pins.keys():
                        raise ValueError('Complete remaining-surface package and renderer must be pinned')
                catalog = catalog_class(proof_config, project=self.project)
                self.catalogs.append(catalog)
                adapter = adapter_class(resolve_proof=catalog.resolve)
                selected = entry['source_ids']
                if not selected or len(set(selected)) != len(selected):
                    raise ValueError('Distinct selected sources required')
                rows = []
                for sid in selected:
                    if sid in self.sources or sid not in catalog.sources:
                        raise ValueError('Duplicate or unverified registry source')
                    row = deepcopy(catalog.sources[sid]['candidate'])
                    descriptor = deepcopy(catalog.descriptors[sid])
                    if kind == 'public_overlays_v190':
                        # Keep the exact executed candidate schema. Its training
                        # split is checked against pinned original source records.
                        if catalog.sources[sid].get('training_source_verified') is not True:
                            raise ValueError('Reviewed overlay training source proof required')
                    elif row.get('split') != 'train' or row.get('heldout_quarantine'):
                        raise ValueError('Registry sources must remain in training scope')
                    if row.get('browser_capabilities', {}).get('print_to_pdf') is True:
                        required = {'src/lab_generate_skill/'+n+'.py' for n in (
                            'actor_capability_preflight','actor_protocol','constrained_actions')}
                        if not required <= pins.keys():
                            raise ValueError('Print actor capability implementations must be pinned')
                        from .actor_capability_preflight import require_capabilities
                        require_capabilities(row)
                    adapter.require_admission(row, descriptor)
                    self.sources[sid] = row; self.descriptors[sid] = descriptor
                    extra = ['--map-instances', '1']
                    if kind in ('share', 'short_route'):
                        extra.append('--map-share-observer')
                    if kind in ('provider','provider_source_cycles','comparison','gps','ordered_export'):
                        extra.extend(['--map-native-provider-manifest', catalog.config['profile']['path']])
                    if kind == 'gps_document_v190':
                        extra.extend(['--map-native-provider-manifest', catalog.config['profile']['path']])
                    if kind in ('remaining_routes','remaining_four_v191','eiffel_search_v191') and catalog.config.get('asset_manifest') is not None:
                        extra.extend(['--map-native-asset-manifest', catalog.config['asset_manifest']['path']])
                    if kind == 'remaining_surfaces':
                        if row['surface']['kind'] not in ('initial_png', 'named_png'):
                            extra.append('--map-share-observer')
                        if catalog.config.get('asset_manifest') is not None:
                            extra.extend(['--map-native-asset-manifest', catalog.config['asset_manifest']['path']])
                    self.profiles[sid] = tuple(extra)
                    rows.append(row)
                key = (getattr(adapter, 'AUTHORIZED_TARGET_WRITES', False),
                       getattr(adapter, 'OWNS_NATIVE_CSV_TRANSPORT', False))
                groups[key].append((adapter, rows))
            retained = config.get('retained_native_sources')
            if retained is not None:
                required = {'src/lab_generate_skill/'+name+'.py' for name in (
                    'retained_map_source_context','original_map_proof_archive','original_map_proof_glob',
                    'map_native_layer_runtime','map_history_layer_runtime','map_history_layer_normal',
                    'history_layer_hooks','history_layer_replay','map_local_view_facts',
                    'map_native_facts_runtime','map_native_facts_normal','map_named_facts_binding',
                    'map_identity_policy_scope','map_local_coverage_goal_revision','map_export_normal',
                    'map_export_runtime','map_native_route_runtime','current_actor_entry','current_actor_submission')}
                if not required <= pins.keys():
                    raise ValueError('Complete retained Map lifecycle code must be pinned')
                chosen = list(retained['source_ids'])
                if selected_sources is not None:
                    chosen = [sid for sid in chosen if sid in selected_sources]
                if chosen:
                    from .retained_map_source_context import RetainedMapSourceContext
                    settings = deepcopy(retained); settings['source_ids'] = chosen
                    self.retained = RetainedMapSourceContext(settings, read_pinned=self.read)
                    if self.sources.keys() & self.retained.sources.keys():
                        raise ValueError('Duplicate reviewed and retained Map sources')
                    self.sources.update(self.retained.sources)
                    self.descriptors.update(self.retained.descriptors)
                    self.profiles.update({sid:('--map-instances','1')for sid in chosen})
            # Build everything before registering any protocol. Existing global
            # protocols cannot be replaced; registration failures roll back ours.
            bundles = [ReviewedProtocolBundle(value) for value in groups.values()]
            for number, bundle in enumerate(bundles):
                name = 'current_reviewed_map_' + str(number)
                dispatch.register_protocol(name, bundle)
                self.registered.append((name, bundle))
            self.require_current()
        except BaseException:
            self.close()
            raise

    def read(self, path, digest):
        path = Path(path)
        if not path.is_absolute():
            raise ValueError('Absolute registry evidence required')
        before = identity(path); raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest or identity(path) != before:
            raise ValueError('Registry evidence changed: ' + str(path))
        self.files[path] = before
        return raw

    def require_current(self):
        if self.closed or any(identity(p) != value for p, value in self.files.items()):
            raise ValueError('Current registry changed or closed')
        if self.retained is not None and self.retained.closed:
            raise ValueError('Retained Map proof scope is closed')
        for catalog in self.catalogs:
            catalog.require_current()

    def partition(self, contracts):
        """Plan compatible batches before allocating a model or website."""
        from .website_batch_profile import partition
        self.require_current()
        startup_groups = {}
        for row in contracts:
            sid = row.get('source_task_id')
            if {k:v for k,v in row.items() if k != 'admission_result'} != self.sources.get(sid):
                raise ValueError('Batch task differs from registered source')
            startup_groups.setdefault(self.profiles[sid], []).append(deepcopy(row))
        groups = []
        for arguments, rows in startup_groups.items():
            for group in partition(rows, 'map'):
                groups.append(dict(rows=group['rows'], profile=group['profile'],
                                   runner_arguments=list(arguments)))
        return groups

    def runner(self, argv=None, **kwargs):
        import argparse
        self.require_current()
        argv = list(argv or [])
        reserved = ('--map-instances', '--map-share-observer', '--map-native-provider-manifest',
                    '--map-native-asset-manifest', '--map-native-frontend-manifest')
        if any(a.split('=', 1)[0] in reserved for a in argv):
            raise ValueError('Reviewed startup settings must not be overridden')
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument('--manifest', type=Path, required=True)
        args, _ = parser.parse_known_args(argv)
        rows = [json.loads(line) for line in args.manifest.read_text().splitlines()]
        if not rows:
            raise ValueError('Nonempty reviewed manifest required')
        profiles = set()
        for row in rows:
            sid = row.get('source_task_id')
            if {k:v for k,v in row.items() if k != 'admission_result'} != self.sources.get(sid):
                raise ValueError('Manifest differs from registered source')
            profiles.add(self.profiles[sid])
        if len(profiles) != 1:
            raise ValueError('Partition incompatible website startup profiles before execution')
        from .website_batch_profile import profile
        profile(rows, 'map')  # Retains account/short-route separation as well.
        runner = importlib.import_module('run_site_navigation_once')
        if Path(runner.__file__).resolve() != self.project/'scripts/run_site_navigation_once.py':
            raise ValueError('Only the registered current ordinary runner is allowed')
        return runner.main(argv + list(profiles.pop()), runtime_project=self.project, **kwargs)

    def close(self):
        for name, bundle in reversed(self.registered):
            dispatch.unregister_protocol(name, bundle)
        self.registered.clear()
        for catalog in self.catalogs:
            catalog.close()
        self.catalogs.clear()
        if self.retained is not None:
            self.retained.close(); self.retained = None
        self.closed = True

    def __enter__(self):
        self.require_current()
        return self

    def __exit__(self, *_):
        self.close()
