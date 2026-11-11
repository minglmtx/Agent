"""Ordinary source-start browser lifecycle for explicit local node editing."""
from copy import deepcopy
import json
from pathlib import Path
from urllib.parse import urlsplit
from . import map_node_task as task
from .map_node_write_audit import read as read_audit
from .map_node_readout import capture
from .map_reset_guard import STATE_SQL,checked_state
from .map_editor_navigation import authenticate
from .map_candidate_start import InitialStartHooks
from .io_utils import atomic_write_json


class NodeEpisodeHooks(InitialStartHooks):
    def __init__(self,candidate,directory,*,profile):
        task.environment_key(candidate,profile)
        super().__init__(deepcopy(candidate),None)
        self.directory=Path(directory);self.profile=deepcopy(profile)
        self.initialization=None;self.browser_initialized=False;self.closed=self.scored=False

    def prepare(self,site,username):
        if self.site is not None or username is not None:raise ValueError('One local node episode required')
        from browsergym.core import _get_global_playwright
        browser=_get_global_playwright().chromium.launch(headless=True)
        try:self.initialization=task.prepare(site,self.candidate,self.profile,browser=browser)
        finally:browser.close()
        spec=task.resolve_spec(self.candidate,self.initialization)
        if spec['operation']=='update':
            before=self.initialization['snapshot'];empty_audit=read_audit(site)
            initial_judgment=task.evaluate_set(self.candidate,self.initialization,empty_audit,before)
            if initial_judgment['status']!='failure':raise ValueError('Declared update goal is already satisfied or malformed')
        self.site=site;self.events.append('prepare')
        atomic_write_json(self.directory/'node-initialization.json',self.initialization)

    def initialize_browser(self,page):
        if self.browser_initialized or self.site is None or page.context is not self.context:
            raise ValueError('Authenticate only once before the original first document')
        page.context.set_extra_http_headers({'Accept-Language':'en-US'})
        authenticate(page,self.site)
        self.site.reset_guard.require_unchanged()
        self.browser_initialized=True;self.events.append('initialize_browser')

    def observe_initial(self,page):
        if not self.browser_initialized or self.initial is not None or page.context is not self.context:
            raise ValueError('Original authenticated initial page required')
        expected=urlsplit(self.site.url+self.candidate['start_path']);actual=urlsplit(page.url)
        if (actual.scheme,actual.netloc,actual.path,actual.query)!=(expected.scheme,expected.netloc,expected.path,expected.query):
            raise ValueError('Original source document changed')
        if expected.path=='/':
            super().observe_initial(page)
        else:
            if actual.fragment!=expected.fragment:raise ValueError('Original fragment changed')
            self.initial=dict(url=page.url);self.events.append('observe_initial')
        self.site.reset_guard.require_unchanged()
        atomic_write_json(self.directory/'node-initial-page.json',self.initial)

    def close(self):
        if not self.closed:super().close();self.closed=True

    def score_terminal(self,site,terminal,*,runtime_error=None):
        if site is not self.site or self.scored or not self.closed or terminal!=self.terminal or self.terminal is None:
            raise ValueError('One completed bound node episode required')
        self.scored=True;audit=final=guard=None;integrity=False
        try:
            guard=checked_state(json.loads(site.app_sql(STATE_SQL)))
            audit=read_audit(site);spec=task.resolve_spec(self.candidate,self.initialization)
            maximum=self.initialization['snapshot']['max_node_id']
            ids=[spec['node_id']]if spec['operation']=='update'else [x for x in audit['node_ids']if x>maximum]
            final=capture(site,node_ids=ids)if ids else capture(site,after_node_id=maximum)
            integrity=True
            judgment=task.evaluate_set(self.candidate,self.initialization,audit,final,integrity=True,runtime_error=runtime_error)
        except (OSError,ValueError,KeyError,RuntimeError)as exc:
            judgment=dict(version='native-map-node-task-v1',status='unknown',reward=None,checks={},reason='Native write/readback capture failed: '+type(exc).__name__)
        # Never clear guard markers or audit rows. SiteWorker verifies the full
        # state and cold-recreates a dirty instance before the next episode.
        self.events.append('score_terminal')
        atomic_write_json(self.directory/'node-terminal.json',dict(events=self.events,terminal=terminal,
            audit=audit,final=final,guard=guard,integrity=integrity,judgment=judgment,
            dirty_state_not_cleared=True))
        return judgment,integrity
