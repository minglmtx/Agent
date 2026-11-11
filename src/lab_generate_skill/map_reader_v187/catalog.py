"""Exact source admission over two sealed, independently reviewed native batches."""
from pathlib import Path, PurePosixPath
from copy import deepcopy
from io import BytesIO
import hashlib, json, tarfile
from lab_generate_skill.provider_review_catalog import identity
from .adapter import materialize
from .evidence import replay

PACKAGE = 'src/lab_generate_skill/map_reader_v187/'
QUALIFIED = ('__init__.py', 'rss_client.py', 'reader_ui.py', 'reader_site.py',
    'pipelined_site.py', 'diary_read.py', 'profile.py', 'hooks.py', 'public-environment.json')
CORE = ('map_account_initial', 'map_account_readout', 'map_existing_account_observation',
    'map_existing_account_site', 'map_account_profile', 'map_query_site', 'map_reset_guard',
    'browser_http_status', 'site_worker', 'website_batch_profile', 'native_goal_dispatch',
    'gobrowse_runtime', 'browser_assets', 'actor_protocol', 'runtime_profile',
    'observation_budget', 'public_read_memory', 'reviewed_protocol_bundle')


class ReaderCatalog:
    def __init__(self, config, *, project):
        self.config, self.project = deepcopy(config), Path(project)
        self.files, self.sources, self.descriptors = {}, {}, {}
        self.closed = False
        if config.get('version') != 'native-reader-diaries-catalog-v188':
            raise ValueError('Explicit native reader/diary catalog required')
        from lab_generate_skill.saved_reader_scope_review import specification, verify
        revision = specification(self, config, 'reader')
        contracts, inventory = self.read(config['contracts']), self.read(config['inventory'])
        inventory = {row['task_id']: row for row in inventory}
        baseline = self.read(config['baseline'])
        native, ordinary = self.read(config['native_review']), self.read(config['ordinary_review'])
        if native.get('passed') is not True or ordinary.get('passed') is not True or len(native['cases']) != 9 or len(ordinary['cases']) != 2:
            raise ValueError('Nine native and two ordinary independent controls required')
        if ordinary['native_control_qualification'] != config['native_review']:
            raise ValueError('Ordinary/native qualification chain differs')
        for ref in config['independent_reader_plans']:
            reader = self.read(ref)
            if reader.get('actor_calls') != 0 or reader.get('model_loads') != 0:
                raise ValueError('Independent qualification must be model-free')
        capsule = self.read(config['ordinary_capsule'])
        required = [PACKAGE + n for n in QUALIFIED] + ['scripts/run_site_navigation_once.py']
        required += ['src/lab_generate_skill/' + n + '.py' for n in CORE]
        for relative in required:
            expected = capsule['members'][relative]['sha256']
            if relative in revision['qualified_component_revisions']:
                change = revision['qualified_component_revisions'][relative]
                if change['old_sha256'] != expected:
                    raise ValueError('Scope revision belongs to another qualified component')
            else:
                self.read(dict(path=str(self.project / relative), sha256=expected), json_value=False)
        integration = {PACKAGE + n for n in ('adapter.py', 'catalog.py', 'evidence.py')}
        integration.update({'src/lab_generate_skill/reviewed_map_registry.py', 'src/lab_generate_skill/saved_reader_scope_review.py', PACKAGE + 'input_rejection.py'})
        if set(config['integration_files']) != integration:
            raise ValueError('Complete exact reader source integration required')
        for relative, digest in config['integration_files'].items():
            self.read(dict(path=str(self.project / relative), sha256=digest), json_value=False)
        if set(config['batches']) != {'native', 'ordinary'}:
            raise ValueError('Both original closed evidence batches required')
        archives, reports = {}, {}
        for name, spec in config['batches'].items():
            plan, completed, term = self.read(spec['plan']), self.read(spec['completed']), self.read(spec['termination'])
            if completed['returncode'] != 0 or term['returncode'] != 0 or not term['confirmed'] or term['group'].get('live_members') or term['scope']['live_scratch_references'] or term['scope']['unreadable_same_uid_pids']:
                raise ValueError('Native evidence writer has not closed successfully')
            review = native if name == 'native' else ordinary
            if review['archive'] != spec['archive'] or review['index'] != spec['index'] or review['plan'] != spec['plan']:
                raise ValueError('Independent review belongs to another native batch')
            if name == 'ordinary' and plan['capsule'] != config['ordinary_capsule']:
                raise ValueError('Ordinary controls used another runtime capsule')
            index, raw = self.read(spec['index']), self.read(spec['archive'], json_value=False)
            if index['archive_sha256'] != spec['archive']['sha256']:
                raise ValueError('Closed archive index differs')
            data, size = {}, 0
            with tarfile.open(fileobj=BytesIO(raw)) as archive:
                for member in archive:
                    path = PurePosixPath(member.name)
                    size += member.size
                    if not member.isfile() or path.is_absolute() or '..' in path.parts or member.name in data or member.name not in index['members'] or member.size > 128 * 1024**2 or size > 2 * 1024**3:
                        raise ValueError('Unexpected closed evidence member')
                    value = archive.extractfile(member).read()
                    if index['members'][member.name] != dict(bytes=len(value), sha256=hashlib.sha256(value).hexdigest()):
                        raise ValueError('Closed evidence member changed')
                    data[member.name] = value
            if set(data) != set(index['members']) or len(data) != review['all_members_verified']:
                raise ValueError('Incomplete closed native evidence')
            archives[name], reports[name] = data, self.read(spec['result'])
        result = replay(contracts, archives, baseline, native, ordinary, reports)
        self.scope_scores = verify(self, revision, contracts, baseline)
        for kind, control in contracts.items():
            sid = control['source_task_id']
            initial = self.read(control['original_initial_frame'])
            if initial['source_task_id'] != sid or initial['original_goal'] != control['original_goal'] or initial['original_start_path'] != control['start_path'] or initial['source_trace']['trace_id'] not in inventory[sid]['source_trace_ids']:
                raise ValueError('Audited actual original browser frame differs')
            self.read(control['scope_plan'], json_value=False)
            if kind == 'ny':
                self.read(control['public_fixture'], json_value=False)
            candidate = materialize(control, inventory[sid])
            admission = dict(version='native-reader-diaries-admission-v188', source_task_id=sid,
                passed=result['passed'], native_controls_verified=True, ordinary_lifecycle_verified=True,
                full_cold_reset_verified=True, actual_public_input_verified=True, actor_executed=False, scope_revision_verified=True)
            self.sources[sid] = dict(candidate=candidate, control_contract=control, baseline=baseline, admission=admission)
            self.descriptors[sid] = dict(version='native-reader-diaries-source-v188', source_task_id=sid,
                contract_sha256=hashlib.sha256(json.dumps(candidate, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
                native_review_sha256=config['native_review']['sha256'], ordinary_review_sha256=config['ordinary_review']['sha256'], scope_revision_sha256=config['scope_revision']['sha256'])
        if len(self.sources) != 2:
            raise ValueError('Exactly two independently qualified reader/diary sources required')
        self.require_current()

    def read(self, ref, *, json_value=True):
        path = Path(ref['path'])
        if not path.is_absolute():
            raise ValueError('Absolute pinned evidence path required')
        before, raw = identity(path), path.read_bytes()
        actual = hashlib.sha256(raw).hexdigest()
        if actual != ref['sha256']:
            from lab_generate_skill.reviewed_code_evolution import accepts
            if not accepts(self, ref, path, actual, json_value=json_value):
                raise ValueError('Pinned reader evidence changed: ' + str(path))
        if identity(path) != before:
            raise ValueError('Reader evidence changed during read')
        self.files[path] = before
        return json.loads(raw) if json_value else raw

    def require_current(self):
        if self.closed or any(identity(path) != previous for path, previous in self.files.items()):
            raise ValueError('Reader evidence changed or closed')

    def resolve(self, source_id, descriptor):
        self.require_current()
        if self.descriptors.get(source_id) != descriptor:
            raise ValueError('Exact reader/diary source descriptor required')
        from lab_generate_skill.reviewed_code_evolution import require_source
        require_source(self, source_id)
        return deepcopy(self.sources[source_id])

    def close(self):
        self.closed = True
