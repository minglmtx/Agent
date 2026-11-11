"""Use reviewed PDF/answer controls in the ordinary one-attempt actor runner."""
from .frozen_route_actor_adapter import FrozenRouteActorAdapter
from .map_route_print_episode import PrintEpisodeHooks
from .map_highways_episode import HighwayEpisodeHooks


class FrozenRouteOutputActorAdapter(FrozenRouteActorAdapter):
    FEEDBACK_VERSIONS=('map-candidate-native-route-terminal-v1',
        'native-route-print-episode-v1','native-numbered-route-highways-v1')

    def enabled(self,c):
        return (super().enabled(c) and
            (c.get('browser_capabilities',{}).get('print_to_pdf')is True
             or c.get('answer_fields')=={'highway_refs':'text_list'}))

    def verified(self,c,descriptor):
        candidate=self.canonical(c);source=self.resolve(candidate['source_task_id'],descriptor)
        a=source['admission']
        if (source['candidate']!=candidate or a.get('version')!='native-route-output-admission-v1'
                or a.get('source_task_id')!=candidate['source_task_id']
                or any(a.get(k)is not True for k in ('passed','ordinary_lifecycle_verified',
                    'native_output_controls_verified','reset_verified'))
                or a.get('baseline')!=source['baseline'] or not source['baseline']):
            raise ValueError('Exact route output, ordinary controls and reset required')
        return source

    def NativeReadHooks(self,c,descriptor,directory):
        source=self.verified(c,descriptor);candidate=self.canonical(c)
        cls=PrintEpisodeHooks if candidate.get('browser_capabilities',{}).get('print_to_pdf')else HighwayEpisodeHooks
        return cls(candidate,directory,baseline=source['baseline'],reference=source['reference'])

    def fields(self,c):
        return self.canonical(c).get('answer_fields',[])
