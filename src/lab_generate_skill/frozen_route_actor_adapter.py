"""Reviewed native routes in the common terminal-only actor lifecycle."""
from copy import deepcopy
from .map_candidate_route_observation import RouteObservationHooks
from .map_candidate_route_terminal import VERSION, feedback
from .source_revision_binding import require_source_binding


class FrozenRouteActorAdapter:
    FEEDBACK_VERSIONS=(VERSION,)
    AUTHORIZED_TARGET_WRITES=False

    def __init__(self,*,resolve_proof):
        if not callable(resolve_proof):raise ValueError('Frozen route resolver required')
        self.resolve=resolve_proof

    def enabled(self,c):
        return c.get('domain')=='map' and c.get('candidate_completion',{}).get('family')=='displayed_route'

    def canonical(self,c):
        if not self.enabled(c):raise ValueError('Declared native route contract required')
        return deepcopy({k:v for k,v in c.items()if k!='admission_result'})

    def verified(self,c,descriptor):
        candidate=self.canonical(c);source=self.resolve(candidate['source_task_id'],descriptor)
        a=source['admission']
        if (source['candidate']!=candidate or a.get('version')!='native-route-normal-admission-v1'
                or a.get('source_task_id')!=candidate['source_task_id']
                or any(a.get(k)is not True for k in ('passed','two_cold_environment_verified',
                    'ordinary_lifecycle_verified','all_route_alternatives_verified'))
                or a.get('baseline')!=source['baseline'] or not source['baseline'] or not source['references']):
            raise ValueError('Native route contract or admission differs')
        return source

    def require_admission(self,c,descriptor):
        return deepcopy(self.verified(c,descriptor)['admission'])

    def require_original_binding(self,c,original,inventory):
        return require_source_binding(self.canonical(c),original,inventory,domain='map')

    def NativeReadHooks(self,c,descriptor,directory):
        source=self.verified(c,descriptor)
        return RouteObservationHooks(self.canonical(c),directory,baseline=source['baseline'],references=source['references'])

    def public_goal(self,c):return self.canonical(c)['goal']
    def fields(self,c):
        self.canonical(c)
        return []
    def feedback(self,judgment):
        if judgment.get('version')==VERSION:return feedback(judgment)
        if judgment.get('version')not in self.FEEDBACK_VERSIONS:
            raise ValueError('Unregistered native route output feedback')
        return dict(status=judgment['status'],reward=judgment['reward'],
            checks=[dict(condition=k,passed=v)for k,v in judgment['checks'].items()if type(v)is bool],
            private_reference_values_provided=False,action_sequence_provided=False)
