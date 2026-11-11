"""Passive route/answer lifecycle for the explicitly defined highway query."""
from copy import deepcopy
from .map_candidate_route_observation import RouteObservationHooks
from .map_route_highways import evaluate, reference_highways
from .admin_pilot import final_answer
from .io_utils import atomic_write_json


class HighwayEpisodeHooks(RouteObservationHooks):
    def __init__(self, candidate, directory, *, baseline, reference):
        reference_highways(reference)
        native = next(x['native'] for x in reference['scope']['rendered_route_spec']['alternatives']
                      if x['profile'] == reference['profile'])
        route_reference = dict(pair=reference['pair'], profile=reference['profile'],
                               body=reference['native_body'], reference_state=native)
        super().__init__(candidate, directory, baseline=baseline, references=[route_reference])
        self.highway_reference = deepcopy(reference)
        self.trace = None

    def provide_trace(self, trace):
        if self.trace is not None or self.scored or not self.closed or not isinstance(trace, dict):
            raise ValueError('One completed trace after browser closure required')
        self.trace = deepcopy(trace)

    def score_terminal(self, site, terminal, *, runtime_error=None):
        if self.trace is None or not self.closed:
            raise ValueError('Completed episode and actual answer required')
        # Reuse the existing route health/capture predicate. A normal no-route
        # or wrong-page terminal is failure, not missing reference evidence.
        route_result, integrity = super().score_terminal(site, terminal, runtime_error=runtime_error)
        judgment = route_result
        if route_result['status'] == 'success':
            answer = final_answer(self.trace)
            if isinstance(answer, str):
                import json
                try:
                    answer = json.loads(answer)
                except ValueError:
                    pass
            judgment = evaluate(self.highway_reference, served=self.served,
                                state=self.native_terminal, url=terminal['url'], answer=answer,
                                runtime_error=runtime_error, integrity=integrity)
        atomic_write_json(self.directory/'highways-terminal.json', dict(
            route_judgment=route_result, judgment=judgment, integrity=integrity,
            private_reference_sent_to_actor=False))
        return judgment, integrity
