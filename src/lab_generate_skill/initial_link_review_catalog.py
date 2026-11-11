"""Exact retained initial-map-link evidence with reviewed current dependencies.

Only the trusted publication selects this catalog and its pinned scope review.
Historical provenance stays unchanged. Public wrappers add registry metadata;
controls and hooks continue to use the exact originally verified contract.
"""
from copy import deepcopy
from pathlib import Path
import hashlib,json
from .provider_review_catalog import identity
from . import map_initial_view_link_runtime as runtime
from .source_revision_binding import fingerprint

VERSION='reviewed-initial-map-link-v1'


class InitialLinkReviewCatalog:
    def __init__(self,config,*,project):
        self.config=deepcopy(config);self.files={};self.sources={};self.descriptors={};self.closed=False
        project=Path(project)
        scope=self.read(config['scope_review'])
        semantic=self.read(config['semantic_review'])
        # Baseline changes invalidate this reuse before a website is started.
        baseline_metadata=self.read(scope['baseline_metadata'])
        if baseline_metadata.get('status')!='complete' or baseline_metadata.get('full_snapshot_imported')is not True:
            raise ValueError('The reviewed published baseline is unavailable')
        if (scope.get('passed')is not True or scope.get('profile')!=runtime.PROFILE
                or scope.get('semantic_review')!=config['semantic_review']
                or scope.get('native_proof_checker_equivalent')is not True
                or scope.get('hooks_ast_unchanged')is not True):
            raise ValueError('Exact tested default-profile dependency review required')
        required={'map_initial_view_link','map_initial_view_link_runtime','map_view',
                  'map_reset_guard','site_worker','map_query_site','initial_link_review_catalog',
                  'frozen_initial_link_actor_adapter'}
        pins=scope['current_dependencies']
        if set(pins)!={'src/lab_generate_skill/'+n+'.py'for n in required}:
            raise ValueError('Complete scoped runtime dependency set required')
        for name,digest in pins.items():self.read(dict(path=str(project/name),sha256=digest),json_value=False)
        dependency=self.read(scope['dependency_review'])
        if dependency.get('passed')is not True or dependency['semantic_review']!=config['semantic_review']:
            raise ValueError('Scoped differential dependency evidence required')
        rows={r['source_task_id']:r for r in semantic['records']}
        if (set(rows)!=set(scope['original_contract_sha256'])
                or len(rows)!=len(semantic['records'])or not rows):
            raise ValueError('Exact original source scope required')
        for sid,row in rows.items():
            c=deepcopy(row['contract']);c.pop('admission_result',None)
            if (fingerprint(c)!=scope['original_contract_sha256'][sid]
                    or fingerprint(c)!=dependency['source_contract_fingerprints'][sid]
                    or c.get('heldout_quarantine')is not False
                    or c.get('split','train')!='train'
                    or not c['start_path'].startswith('/#map=')):
                raise ValueError('Retained source/profile/goal/start changed')
            p=self.read(row['native_proof'])
            old=scope['original_provenance']
            if p['provenance']!=old:
                raise ValueError('Historical dependency identity differs from reviewed code')
            # No rewritten provenance and no import of the historical runtime.
            baseline,reference=runtime.verify_retained_native_proof(c,p,expected_provenance=old)
            candidate=dict(c,split='train',reviewed_initial_link={'version':VERSION})
            # The reviewed adapter owns this lifecycle; do not also select the
            # built-in exact-provenance adapter. Keep its original flag only
            # in the immutable original contract used by private hooks.
            candidate.pop('map_initial_view_link')
            desc=dict(version=VERSION,source_task_id=sid,candidate_sha256=fingerprint(candidate),
                      native_proof_sha256=row['native_proof']['sha256'],scope_review_sha256=config['scope_review']['sha256'])
            self.sources[sid]=dict(candidate=candidate,original=c,baseline=baseline,reference=reference,
                                  admission=dict(passed=True,two_cold_environment_verified=True,ordinary_lifecycle_verified=True,
                                  retained_native_controls_verified=True,source_task_id=sid,baseline=baseline))
            self.descriptors[sid]=desc
        self.require_current()

    def read(self,pin,*,json_value=True):
        path=Path(pin['path'])
        if not path.is_absolute():raise ValueError('Absolute pinned evidence required')
        before=identity(path);raw=path.read_bytes()
        actual=hashlib.sha256(raw).hexdigest()
        if actual!=pin['sha256']:
            from .reviewed_code_evolution import accepts
            if not accepts(self,pin,path,actual,json_value=json_value):raise ValueError('Pinned evidence/code changed: '+str(path))
        if identity(path)!=before:raise ValueError('Pinned evidence/code changed: '+str(path))
        self.files[path]=before
        return json.loads(raw)if json_value else raw

    def require_current(self):
        if self.closed or any(identity(p)!=value for p,value in self.files.items()):
            raise ValueError('Reviewed initial-link catalog changed or closed')

    def resolve(self,sid,descriptor):
        self.require_current()
        if sid not in self.sources or descriptor!=self.descriptors[sid]:
            raise ValueError('Exact source-bound descriptor required')
        from .reviewed_code_evolution import require_source
        require_source(self,sid)
        return deepcopy(self.sources[sid])

    def close(self):
        self.closed=True;self.sources.clear()
