"""Bind independently reviewed source cycles without inventing whole-batch runs."""
from copy import deepcopy
import json
from pathlib import Path

from .provider_review_catalog import ProviderReviewCatalog, digest
from .source_revision_binding import binding


RUNTIME_MEMBERS = tuple('src/lab_generate_skill/' + n + '.py' for n in (
    'site_worker', 'map_query_site', 'map_reset_guard',
    'map_provider_environment', 'map_provider_observation',
    'map_provider_terminal', 'map_frozen_provider_runtime',
    'map_provider_contract', 'map_provider_resources', 'map_provider_coverage',
    'browser_page_wait', 'gobrowse_runtime', 'actor_protocol',
)) + ('scripts/run_site_navigation_once.py',)


class SourceCycleProviderCatalog(ProviderReviewCatalog):
    def __init__(self, config, *, project):
        self.closed = False
        self.files = {}
        self.sources = {}
        self.descriptors = {}
        self.config = deepcopy(config)
        if config.get('version') != 'source-cycle-provider-proof-v1':
            raise ValueError('Explicit source-cycle provider evidence required')
        profile = self.read(config['profile'])
        contracts = self.read(config['contracts'])['tasks']
        combined = self.read(config['review'])
        retained = self.read(combined['retained_review'])
        if (profile['contracts'] != config['contracts']
                or profile.get('runtime_external_requests') is not False
                or profile.get('original_snapshot_equivalence') is not False
                or profile.get('version') != 'map-frozen-provider-environment-v1'
                or combined.get('passed') is not True
                or retained.get('passed') is not True
                or combined.get('all_native_cases_passed') is not True
                or combined.get('missing_cold_controls') != []):
            raise ValueError('Complete reviewed local provider evidence required')
        self.read(profile['resources'])
        # Bind the actual test plans and tested runtime. Private control scripts
        # can differ by cycle; they are not injected into Actor decisions.
        for proof in (combined, retained):
            submission = self.read(proof['actual_submission'])
            plan = self.read(submission['plan'])
            if (plan['profile'] != config['profile']
                    or config['contracts'] not in plan['inputs']):
                raise ValueError('Tested provider profile differs')
            capsule_ref = config['tested_capsules'].get(submission['job_id'])
            if capsule_ref is None:
                raise ValueError('Missing tested runtime capsule')
            capsule = self.read(capsule_ref)
            for name in RUNTIME_MEMBERS:
                tested = plan.get('helper_overlays', {}).get(name)
                expected = tested['sha256'] if tested else capsule['members'][name]['sha256']
                self.read(dict(path=str(Path(project) / name), sha256=expected), json_value=False)
        # Every selected cycle must be an actual reviewed successful record.
        all_records = retained['records'] + combined['records']
        cycles = combined['selected_verified_cycles']
        workers = retained['workers'] + combined['workers']
        ids = {c['source_task_id'] for c in contracts}
        if (len(ids) != len(contracts) or not ids
                or {r['source_task_id'] for r in cycles} != ids):
            raise ValueError('Provider source coverage differs')
        self.environment_binding = dict(version=profile['version'],
            manifest_sha256=config['profile']['sha256'],
            resources_sha256=profile['resources']['sha256'],
            contracts_sha256=config['contracts']['sha256'])
        baselines = {w['baseline'] for w in workers}
        if len(baselines) != 1:
            raise ValueError('Provider cold baselines differ')
        self.baseline = baselines.pop()
        for candidate in contracts:
            sid = candidate['source_task_id']
            binding(candidate)
            if (candidate.get('split') != 'train' or candidate.get('heldout_quarantine')
                    or candidate['candidate_completion']['family'] != 'base_layer'):
                raise ValueError('Explicit training provider task required')
            selected = [r for r in cycles if r['source_task_id'] == sid]
            if len(selected) != 2 or any(r not in all_records for r in selected):
                raise ValueError('Two original reviewed source cycles required')
            factories = set()
            for cycle in selected:
                matches = [w for w in workers if w['archive'] == cycle['archive']
                           and w['worker'] == cycle['worker']]
                if (len(matches) != 1 or cycle.get('passed') is not True
                        or cycle.get('full_reset_verified') is not True
                        or cycle.get('native_control_cases') != 5
                        or cycle.get('ordinary_control_cases') != 3
                        or matches[0].get('reset_and_cleanup_verified') is not True):
                    raise ValueError('Incomplete native/ordinary lifecycle controls')
                factories.add(matches[0]['factory_id'])
            if len(factories) != 2:
                raise ValueError('Repeated cycles in one factory are not independent cold starts')
            descriptor = dict(version='reviewed-provider-source-cycles-v1', source_task_id=sid,
                candidate_sha256=digest(json.dumps(candidate, sort_keys=True, separators=(',', ':')).encode()),
                review_sha256=config['review']['sha256'], profile_sha256=config['profile']['sha256'])
            admission = dict(version='native-provider-normal-admission-v1', passed=True,
                two_cold_environment_verified=True, ordinary_lifecycle_verified=True,
                source_task_id=sid, environment_binding=self.environment_binding,
                baseline=self.baseline, verified_review_reused=True,
                reviewed_cycles=deepcopy(selected))
            self.sources[sid] = dict(candidate=deepcopy(candidate), admission=admission,
                environment_binding=self.environment_binding, baseline=self.baseline)
            self.descriptors[sid] = descriptor
        self.require_current()
