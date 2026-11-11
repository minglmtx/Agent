"""Reviewed native signup accounts in the common terminal-only actor lifecycle."""
from copy import deepcopy
from .map_account_observation import AccountObservationHooks
from .map_account_terminal import VERSION, feedback, public_goal
from .source_revision_binding import require_source_binding


class FrozenAccountActorAdapter:
    FEEDBACK_VERSIONS=(VERSION,)
    AUTHORIZED_TARGET_WRITES=True

    def __init__(self,*,resolve_proof):
        if not callable(resolve_proof):raise ValueError('Frozen account resolver required')
        self.resolve=resolve_proof

    def enabled(self,c):
        return c.get('domain')=='map' and c.get('candidate_completion',{}).get('family')=='account_signup'

    def canonical(self,c):
        if not self.enabled(c):raise ValueError('Declared native account contract required')
        return deepcopy({k:v for k,v in c.items()if k!='admission_result'})

    def verified(self,c,descriptor):
        candidate=self.canonical(c);source=self.resolve(candidate['source_task_id'],descriptor)
        a=source['admission']
        if (source['candidate']!=candidate or a.get('version')!='native-account-normal-admission-v1'
                or a.get('source_task_id')!=candidate['source_task_id']
                or any(a.get(k)is not True for k in ('passed','two_cold_environment_verified',
                    'ordinary_lifecycle_verified','account_confirmation_session_verified'))
                or a.get('baseline')!=source['baseline'] or not source['baseline']):
            raise ValueError('Native account contract or admission differs')
        return source

    def require_admission(self,c,descriptor):
        return deepcopy(self.verified(c,descriptor)['admission'])

    def require_original_binding(self,c,original,inventory):
        return require_source_binding(self.canonical(c),original,inventory,domain='map')

    def NativeReadHooks(self,c,descriptor,directory):
        source=self.verified(c,descriptor)
        return AccountObservationHooks(self.canonical(c),directory,baseline=source['baseline'])

    def public_goal(self,c):return public_goal(self.canonical(c))
    def fields(self,c):
        self.canonical(c)
        return []
    def feedback(self,judgment):return feedback(judgment)

    def profile_for_contracts(self,contracts):
        from .map_account_profile import profile_for_contracts
        return profile_for_contracts([self.canonical(c)for c in contracts])
