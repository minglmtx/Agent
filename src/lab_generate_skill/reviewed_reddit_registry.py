"""Source-bound native Reddit families for the ordinary actor entry.

The trusted publication selects implementations, never task-supplied module
names. Full original proofs are rerun before ordinary constructors are exposed.
Wiki's initialized native baseline and RSS's local client are separate profiles.
"""
from copy import deepcopy
import gzip
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import sys

from . import native_goal_dispatch as dispatch
from .provider_review_catalog import identity
from .reddit_owned_environment import OwnedNativeHooks, ordinary_owner_scope
from .reddit_reviewed_family_adapters import FamilyAdapter
from .source_revision_binding import require_source_binding

VERSION = 'reviewed-original-reddit-registry-v1'
DESCRIPTOR = 'reviewed-original-reddit-source-v1'
FAMILIES = {
    'post_reading': ('reddit_post_reading_runtime', 'PostReadingHooks', False),
    'semantic_read': ('reddit_semantic_normal_candidate', 'SemanticHooks', False),
    'reading_bridge': ('lab_generate_skill.reddit_reading_bridge_runtime', 'ReadingBridgeHooks', False),
    'search_completion': ('lab_generate_skill.reddit_candidate_search_runtime', 'SearchCompletionHooks', True),
    'native_wiki_home': ('native_wiki_runtime', None, False),
    'local_rss': ('reddit_rss_subscription_hooks', 'NativeReadHooks', False),
    'local_read': ('reddit_local_read_hooks', 'NativeReadHooks', False),
    'local_post': ('reddit_local_post_candidate', 'NativeReadHooks', False),
    'media_local_read': ('reddit_local_read_hooks', 'NativeReadHooks', False),
    'media_local_post': ('reddit_local_post_candidate', 'NativeReadHooks', False),
    'local_report': ('reddit_report_runtime', 'OrdinaryHooks', False),
    'parented_reply': ('lab_generate_skill.reddit_parented_reply_runtime', 'ParentedReplyHooks', False),
}

# Mutation permission belongs to a reviewed capability, never to the entire
# registry or to a flag supplied in a task. Existing families retain their
# published policy; adding replies must not authorize writes in reading tasks.
WRITABLE_FAMILIES = frozenset({'parented_reply', 'local_report'})


class _PolicyScope:
    def __init__(self, owner, source_ids, writes):
        self.owner = owner
        self.source_ids = frozenset(source_ids)
        self.AUTHORIZED_TARGET_WRITES = writes
        self.FEEDBACK_VERSIONS = tuple(sorted({
            owner.adapters[sid].PROOF if owner.kinds[sid] == 'native_wiki_home'
            else owner.adapters[sid].module.VERSION for sid in self.source_ids}))

    def enabled(self, contract):
        return contract.get('source_task_id') in self.source_ids

    def _bound(self, contract):
        if not self.enabled(contract):
            raise ValueError('Source is outside this native write-policy scope')
        self.owner.bound(contract)

    def require_admission(self, contract, proof):
        self._bound(contract)
        return self.owner.require_admission(contract, proof)

    def require_original_binding(self, contract, original, inventory):
        self._bound(contract)
        return self.owner.require_original_binding(contract, original, inventory)

    def NativeReadHooks(self, contract, proof, directory):
        self._bound(contract)
        return self.owner.NativeReadHooks(contract, proof, directory)

    def public_goal(self, contract):
        self._bound(contract)
        return self.owner.public_goal(contract)

    def fields(self, contract):
        self._bound(contract)
        return self.owner.fields(contract)

    def feedback(self, judgment):
        if judgment.get('version') not in self.FEEDBACK_VERSIONS:
            raise ValueError('Feedback is outside this native write-policy scope')
        return self.owner.feedback(judgment)


def canonical(contract):
    return {k: v for k, v in contract.items() if k != 'admission_result'}


class ReviewedRedditRegistry:
    AUTHORIZED_TARGET_WRITES = False

    def __init__(self, manifest, expected_sha256, *, project, selected_sources=None):
        self.project = Path(project).resolve()
        self.files, self.loaded, self.sources, self.proofs = {}, {}, {}, {}
        self.adapters, self.kinds, self.initial = {}, {}, {}
        self.owners, self.judgments = [], []
        self.owner_scope = None
        self.media_profile = None
        self.report_profile = None
        self.protocols = []
        self.registered = self.closed = False
        try:
            self.config = json.loads(self.read(manifest, expected_sha256))
            if self.config.get('version') != VERSION:
                raise ValueError('Explicit reviewed native Reddit registry required')
            pins = self.config['runtime_files']
            required = {'src/lab_generate_skill/reviewed_reddit_registry.py',
                        'src/lab_generate_skill/reddit_owned_environment.py',
                        'src/lab_generate_skill/reddit_terminal_failure.py',
                        'src/lab_generate_skill/reddit_reviewed_family_adapters.py',
                        'src/lab_generate_skill/site_worker.py', 'scripts/run_site_navigation_once.py'}
            if not required <= pins.keys():
                raise ValueError('Ordinary owner, runner and native runtime closure required')
            for relative, digest in pins.items():
                path = Path(relative)
                if path.is_absolute() or '..' in path.parts:
                    raise ValueError('Project-relative native executable closure required')
                self.read(self.project/path, digest)
            rows = self.config['sources']
            all_ids = [r['source_task_id'] for r in rows]
            if not all_ids or len(set(all_ids)) != len(all_ids):
                raise ValueError('Distinct retained source records required')
            selected = set(all_ids) if selected_sources is None else set(selected_sources) & set(all_ids)
            if not selected:
                raise ValueError('A selected retained native source is required')
            kinds = {r['kind'] for r in rows if r['source_task_id'] in selected}
            if kinds - FAMILIES.keys():
                raise ValueError('Unsupported native Reddit capability')
            if 'local_report' in kinds:
                names = ('reddit_report_store', 'reddit_report_auth', 'reddit_report_state',
                         'reddit_report_ui', 'reddit_report_lifecycle', 'reddit_report_protocol',
                         'reddit_report_runtime')
                prefix = 'scripts/native_reddit/report/'
                required_report = {prefix + n + '.py' for n in (*names, 'reddit_report_cpu_driver')} | {
                    'src/lab_generate_skill/reddit_report_profile.py',
                    'src/lab_generate_skill/reddit_media_local_profile.py',
                    'src/lab_generate_skill/reddit_submission_snapshot_stream.py',
                    'src/lab_generate_skill/source_revision_binding.py'}
                if not required_report <= pins.keys():
                    raise ValueError('Complete original report lifecycle and owner closure must be pinned')
                for name in names:
                    self.load(name, prefix + name + '.py')
                from .reddit_report_profile import ReportProfile
                self.report_profile = ReportProfile(self)
            if 'parented_reply' in kinds:
                required_reply = {'src/lab_generate_skill/'+name for name in (
                    'reddit_parented_reply.py', 'reddit_parented_reply_runtime.py',
                    'reddit_parented_reply_native.py', 'reddit_parented_reply_native.php',
                    'reddit_fresh_capture_handoff.py', 'source_revision_binding.py',
                    'reddit_search.py')}
                if not required_reply <= pins.keys():
                    raise ValueError('Complete original reply lifecycle must be pinned')
            if kinds & {'post_reading', 'semantic_read'}:
                prefix = 'scripts/native_reddit/reading/'
                required_reading = {prefix + name + '.py' for name in (
                    'reddit_post_reading_candidate', 'reddit_post_reading_controls_v1', 'reddit_post_reading_runtime')} | {
                    'src/lab_generate_skill/reddit_final_read_runtime.py',
                    'src/lab_generate_skill/reddit_remaining_normal.py',
                    'src/lab_generate_skill/reddit_native_read_protection.py',
                    'src/lab_generate_skill/source_revision_binding.py'}
                if not required_reading <= pins.keys():
                    raise ValueError('Complete post-reading lifecycle and predicate must be pinned')
                for name in ('reddit_post_reading_candidate', 'reddit_post_reading_controls_v1', 'reddit_post_reading_runtime'):
                    self.load(name, prefix + name + '.py')
            if 'semantic_read' in kinds:
                prefix = 'scripts/native_reddit/semantic/'
                names = ('reddit_semantic_rules', 'reddit_semantic_native_certificate', 'reddit_semantic_normal_candidate')
                if not {prefix + name + '.py' for name in names} <= pins.keys():
                    raise ValueError('Complete semantic predicate/certificate/ordinary lifecycle closure required')
                for name in names:
                    self.load(name, prefix + name + '.py')
            if kinds & {'media_local_read', 'media_local_post'}:
                from .reddit_media_local_profile import MediaLocalProfile, FILES
                prefix = 'scripts/native_reddit/media_local/'
                required_media = {prefix + n for n in FILES} | {
                    'src/lab_generate_skill/reddit_media_local_profile.py'}
                if not required_media <= pins.keys():
                    raise ValueError('Complete media/local owner closure must be pinned')
                self.media_profile = MediaLocalProfile(self.project / prefix,
                    {n: pins[prefix + n] for n in FILES})
            if 'native_wiki_home' in kinds:
                for name in ('native_wiki_state', 'native_wiki_environment', 'native_wiki_runtime'):
                    self.load(name, 'scripts/native_reddit/wiki/'+name+'.py')
            if kinds & {'local_rss', 'local_read', 'local_post'}:
                for name in ('reddit_public_artifact_candidate', 'reddit_local_service_candidate',
                             'reddit_candidate_ui', 'reddit_native_feed_reference',
                             'reddit_extension_lifecycle'):
                    self.load(name, 'scripts/native_reddit/rss/'+name+'.py')
                for kind in sorted(kinds & {'local_rss', 'local_read', 'local_post'}):
                    name = FAMILIES[kind][0]
                    self.load(name, 'scripts/native_reddit/rss/'+name+'.py')
            for row in rows:
                sid, kind = row['source_task_id'], row['kind']
                if sid not in selected:
                    continue
                raw = self.read(row['record']['path'], row['record']['sha256'])
                record = json.loads(gzip.decompress(raw))
                c, proof = canonical(record['contract']), record['proof']
                if (c.get('source_task_id') != sid or record.get('source_task_id') != sid
                        or c.get('domain') != 'reddit' or c.get('heldout_quarantine') is not False
                        or row.get('split') not in ('train', 'replacement_train')):
                    raise ValueError('Exact nonheldout native source required')
                name, constructor, params = FAMILIES[kind]
                composed = kind in ('media_local_read', 'media_local_post')
                module = (self.media_profile.module(name) if composed
                          else self.loaded.get(name) or importlib.import_module(name))
                expected_file = ('src/'+name.replace('.', '/')+'.py' if name.startswith('lab_generate_skill.')
                    else 'scripts/native_reddit/'+('media_local/' if composed else 'wiki/' if kind == 'native_wiki_home' else 'reading/' if kind == 'post_reading' else 'semantic/' if kind == 'semantic_read' else 'report/' if kind == 'local_report' else 'rss/')+name+'.py')
                if expected_file not in pins or Path(module.__file__).resolve() != self.project/expected_file:
                    raise ValueError('Native implementation is not from this frozen runtime')
                try:
                    self.initial[sid] = module.require_admission(c, proof)
                except ValueError as error:
                    raise ValueError('Native admission for '+sid+': '+str(error)) from error
                if composed and self.initial[sid][2] is None:
                    raise ValueError('Composed media/local family requires its full sidecar proof')
                self.sources[sid], self.kinds[sid] = c, kind
                self.proofs[sid] = ({'version': DESCRIPTOR, 'source_task_id': sid,
                                     'retained_record': deepcopy(row['record'])}, proof)
                self.adapters[sid] = (module if kind == 'native_wiki_home'
                                      else FamilyAdapter(module, constructor, kind in WRITABLE_FAMILIES, params))
            self.FEEDBACK_VERSIONS = tuple(sorted({
                (self.adapters[sid].PROOF if self.kinds[sid] == 'native_wiki_home'
                 else self.adapters[sid].module.VERSION) for sid in self.sources}))
            for writes in (False, True):
                source_ids = [sid for sid in self.sources
                              if (self.kinds[sid] in WRITABLE_FAMILIES) == writes]
                if not source_ids:
                    continue
                scope = _PolicyScope(self, source_ids, writes)
                name = 'current_original_reddit' + ('_writes' if writes else '')
                dispatch.register_protocol(name, scope)
                self.protocols.append((name, scope))
            self.registered = True
        except BaseException:
            self.close()
            raise

    def read(self, path, digest):
        path = Path(path)
        if not path.is_absolute() or path.is_symlink() or not path.is_file():
            raise ValueError('Regular absolute native evidence required')
        before = identity(path)
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest or identity(path) != before:
            raise ValueError('Retained native evidence changed: '+str(path))
        self.files[path] = before
        return raw

    def load(self, name, relative):
        if name in sys.modules or relative not in self.config['runtime_files']:
            raise ValueError('Native module missing from closure or owned by another scope')
        spec = importlib.util.spec_from_file_location(name, self.project/relative)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        self.loaded[name] = module
        spec.loader.exec_module(module)

    def require_current(self):
        if self.closed or any(identity(path) != before for path, before in self.files.items()):
            raise ValueError('Native registry closed or pinned evidence changed')

    def enabled(self, c):
        return c.get('source_task_id') in self.sources

    def bound(self, c):
        self.require_current()
        sid = c.get('source_task_id')
        if canonical(c) != self.sources.get(sid):
            raise ValueError('Task differs from the exact retained native contract')
        return sid

    def require_admission(self, c, descriptor):
        sid = self.bound(c)
        if descriptor != self.proofs[sid][0]:
            raise ValueError('Native source proof locator changed')
        return deepcopy(self.initial[sid])

    def require_original_binding(self, c, original, inventory):
        self.bound(c)
        return require_source_binding(canonical(c), original, inventory, domain='reddit')

    def NativeReadHooks(self, c, descriptor, directory):
        self.require_admission(c, descriptor)
        sid = self.bound(c)
        c, proof = self.sources[sid], self.proofs[sid][1]
        if self.kinds[sid] == 'native_wiki_home':
            return OwnedNativeHooks(c, proof, directory, runtime=self.adapters[sid],
                environment_type=self.loaded['native_wiki_environment'].NativeWikiHomeEnvironment,
                owners=self.owners, judgments=self.judgments)
        return self.adapters[sid].NativeReadHooks(c, proof, directory)

    def public_goal(self, c):
        return self.adapters[self.bound(c)].public_goal(canonical(c))

    def fields(self, c):
        sid = self.bound(c)
        return [] if self.kinds[sid] == 'native_wiki_home' else self.adapters[sid].fields(canonical(c))

    def feedback(self, judgment):
        for sid, adapter in self.adapters.items():
            if self.kinds[sid] != 'native_wiki_home' and judgment.get('version') in adapter.FEEDBACK_VERSIONS:
                return adapter.feedback(judgment)
        raise ValueError('Unknown retained native feedback version')

    def partition(self, contracts):
        from .website_batch_profile import partition
        groups = {}
        for c in contracts:
            sid = self.bound(c)
            # Wiki changes a native baseline; RSS adds an owned local service.
            # Neither may borrow the other capability's website lifetime.
            kind = self.kinds[sid]
            profile = kind if kind in ('native_wiki_home', 'local_rss', 'local_report') else 'native_reading'
            if kind in ('local_read', 'local_post') and self.initial[sid][2] is not None:
                profile = 'local_owned_sidecar'
            if kind in ('media_local_read', 'media_local_post'):
                profile = 'initialized_media_local'
            groups.setdefault(profile, []).append(c)
        return [dict(rows=part['rows'], profile={**part['profile'], 'retained_reddit': key},
                     runner_arguments=[])
                for key, rows in groups.items() for part in partition(rows, 'reddit')]

    def runner(self, argv=None, **kwargs):
        import argparse
        self.require_current()
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument('--manifest', type=Path, required=True)
        args, _ = parser.parse_known_args(argv)
        rows = [json.loads(line) for line in args.manifest.read_text().splitlines() if line.strip()]
        if len(self.partition(rows)) != 1:
            raise ValueError('One isolated native Reddit profile per worker required')
        runner = importlib.import_module('run_site_navigation_once')
        if Path(runner.__file__).resolve() != self.project/'scripts/run_site_navigation_once.py':
            raise ValueError('Current ordinary actor runner required')
        if any(self.kinds[self.bound(c)] == 'local_report' for c in rows):
            holder = kwargs.get('backend_holder')
            with self.report_profile.runner_scope(runner, holder) as scoped_holder:
                scoped = dict(kwargs)
                if holder is not None:
                    scoped['backend_holder'] = scoped_holder
                return runner.main(argv, runtime_project=self.project, **scoped)
        if any(self.kinds[self.bound(c)] in ('media_local_read', 'media_local_post') for c in rows):
            holder = kwargs.get('backend_holder')
            with self.media_profile.runner_scope(runner, holder) as scoped_holder:
                scoped = dict(kwargs)
                if holder is not None:
                    scoped['backend_holder'] = scoped_holder
                return runner.main(argv, runtime_project=self.project, **scoped)
        if not any(self.kinds[self.bound(c)] == 'native_wiki_home' for c in rows):
            return runner.main(argv, runtime_project=self.project, **kwargs)
        from . import site_worker
        holder = kwargs.get('backend_holder')
        if self.owner_scope is None:
            self.owner_scope = ordinary_owner_scope(dispatch, site_worker, runner, self.owners, self.judgments)
            self.owner_scope.__enter__()
        if (holder is not None and getattr(holder, 'sites', None) is not None
                and not isinstance(holder.sites, site_worker.SiteWorker)):
            # A previous homogeneous group may have retained a different site
            # owner. Retire that pool, keeping model weights; never borrow its
            # state or bypass this profile's episode restoration.
            old_sites = holder.sites
            try:
                old_sites.close()
            except BaseException:
                holder.closed = True
                raise
            holder.sites, holder.site_binding = None, None
        # Keep the same scoped factory across adjacent waves, so an existing
        # compatible site can be reused without bypassing episode cleanup.
        return runner.main(argv, runtime_project=self.project, **kwargs)

    def close(self):
        try:
            if self.owner_scope is not None:
                scope, self.owner_scope = self.owner_scope, None
                scope.__exit__(None, None, None)
            else:
                for hook in self.owners:
                    if hook.owner is not None and not hook.finish_owner():
                        raise RuntimeError('Native owner restoration is incomplete')
        finally:
            try:
                if self.media_profile is not None:
                    self.media_profile.close()
            finally:
                try:
                    if self.report_profile is not None:
                        self.report_profile.close()
                finally:
                    self._unregister()

    def _unregister(self):
            for name, scope in reversed(self.protocols):
                dispatch.unregister_protocol(name, scope)
            self.protocols.clear()
            self.registered = False
            for name, module in reversed(list(self.loaded.items())):
                if sys.modules.get(name) is module:
                    sys.modules.pop(name)
            self.loaded.clear()
            self.closed = True

    def __enter__(self):
        self.require_current()
        return self

    def __exit__(self, *args):
        self.close()
