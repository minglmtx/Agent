"""Reviewed route images use the ordinary terminal-download actor lifecycle."""
from .frozen_route_actor_adapter import FrozenRouteActorAdapter
from .map_route_image_episode import RouteImageHooks
from .map_route_image_downloads import VERSION


class FrozenRouteImageActorAdapter(FrozenRouteActorAdapter):
    FEEDBACK_VERSIONS=(VERSION,)

    def enabled(self,c):
        return c.get('domain')=='map' and c.get('candidate_completion',{}).get('family')=='route_png_artifact'

    def verified(self,c,descriptor):
        candidate=self.canonical(c);source=self.resolve(candidate['source_task_id'],descriptor)
        a=source['admission']
        if (source['candidate']!=candidate or a.get('version')!='native-route-image-admission-v1'
                or a.get('source_task_id')!=candidate['source_task_id']
                or any(a.get(k)is not True for k in ('passed','ordinary_lifecycle_verified',
                    'native_artifact_controls_verified','reset_verified'))
                or a.get('render_query_policy')!='stable-scan'
                or a.get('baseline')!=source['baseline'] or not source['baseline']):
            raise ValueError('Exact route image, renderer, controls and reset required')
        return source

    def NativeReadHooks(self,c,descriptor,directory):
        source=self.verified(c,descriptor)
        return RouteImageHooks(self.canonical(c),directory,baseline=source['baseline'],references=source['references'])

    def profile_for_contracts(self,contracts):
        rows=list(contracts)
        if not rows or not all(self.enabled(c)for c in rows):
            raise ValueError('Reviewed route-image profile required')
        return dict(map_raster_export=True,map_raster_query_policy='stable-scan')
