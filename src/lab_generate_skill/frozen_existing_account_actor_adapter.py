"""Reviewed existing-account login in the shared terminal-only actor lifecycle."""
from .frozen_account_actor_adapter import FrozenAccountActorAdapter
from .map_existing_account_observation import ExistingAccountObservationHooks,VERSION
from .map_account_profile import existing_profile_for_contracts


class FrozenExistingAccountActorAdapter(FrozenAccountActorAdapter):
    AUTHORIZED_TARGET_WRITES=False
    FEEDBACK_VERSIONS=(VERSION,)

    def enabled(self,c):
        return c.get('domain')=='map'and c.get('candidate_completion',{}).get('family')=='account_login'

    def verified(self,c,descriptor):
        candidate=self.canonical(c);source=self.resolve(candidate['source_task_id'],descriptor)
        a=source['admission']
        if (source['candidate']!=candidate or a.get('version')!='native-existing-account-normal-admission-v1'
                or a.get('source_task_id')!=candidate['source_task_id']
                or any(a.get(k)is not True for k in ('passed','native_controls_verified','ordinary_lifecycle_verified',
                    'initial_anonymous_verified','post_reset_anonymous_verified'))
                or a.get('baseline')!=source['baseline'] or not source['baseline']):
            raise ValueError('Existing-account contract or admission differs')
        return source

    def NativeReadHooks(self,c,descriptor,directory):
        source=self.verified(c,descriptor)
        return ExistingAccountObservationHooks(self.canonical(c),directory,baseline=source['baseline'])

    def profile_for_contracts(self,contracts):
        return existing_profile_for_contracts([self.canonical(c)for c in contracts])

    def feedback(self,judgment):
        from .map_account_terminal import feedback,VERSION as BASE_VERSION
        if judgment.get('version')!=VERSION:raise ValueError('Existing-account feedback version required')
        return feedback(dict(judgment,version=BASE_VERSION))
