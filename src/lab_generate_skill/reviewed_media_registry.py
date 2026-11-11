"""Current native image-upload family with retained full controls and fixed assets.

No tasks select Python code. The trusted registry pins the shipped implementation,
materials and source proofs. Only an exact, logging-only snapshot-reader evolution
may rebind historical provenance; native judgments and state guards are rerun.
"""
import ast
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
from .source_revision_binding import require_source_binding


def canonical(contract):
    return {k:v for k,v in contract.items() if k != 'admission_result'}


def snapshot_semantics(old, current):
    """Remove only the explicitly reviewed operational logging statements."""
    statements = [
        'from .progress_log import ProgressLog',
        'self.log = ProgressLog(self.output)',
        'if self.output is not None:\n self.output.parent.mkdir(parents=True, exist_ok=True)',
        "if self.output is not None:\n with self.output.open('a') as stream:\n  stream.write(json.dumps(value) + '\\n')",
        "self.log.record('submissions', value)",
        'self.log.flush()', 'parser.log.flush()',
    ]
    allowed = {ast.dump(ast.parse(s).body[0], include_attributes=False) for s in statements}
    class Strip(ast.NodeTransformer):
        def visit(self, node):
            if isinstance(node, ast.stmt) and ast.dump(node, include_attributes=False) in allowed:
                return None
            return super().visit(node)
    def normalized(text):
        return ast.dump(Strip().visit(ast.parse(text)), include_attributes=False)
    if normalized(old) != normalized(current):
        raise ValueError('Native snapshot semantics changed beyond reviewed progress logging')


class ReviewedMediaRegistry:
    AUTHORIZED_TARGET_WRITES = True
    def __init__(self, manifest, expected_sha256, *, project):
        self.project = Path(project).resolve()
        self.files = {}; self.loaded = {}; self.sources = {}; self.proofs = {}; self.initial = {}
        self.registered = False; self.closed = False
        try:
            self.config = json.loads(self.read(manifest, expected_sha256))
            if self.config.get('version') != 'reviewed-native-media-registry-v1':
                raise ValueError('Explicit native media registry required')
            required = {'src/lab_generate_skill/reviewed_media_registry.py',
                        'src/lab_generate_skill/reddit_submission_snapshot_stream.py',
                        'src/lab_generate_skill/progress_log.py',
                        'scripts/run_site_navigation_once.py'}
            if not required <= self.config['runtime_files'].keys():
                raise ValueError('Current native reader and ordinary runner must be pinned')
            for name, digest in self.config['runtime_files'].items():
                if Path(name).is_absolute() or '..' in Path(name).parts:
                    raise ValueError('Project-relative runtime files required')
                self.read(self.project/name, digest)
            root = self.project/'scripts/native_media'
            for name in ('reddit_media_lifecycle', 'reddit_media_state', 'reddit_media_protocol'):
                if name in sys.modules:
                    raise ValueError('Native media module already loaded from another context')
                path = root/(name+'.py')
                if str(path.relative_to(self.project)) not in self.config['runtime_files']:
                    raise ValueError('Native module missing from registry closure')
                spec = importlib.util.spec_from_file_location(name, path)
                module = importlib.util.module_from_spec(spec)
                sys.modules[name] = module; self.loaded[name] = module
                spec.loader.exec_module(module)
            self.module = self.loaded['reddit_media_protocol']
            if Path(self.module.state.stream.__file__).resolve() != self.project/'src/lab_generate_skill/reddit_submission_snapshot_stream.py':
                raise ValueError('Only the current native snapshot implementation is allowed')
            old_pin = self.config['original_snapshot_reader']
            old = self.read(old_pin['path'], old_pin['sha256']).decode()
            current = (self.project/'src/lab_generate_skill/reddit_submission_snapshot_stream.py').read_text()
            snapshot_semantics(old, current)
            current_provenance = self.module.provenance()
            for item in self.config['sources']:
                sid = item['source_task_id']
                if sid in self.sources:
                    raise ValueError('Duplicate media source')
                packed = self.read(item['record']['path'], item['record']['sha256'])
                original = json.loads(gzip.decompress(packed))
                c, proof = original['contract'], original['proof']
                if (sid != original['source_task_id'] or sid != c['source_task_id']
                        or c['domain'] != 'reddit' or c.get('heldout_quarantine') is not False
                        or item['split'] not in ('train', 'replacement_train')):
                    raise ValueError('Distinct nonheldout source identity required')
                old_provenance = proof['provenance']
                if old_provenance != dict(current_provenance, installed_full13_stream_sha256=old_pin['sha256']):
                    raise ValueError('Unreviewed native implementation or materials change')
                normalized = deepcopy(proof)
                normalized['provenance'] = deepcopy(current_provenance)
                for cycle in normalized['cycles']:
                    for control in cycle['controls'].values():
                        if control['provenance'] != old_provenance:
                            raise ValueError('Historical native control provenance differs')
                        control['provenance'] = deepcopy(current_provenance)
                # Full 14 native controls, complete DB/media guards and both resets.
                initial = self.module.require_admission(c, normalized)
                descriptor = {'version':'reviewed-current-native-media-source-v1',
                              'source_task_id':sid,'retained_record':deepcopy(item['record'])}
                self.sources[sid] = deepcopy(c)
                self.proofs[sid] = (descriptor, normalized)
                self.initial[sid] = initial
            if not self.sources:
                raise ValueError('Nonempty native media source set required')
            self.FEEDBACK_VERSIONS = (self.module.VERSION,)
            self.require_current()
            dispatch.register_protocol('current_native_media', self); self.registered = True
        except BaseException:
            self.close(); raise

    def read(self, path, digest):
        path = Path(path)
        if not path.is_absolute() or path.is_symlink() or not path.is_file():
            raise ValueError('Regular absolute native evidence required')
        before = identity(path); raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest or identity(path) != before:
            raise ValueError('Native registry evidence changed: '+str(path))
        self.files[path] = before
        return raw

    def require_current(self):
        if self.closed or any(identity(p) != state for p,state in self.files.items()):
            raise ValueError('Native registry closed or evidence changed')

    def enabled(self, c):
        return c.get('source_task_id') in self.sources or c.get('kind') == 'native_image_submission'

    def bound(self, c):
        self.require_current()
        sid = c.get('source_task_id')
        if canonical(c) != self.sources.get(sid):
            raise ValueError('Image task differs from its exact reviewed source')
        return sid

    def require_admission(self, c, descriptor):
        sid = self.bound(c)
        if descriptor != self.proofs[sid][0]:
            raise ValueError('Source proof locator differs')
        return deepcopy(self.initial[sid])

    def require_original_binding(self, c, original, inventory):
        self.bound(c)
        return require_source_binding(canonical(c), original, inventory, domain='reddit')

    def NativeReadHooks(self, c, descriptor, directory):
        self.require_admission(c, descriptor)
        return self.module.MediaHooks(canonical(c), self.proofs[c['source_task_id']][1], directory)

    def fields(self, c):
        self.bound(c); return []

    def public_goal(self, c):
        self.bound(c); return self.module.public_goal(canonical(c))

    def upload_files(self, c, hooks=None):
        self.bound(c); return self.module.upload_files(canonical(c))

    def feedback(self, judgment):
        return {'status':judgment['status'], 'reward':judgment['reward'],
                'checks':{k:v for k,v in judgment.get('checks',{}).items() if type(v) is bool},
                'private_reference_values_provided':False, 'action_sequence_provided':False}

    def partition(self, contracts):
        from .website_batch_profile import partition
        for c in contracts: self.bound(c)
        return [dict(rows=x['rows'], profile={**x['profile'],'native_media':True}, runner_arguments=[])
                for x in partition(contracts, 'reddit')]

    def runner(self, argv=None, **kwargs):
        import argparse
        self.require_current()
        parser=argparse.ArgumentParser(add_help=False)
        parser.add_argument('--manifest', type=Path, required=True)
        args,_=parser.parse_known_args(argv)
        rows=[json.loads(line) for line in args.manifest.read_text().splitlines() if line.strip()]
        if len(self.partition(rows)) != 1:
            raise ValueError('One compatible native media profile required')
        runner=importlib.import_module('run_site_navigation_once')
        if Path(runner.__file__).resolve()!=self.project/'scripts/run_site_navigation_once.py':
            raise ValueError('Current ordinary runner required')
        return runner.main(argv, runtime_project=self.project, **kwargs)

    def close(self):
        if self.registered:
            dispatch.unregister_protocol('current_native_media', self); self.registered=False
        for name,module in reversed(list(self.loaded.items())):
            if sys.modules.get(name) is module:sys.modules.pop(name)
        self.loaded.clear();self.closed=True

    def __enter__(self):self.require_current();return self
    def __exit__(self,*args):self.close()
