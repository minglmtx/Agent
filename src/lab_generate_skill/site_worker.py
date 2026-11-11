"""Private worker sites, with reset policies selected per adapter.

Content sites restore a full offline clone between tasks. Separate workers
never share mutable state; a failed reset cannot expose dirty state to an actor.
"""
from contextlib import contextmanager
from pathlib import Path
from .gitlab_site import IsolatedGitlabSite
from .map_query_site import IsolatedMapQuerySite
from .map_reset_guard import MapStateChanged


def website_batch_tasks(current_tasks, backend_holder=None):
    """Only count other manifests when their website services are reused.

    Sharing model weights does not amortize another website's startup. The
    archived bundle owner explicitly enables service reuse with site_logs_root.
    """
    if (backend_holder is not None
            and backend_holder.site_logs_root is not None
            and backend_holder.service_tasks is not None):
        return backend_holder.service_tasks
    return current_tasks


def website_instance_count(*, tasks, scripted=False, requested=None, domain=None):
    """Amortize two cold sites over at least two episodes per site.

    Tiny diagnostic batches reuse one site with the usual full reset. Larger
    batches can overlap resets using two isolated sites. Explicit settings are
    retained for controlled performance/isolation experiments.
    """
    if type(tasks) is not int or tasks < 0:
        raise ValueError('Task count must be a nonnegative integer')
    if type(scripted) is not bool:
        raise ValueError('Scripted must be boolean')
    if domain not in (None, "map", "gitlab", "reddit", "shopping"):
        raise ValueError("Unknown website resource profile")
    if requested is not None:
        if type(requested) is not int or requested not in (1, 2):
            raise ValueError('Requested site instances must be 1 or 2')
        return requested
    # A Map cold instance copies the full app DB; its clean reset only
    # restarts Rails. Amortize a second cold instance over a genuinely large
    # batch. Explicit instance counts still support controlled experiments.
    minimum = 64 if domain == "map" else 4
    return 2 if not scripted and tasks >= minimum else 1


class SiteWorker:
    def __init__(self,root,logs,domain,*,gitlab_reset='clone',shopping_capture_mail=False,map_community_fixture=None,map_native_layers=False,gitlab_prefetch=None,shopping_instances=1,gitlab_instances=1,reddit_instances=1,map_instances=1,map_native_asset_manifest=None,map_native_frontend_manifest=None,map_native_provider_manifest=None,map_share_observer=False,map_location_observer=False,map_short_routes=False,map_raster_export=False,map_pdf_export=False,map_raster_query_policy=None,map_account=None,map_existing_account=None,map_reader_diaries=None,map_saved_node_editor=None,gitlab_initial_profile=None,gitlab_cache_initialization=None):
        from .gitlab_declared_profiles import validate_profile
        self.gitlab_initial_profile=validate_profile(gitlab_initial_profile)
        if self.gitlab_initial_profile is not None and domain!='gitlab':
            raise ValueError('GitLab initial state requires GitLab')
        if gitlab_cache_initialization is not None and (domain!='gitlab' or gitlab_cache_initialization not in ('wiki_issue','calendar_wiki_issue') or self.gitlab_initial_profile is not None):
            raise ValueError('Native cache profile requires a separate plain GitLab baseline')
        self.gitlab_cache_initialization=gitlab_cache_initialization
        if gitlab_reset != 'clone':raise ValueError('Only optimized clone resets are supported')
        if shopping_capture_mail and domain!='shopping':raise ValueError('Local newsletter mail profile is Shopping only')
        if type(shopping_instances) is not int or shopping_instances not in (1,2):
            raise ValueError('Shopping instances must be explicitly 1 or 2')
        if shopping_instances==2 and domain!='shopping':
            raise ValueError('Shopping instances require Shopping')
        if type(gitlab_instances) is not int or gitlab_instances not in (1,2):
            raise ValueError('GitLab instances must be explicitly 1 or 2')
        if gitlab_instances==2 and domain!='gitlab':
            raise ValueError('GitLab instances require GitLab')
        for name,count in (('reddit',reddit_instances),('map',map_instances)):
            if type(count) is not int or count not in (1,2):raise ValueError(name+' instances must be 1 or 2')
            if count==2 and domain!=name:raise ValueError(name+' instances require matching domain')
        if domain!='map' and (map_native_asset_manifest is not None or map_native_frontend_manifest is not None or map_native_provider_manifest is not None):
            raise ValueError('Regional native environment assets require Map')
        if type(map_share_observer)is not bool or (map_share_observer and domain!='map'):
            raise ValueError('Native share observer requires Map')
        self.map_environment_options={k:v for k,v in {
            'native_assets_manifest':map_native_asset_manifest,
            'native_frontend_manifest':map_native_frontend_manifest,
            'native_provider_manifest':map_native_provider_manifest}.items() if v is not None}
        if map_share_observer:self.map_environment_options['native_share_observer']=True
        if type(map_short_routes)is not bool or (map_short_routes and
                (domain!='map' or map_instances!=1 or map_community_fixture is not None
                 or map_native_layers or any(v is not None for v in
                    (map_native_asset_manifest,map_native_frontend_manifest,map_native_provider_manifest)))):
            raise ValueError('Compact routes require a separate single-instance Map share profile')
        if map_short_routes:self.map_environment_options.update(native_share_observer=True,native_short_routes=True)
        if type(map_raster_export)is not bool or (map_raster_export and
                (domain!='map' or map_instances!=1 or map_community_fixture is not None
                 or map_native_layers or map_short_routes or map_account is not None
                 or map_existing_account is not None or any(v is not None for v in
                    (map_native_asset_manifest,map_native_frontend_manifest,map_native_provider_manifest)))):
            raise ValueError('PNG export requires a dedicated single-instance Map renderer profile')
        if type(map_location_observer)is not bool or (map_location_observer and
                (domain!='map' or map_instances!=1 or map_community_fixture is not None
                 or map_native_layers or map_short_routes or map_raster_export
                 or map_account is not None or map_existing_account is not None
                 or any(v is not None for v in (map_native_asset_manifest,map_native_frontend_manifest,map_native_provider_manifest)))):
            raise ValueError('Location observer requires its dedicated single-instance native Map profile')
        self.map_location_observer=map_location_observer
        self.map_raster_export=map_raster_export
        if type(map_pdf_export)is not bool or (map_pdf_export and not map_raster_export):
            raise ValueError('PDF requires the dedicated raster export profile')
        self.map_pdf_export=map_pdf_export
        if map_raster_query_policy is not None and (not map_raster_export or map_raster_query_policy not in ('default','stable-scan')):
            raise ValueError('Explicit supported renderer profile required for query policy')
        self.map_raster_query_policy=map_raster_query_policy
        self.map_account=None
        if map_account is not None:
            from .map_account_profile import validate_account
            if (domain!='map' or map_instances!=1 or self.map_environment_options
                    or map_community_fixture is not None or map_native_layers):
                raise ValueError('Account inbox requires its verified single-instance Map profile')
            self.map_account=validate_account(map_account)
        self.map_reader_diaries=None
        if map_reader_diaries is not None:
            from .map_reader_v187.profile import validate_profile
            if (domain!='map' or map_instances!=1 or self.map_environment_options
                    or map_community_fixture is not None or map_native_layers
                    or map_account is not None or map_existing_account is not None
                    or map_location_observer or map_raster_export or map_short_routes):
                raise ValueError('Native reader/diary fixture requires its dedicated single-instance Map profile')
            self.map_reader_diaries=validate_profile(map_reader_diaries)
        self.map_existing_account=None
        if map_existing_account is not None:
            from .map_account_profile import validate_account
            if (domain!='map' or map_instances!=1 or self.map_environment_options
                    or map_community_fixture is not None or map_native_layers or map_account is not None):
                raise ValueError('Existing-account login requires its separate single-instance Map profile')
            self.map_existing_account=validate_account(map_existing_account)
        self.map_saved_node_editor=None
        if map_saved_node_editor is not None:
            from .map_edit_v190.profile import validate_profile
            if (domain!='map' or map_instances!=1 or self.map_environment_options
                    or map_community_fixture is not None or map_native_layers
                    or map_account is not None or map_existing_account is not None
                    or map_reader_diaries is not None or map_location_observer
                    or map_raster_export or map_pdf_export or map_short_routes):
                raise ValueError('Native saved-node editing requires its dedicated single-instance Map profile')
            self.map_saved_node_editor=validate_profile(map_saved_node_editor)
        self.reddit_instances=reddit_instances;self.map_instances=map_instances
        self.gitlab_instances=gitlab_instances
        self.shopping_instances=shopping_instances;self.pair=None;self._pair_failure=None
        self.root=Path(root);self.logs=Path(logs);self.domain=domain
        self.shopping_capture_mail=shopping_capture_mail
        if map_community_fixture is not None:
            from .map_community_fixture import SUPPORTED_PROFILES
            if domain!='map' or map_community_fixture not in SUPPORTED_PROFILES:raise ValueError('Invalid Map community profile')
        if type(map_native_layers)is not bool or map_native_layers and domain!="map":raise ValueError("Native layer profile is Map only")
        self.map_native_layers=map_native_layers
        self.map_community_fixture=map_community_fixture
        self.gitlab_reset=gitlab_reset;self.shared=None;self.in_use=False
        self.map_instance_index=0
        if gitlab_prefetch not in (None,True) or gitlab_prefetch is not None and type(gitlab_prefetch) is not bool:
            raise ValueError('GitLab reset prefetch is required')
        self.gitlab_prefetch=True
        self.content_reset='clone'

    @contextmanager
    def episode(self,task_logs,*,reuse=True):
        if self.in_use:raise RuntimeError('A website worker cannot serve simultaneous episodes')
        self.in_use=True
        try:
            if self.domain=='gitlab' and self.gitlab_instances==1:
                if self.shared is None:
                    site=self._new_gitlab_site(self.logs)
                    self.shared=site.__enter__();self.shared.domain='gitlab'
                else:
                    try:self.shared.reset_state()
                    except BaseException:
                        self.close();raise
                yield self.shared
            elif self.domain=='map' and self.map_instances==1:
                if self.shared is not None:
                    try:self.shared.reset_state()
                    except MapStateChanged:self.close()
                    except BaseException:
                        self.close();raise
                if self.shared is None:
                    # Reused services keep writing until worker teardown. Their
                    # logs must not mutate a previously closed task checkpoint.
                    service_logs=self.logs/('map-instance-'+str(self.map_instance_index))
                    self.map_instance_index+=1
                    if self.map_account is not None:
                        from .map_account_site import IsolatedMapAccountSite
                        site=IsolatedMapAccountSite(self.root,service_logs,account=self.map_account)
                    elif self.map_reader_diaries is not None:
                        from .map_reader_v187.profile import new_site
                        site=new_site(self.root,service_logs,self.map_reader_diaries)
                    elif self.map_existing_account is not None:
                        from .map_existing_account_site import IsolatedMapExistingAccountSite
                        site=IsolatedMapExistingAccountSite(self.root,service_logs,account=self.map_existing_account)
                    elif self.map_saved_node_editor is not None:
                        from .map_edit_v190.profile import new_site
                        site=new_site(self.root,service_logs,self.map_saved_node_editor)
                    elif self.map_location_observer:
                        from .map_location_factory import new_site
                        site=new_site(self.root,service_logs)
                    elif self.map_raster_export:
                        from .map_raster_site import IsolatedMapRasterSite
                        site=IsolatedMapRasterSite(self.root,service_logs,allow_pdf=self.map_pdf_export,**({'query_policy':self.map_raster_query_policy} if self.map_raster_query_policy is not None else {}))
                    else:
                        site=IsolatedMapQuerySite(self.root,service_logs,with_tiles=True,with_geographic_baseline=True,track_changes=True,
                            **self.map_environment_options,
                            **({'native_layer_refresh':True,'web_workers':0}if self.map_native_layers else {}),
                            **({'community_fixture':self.map_community_fixture}if self.map_community_fixture else {}))
                    self.shared=site.__enter__()
                yield self.shared
            elif self.paired:
                if self._pair_failure is not None:
                    raise RuntimeError('Paired website reset/start failed; worker must stop') from self._pair_failure
                self.prepare_pair()
                ready=False
                try:
                    with self.pair.episode(reuse=reuse) as site:
                        ready=True
                        site.domain=self.domain
                        yield site
                except BaseException as error:
                    # Foreground actor/contract errors still permit a clean
                    # next episode. A failed site acquisition never does.
                    if not ready:self._pair_failure=error
                    raise
            elif self.domain in ('shopping','reddit'):
                if self.shared is None:
                    from .reusable_content_site import ReusableContentSite
                    site=ReusableContentSite(self.root,self.logs,self.domain,
                        **({'capture_mail':True}if self.shopping_capture_mail else {}))
                    self.shared=site.__enter__()
                else:
                    try:self.shared.reset_state()
                    except BaseException:
                        self.close();raise
                yield self.shared
            else:
                raise ValueError('Unsupported site domain: '+self.domain)
        finally:self.in_use=False

    def prepare_pair(self):
        """Initialize the batch's two sites without consuming an episode/reset."""
        if not self.paired or self.pair is not None:
            return False
        if self._pair_failure is not None:
            raise RuntimeError('Paired website initialization previously failed') from self._pair_failure
        from .alternating_sites import AlternatingSites
        from .reusable_content_site import ReusableContentSite
        try:
            generations=[0,0]
            def factory(slot):
                logs=self.logs/('instance-'+str(slot))/str(generations[slot])
                generations[slot]+=1
                if self.domain=='gitlab':
                    return self._new_gitlab_site(logs)
                if self.domain=='map':
                    return IsolatedMapQuerySite(self.root,logs,with_tiles=True,
                        with_geographic_baseline=True,track_changes=True,
            **self.map_environment_options,
                        **({'native_layer_refresh':True,'web_workers':0}if self.map_native_layers else {}),
                        **({'community_fixture':self.map_community_fixture}if self.map_community_fixture else {}))
                return ReusableContentSite(self.root,logs,self.domain,
                    **({'capture_mail':True}if self.shopping_capture_mail else {}))
            self.pair=AlternatingSites(factory,
                recreate_on=(MapStateChanged,) if self.domain=='map' else ()).__enter__()
        except BaseException as error:
            self._pair_failure=error;raise
        return True

    def _new_gitlab_site(self, logs):
        options=dict(reuse_state=True,reset_strategy='clone',prefetch_reset=True)
        if self.gitlab_cache_initialization is not None:
            options['initialization_profile']=self.gitlab_cache_initialization
        if self.gitlab_initial_profile is None:
            return IsolatedGitlabSite(self.root,logs,**options)
        from .gitlab_declared_profiles import new_site
        return new_site(self.root,logs,self.gitlab_initial_profile,**options)

    @property
    def paired(self):
        return 2 in (self.gitlab_instances,self.shopping_instances,self.reddit_instances,self.map_instances)

    @property
    def failed(self):
        return self._pair_failure is not None or (self.pair is not None and self.pair.failed)

    def close(self):
        if self.pair is not None:
            pair=self.pair;self.pair=None
            try:
                try:pair.close()
                finally:
                    from .io_utils import atomic_write_json
                    atomic_write_json(self.logs/'pipeline-timing.json',{'domain':self.domain,
                        'events':list(pair.events),'reset_failed':pair.failed})
            except BaseException as error:
                self._pair_failure=error;raise
        if self.shared is not None:
            site=self.shared;self.shared=None;site.__exit__(None,None,None)
