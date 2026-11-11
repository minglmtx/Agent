"""Reviewed native share artifacts in the common terminal-only actor lifecycle."""
from copy import deepcopy
from .map_share_observation import ShareObservationHooks
from .map_share_terminal import VERSION, feedback, FAMILIES
from .source_revision_binding import require_source_binding


class FrozenShareActorAdapter:
    FEEDBACK_VERSIONS=(VERSION,)
    AUTHORIZED_TARGET_WRITES=False

    def __init__(self,*,resolve_proof):
        if not callable(resolve_proof):raise ValueError('Frozen share resolver required')
        self.resolve=resolve_proof

    def enabled(self,c):
        return c.get('domain')=='map' and c.get('candidate_completion',{}).get('family')in FAMILIES

    def canonical(self,c):
        if not self.enabled(c):raise ValueError('Declared native share contract required')
        return deepcopy({k:v for k,v in c.items()if k!='admission_result'})

    def verified(self,c,descriptor):
        candidate=self.canonical(c);source=self.resolve(candidate['source_task_id'],descriptor)
        a=source['admission']
        if (source['candidate']!=candidate or a.get('version')!='native-share-normal-admission-v1'
                or a.get('source_task_id')!=candidate['source_task_id']
                or any(a.get(k)is not True for k in ('passed','two_cold_environment_verified',
                    'ordinary_lifecycle_verified','native_artifact_controls_verified'))
                or a.get('baseline')!=source['baseline'] or not source['baseline']):
            raise ValueError('Native share contract or admission differs')
        return source

    def require_admission(self,c,descriptor):
        return deepcopy(self.verified(c,descriptor)['admission'])

    def require_original_binding(self,c,original,inventory):
        return require_source_binding(self.canonical(c),original,inventory,domain='map')

    def NativeReadHooks(self,c,descriptor,directory):
        source=self.verified(c,descriptor)
        return ShareObservationHooks(self.canonical(c),directory,baseline=source['baseline'])

    def public_goal(self,c):return self.canonical(c)['goal']
    def profile_for_contracts(self,contracts):
        rows=list(contracts)
        compact=[c.get('candidate_completion',{}).get('family')=='short_route_link' for c in rows]
        if not any(compact):return {}
        if not all(compact) or any(c.get('domain')!='map'for c in rows):
            raise ValueError('Compact-route tasks need a dedicated same-profile manifest')
        return {'map_short_routes':True}
    def fields(self,c):
        family=self.canonical(c)['candidate_completion']['family']
        if family=='share_panel_navigation':return []
        return {'embed_html'if family=='map_embed'else'share_link':'string'}
    def feedback(self,judgment):return feedback(judgment)
