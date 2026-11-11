"""Admit format-specific reviewed exports to the terminal-download lifecycle."""
from .frozen_share_actor_adapter import FrozenShareActorAdapter
from .map_raster_observation import RasterObservationHooks
from .map_raster_downloads import VERSION, PDF_VERSION, feedback


class FrozenRasterActorAdapter(FrozenShareActorAdapter):
    FEEDBACK_VERSIONS = (VERSION, PDF_VERSION)

    def enabled(self, c):
        return c.get('domain') == 'map' and c.get('candidate_completion', {}).get('family') in ('png_artifact','pdf_artifact')

    def verified(self, c, descriptor):
        candidate = self.canonical(c)
        source = self.resolve(candidate['source_task_id'], descriptor)
        a = source['admission']
        format_name=candidate['candidate_completion']['family'].split('_')[0]
        if format_name == 'pdf' and a.get('render_query_policy') != 'stable-scan':
            raise ValueError('PDF proof must bind the validated stable-scan renderer')
        if format_name=='png' and (candidate.get('render_query_policy','default') not in ('default','stable-scan')
                or a.get('render_query_policy','default')!=candidate.get('render_query_policy','default')):
            raise ValueError('PNG actor renderer must match the native control policy')
        if (source['candidate'] != candidate or a.get('version') != 'native-'+format_name+'-normal-admission-v1'
                or a.get('source_task_id') != candidate['source_task_id']
                or any(a.get(k) is not True for k in ('passed', 'native_artifact_controls_verified',
                                                     'ordinary_lifecycle_verified', 'reset_verified'))
                or not source['baseline'] or a.get('baseline') != source['baseline']):
            raise ValueError('Export format, contract, controls or reset evidence differs')
        return source

    def NativeReadHooks(self, c, descriptor, directory):
        source = self.verified(c, descriptor)
        return RasterObservationHooks(self.canonical(c), directory, baseline=source['baseline'])

    def profile_for_contracts(self, contracts):
        rows = list(contracts)
        if (not rows or not all(self.enabled(c) for c in rows)
                or len({c['candidate_completion']['family']for c in rows})!=1):
            raise ValueError('Each native export format requires a dedicated renderer profile')
        profile={'map_raster_export': True}
        if rows[0]['candidate_completion']['family']=='pdf_artifact':
            profile.update(map_pdf_export=True,map_raster_query_policy='stable-scan')
        else:
            policies={c.get('render_query_policy','default')for c in rows}
            if len(policies)!=1 or not policies<={'default','stable-scan'}:
                raise ValueError('PNG renderer policies require separate service profiles')
            policy=next(iter(policies))
            if policy!='default':profile['map_raster_query_policy']=policy
        return profile

    def fields(self, c):
        self.canonical(c)
        return []  # The actual saved artifact is scored, not an asserted answer.

    def feedback(self, judgment):
        return feedback(judgment)
