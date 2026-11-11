"""Exact compact-route proof binding, using the shared ordinary share hooks."""
from .frozen_share_actor_adapter import FrozenShareActorAdapter


class FrozenShortRouteActorAdapter(FrozenShareActorAdapter):
    def enabled(self,c):
        return c.get('domain')=='map'and c.get('candidate_completion',{}).get('family')=='short_route_link'

    def verified(self,c,descriptor):
        candidate=self.canonical(c);source=self.resolve(candidate['source_task_id'],descriptor)
        a=source['admission']
        if (source['candidate']!=candidate or a.get('version')!='native-short-route-normal-admission-v1'
                or a.get('source_task_id')!=candidate['source_task_id']
                or any(a.get(k)is not True for k in ('passed','native_artifact_controls_verified',
                    'ordinary_lifecycle_verified','reset_verified'))
                or a.get('baseline')!=source['baseline']or not source['baseline']):
            raise ValueError('Compact-route task, native controls or ordinary reset proof changed')
        return source
