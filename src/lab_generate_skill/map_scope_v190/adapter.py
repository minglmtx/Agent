"""Bind current registry calls to byte-identical qualified lifecycle adapters."""
from .qualified_gps import Adapter as QualifiedGPS
from .qualified_layers import Adapter as QualifiedLayers


class Bridge:
    AUTHORIZED_TARGET_WRITES = False

    def __init__(self, *, resolve_proof):
        if not callable(resolve_proof):
            raise ValueError('Current verified source resolver required')
        self.resolve = resolve_proof

    def source(self, candidate, descriptor=None, *, admission=False):
        if not self.enabled(candidate):
            raise ValueError('Explicit native scope candidate required')
        source = self.resolve(candidate['source_task_id'], descriptor)
        source['adapter'].canonical(candidate)
        if admission and (descriptor is None or descriptor != source['descriptor']):
            raise ValueError('Exact source admission descriptor required')
        return source

    def canonical(self, candidate):
        source = self.source(candidate)
        return source['adapter'].canonical(candidate)

    def require_admission(self, candidate, descriptor):
        return self.source(candidate, descriptor, admission=True)['adapter'].require_admission(candidate, descriptor)

    def require_original_binding(self, candidate, original, inventory):
        return self.source(candidate)['adapter'].require_original_binding(candidate, original, inventory)

    def NativeReadHooks(self, candidate, descriptor, directory):
        return self.source(candidate, descriptor, admission=True)['adapter'].NativeReadHooks(candidate, descriptor, directory)

    def public_goal(self, candidate):
        return self.source(candidate)['adapter'].public_goal(candidate)

    def fields(self, candidate):
        return self.source(candidate)['adapter'].fields(candidate)


class GPSAdapter(Bridge):
    FEEDBACK_VERSIONS = QualifiedGPS.FEEDBACK_VERSIONS

    def enabled(self, candidate):
        return candidate.get('domain') == 'map' and candidate.get('candidate_completion', {}).get('family') == 'gps_overlay_enabled'

    feedback = QualifiedGPS.feedback


class LayerAdapter(Bridge):
    FEEDBACK_VERSIONS = QualifiedLayers.FEEDBACK_VERSIONS

    def enabled(self, candidate):
        return candidate.get('version') == 'map-local-overlay-public-scope-v1'

    feedback = QualifiedLayers.feedback
