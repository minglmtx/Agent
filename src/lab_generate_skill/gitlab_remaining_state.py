"""Native callback port; source controls and scoring preserved."""
import hashlib

import json

from pathlib import Path

class Hooks:

    def prepare(self, site, username):
        if self.prepared or site.domain != 'gitlab':
            raise ValueError('One native source preparation required')
        import gitlab_native_wiki_cache_init as cache
        from lab_generate_skill.gitlab_native_read_runtime import full_snapshot
        from lab_generate_skill.gitlab_persisted_goal_runtime import refs_snapshot
        from lab_generate_skill.gitlab_native_csv_probe import auth_backup
        if self.contract.get('gitlab_cache_initialization') != getattr(site, 'initialization_profile', None):
            raise ValueError('Actual native cache profile differs from the admitted contract')
        self.cold, self.before, self.effects = initialize_baseline(site, self.directory / 'cache-initialization')
        full_snapshot(self.cold)
        full_snapshot(self.before)
        self.refs_before = refs_snapshot(site)
        if self.expected_baseline is not None and (self.cold, self.before, self.refs_before) != self.expected_baseline:
            raise ValueError('Fresh complete native initialization/ref baseline differs from admitted proof')
        self.auth = auth_backup(site, username)
        self.site = site
        self.prepared = True
        self.events.append('prepare')
        if self.contract['existing_shared_kind'] == 'repository_file':
            from lab_generate_skill.gitlab_mutation_native import protection
            self.mutation_before = protection(site, self.private['spec'], self.private['account_id'], self.directory / 'mutation-before-progress.jsonl')
            import gitlab_project_column_hashes as columns
            self.columns_before = columns.snapshot(site)
        else:
            self.mutation_before = None

    def attach(self, context):
        if not self.prepared or self.context is not None:
            raise ValueError('One prepared actual browser context required')
        self.context = context
        self.events.append('attach')

    def observe_initial(self, page):
        page_lifetime.live_page(self, page, initial=True)
        if page.context is not self.context or self.initial_page is not None or page.url != self.site.url + self.contract['start_path']:
            raise ValueError('Actual original or declared initial page required')
        self.initial_page = page
        self.events.append('observe_initial')

    def record(self, page):
        page_lifetime.live_page(self, page)
        self.events.append('record')

    def close(self):
        self.closed = True

def _read(path):
    return json.loads(Path(path).read_text())

def _artifact_file(folder, name):
    folder = Path(folder).resolve()
    p = folder / name
    if not p.is_file() or p.is_symlink() or folder not in p.resolve().parents:
        raise ValueError('Original private evidence file required: ' + name)
    return p

def initialize_baseline(site, directory):
    from lab_generate_skill.gitlab_prepared_cache_proof import reuse_sequence
    prepared = reuse_sequence(site, directory)
    if prepared is not None:
        return prepared
    import gitlab_native_wiki_cache_init as wiki
    import gitlab_native_issue_cache_init as issue
    phases = []
    first = previous = None
    for name, module in (('wiki', wiki), ('issue', issue)):
        cold, after, effects = module.initialize(site, Path(directory) / name)
        if first is None:
            first = cold
        if previous is not None and cold != previous:
            raise ValueError('Complete native initialization chain changed between collectors')
        phases.append({'name': name, 'cold': cold, 'after': after, 'effects': effects})
        previous = after
    return (first, previous, phases)

def verify_initialization(directory, row):
    prepared = Path(directory) / 'cache-initialization' / 'prepared-sequence.json'
    if prepared.exists():
        from lab_generate_skill.gitlab_prepared_cache_proof import verify_reuse
        return verify_reuse(prepared, row)
    import gitlab_native_wiki_cache_init as wiki
    import gitlab_native_issue_cache_init as issue
    from lab_generate_skill.gitlab_native_read_runtime import full_snapshot
    phases = row['native_initialization_effects']
    if not isinstance(phases, list) or [v.get('name') for v in phases] != ['wiki', 'issue']:
        raise ValueError('Complete exact native initialization sequence required')
    previous = row['native_before_initialization']
    for phase, module, marker in zip(phases, (wiki, issue), ('WIKI', 'ISSUE')):
        folder = Path(directory) / 'cache-initialization' / phase['name']
        full_snapshot(phase['cold'])
        full_snapshot(phase['after'])
        if phase['cold'] != previous:
            raise ValueError('Original complete initialization chain differs')
        invocation = _read(_artifact_file(folder, 'native-cache-initialization.json'))
        if invocation.get('command_returncode') != 0 or invocation.get('stdout_native_begin_markers') != 1 or invocation.get('stdout_native_end_markers') != 1 or (invocation.get('rails_global_new_help_detected') is not False) or (invocation.get('application_entrypoint') != module.APPLICATION_ENTRYPOINT) or (invocation.get('ruby_sha256') != hashlib.sha256(Path(module.__file__).with_suffix('.rb').read_bytes()).hexdigest()):
            raise ValueError('Actual successful pinned native initialization command required')
        record = module.parse_result('LAB_NATIVE_' + marker + '_CACHE_INIT_BEGIN\n' + json.dumps(invocation['native_record']) + '\nLAB_NATIVE_' + marker + '_CACHE_INIT_END')
        capture = _read(_artifact_file(folder, 'native-cache-initialization-capture.json'))
        if capture.get('status') != 'captured' or capture.get('capture_errors') or capture.get('primary_exception_type') or (capture.get('native_record_complete') is not True) or (capture.get('actor_attempts') != 0) or (capture.get('api_calls') != 0) or (capture['full_before'] != phase['cold']) or (capture['full_after'] != phase['after']):
            raise ValueError('Original complete cold initialization capture differs')
        columns_before = _read(_artifact_file(folder, 'columns-before-native-initialization.json'))
        columns_after = _read(_artifact_file(folder, 'columns-after-native-initialization.json'))
        for by_columns, raw in ((columns_before, phase['cold']), (columns_after, phase['after'])):
            if by_columns['row_count'] != raw['projects']['rows'] or by_columns['columns'] != raw['projects']['columns']:
                raise ValueError('Every native project column/row must be included')
        effects = module.verify_effects(columns_before, columns_after, phase['cold'], phase['after'], record)
        if effects != phase['effects'] or effects != _read(_artifact_file(folder, 'native-cache-effect-verification.json')):
            raise ValueError('Exact native initialization effects differ')
        previous = phase['after']
    if previous != row['protected_before']:
        raise ValueError('Complete final initialized baseline differs')
    return phases

from . import native_artifact_page_lifetime as page_lifetime
