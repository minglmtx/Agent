"""Passive ordinary-runner hooks for declared existing-account login tasks.

Native login controls have verified this fixture does not require persistent
writes. Session readout is an independent native GET in the actor's context;
the hook never supplies credentials to a form or authenticates the browser.
"""
from copy import deepcopy
from pathlib import Path
from urllib.parse import urldefrag,urlsplit
import json
from .map_candidate_start import InitialStartHooks
from .map_account_initial import observe_account_start
from .map_account_readout import account_snapshot,session_identity
from .map_account_terminal import evaluate_account
from .map_account_observation import protected_users
from .map_reset_guard import STATE_SQL,checked_state,persistent_files
from .io_utils import atomic_write_json as save

VERSION='native-existing-account-terminal-v1'


def require_anonymous(session,origin):
    actual=urlsplit(session.get('url',''));expected=urlsplit(origin)
    if (session.get('http_status')!=200 or session.get('native_settings_form')is not False
            or (actual.scheme,actual.netloc)!=(expected.scheme,expected.netloc) or actual.path!='/login'):
        raise ValueError('Login task must begin with a verified anonymous native session')


def unchanged_login_state(before,after,*,files_unchanged,users_unchanged):
    before,after=checked_state(before),checked_state(after)
    return (not before['changed']and not after['changed']and before==after
            and files_unchanged is True and users_unchanged is True)


class ExistingAccountObservationHooks(InitialStartHooks):
    def __init__(self,candidate,directory,*,baseline):
        if candidate.get('candidate_completion',{}).get('family')!='account_login':
            raise ValueError('Declared existing-account login contract required')
        super().__init__(deepcopy(candidate),None)
        self.directory=Path(directory);self.baseline=baseline
        self.page=self.before=self.after=self.session=None
        self.capture_error=None;self.closed=self.scored=False;self.document_status={}

    def prepare(self,site,username):
        if self.site is not None or username is not None or site.domain!='map' or site.account!=self.candidate['candidate_completion']['public_account']:
            raise ValueError('Matching signed-out existing-account site required')
        site.reset_guard.require_unchanged();site.require_accounts_unchanged()
        if site.fingerprint()!=self.baseline:raise ValueError('Existing-account fixture baseline changed')
        self.before=account_snapshot(site,site.account['email'])
        row=self.before['target'];account=site.account
        if not row or any(row[k]!=account[k]for k in ('email','display_name')) or row['email_valid']is not True or row['status']not in ('active','confirmed'):
            raise ValueError('Declared confirmed account missing at initialization')
        self.guard_before=checked_state(json.loads(site.app_sql(STATE_SQL)))
        self.files_before=persistent_files(site.state/'frontend/app');self.users_before=protected_users(site)
        self.site=site;self.events.append('prepare')

    def attach(self,context):
        super().attach(context)
        context.on('response',self._response)

    def _response(self,response):
        if response.request.is_navigation_request() and response.frame.parent_frame is None:
            self.document_status[urldefrag(response.url)[0]]=response.status

    def observe_initial(self,page):
        if self.site is None or self.page is not None or page.context is not self.context:
            raise ValueError('One bound login initial page required')
        status=self.document_status.get(urldefrag(page.url)[0])
        self.initial=observe_account_start(page,self.candidate,self.site.url,status)
        self.initial_session=session_identity(self.context,self.site.url)
        require_anonymous(self.initial_session,self.site.url)
        self.page=page;self.events.append('observe_initial')
        save(self.directory/'account-initial.json',dict(original_start=self.initial,account=self.before,
            session=self.initial_session,guard=self.guard_before,protected_users=self.users_before))

    def capture_terminal(self,page,terminal):
        if self.closed or self.scored or page is not self.page:raise ValueError('Bound actor terminal required')
        super().capture_terminal(page,terminal)
        try:
            self.session=session_identity(self.context,self.site.url)
            self.after=account_snapshot(self.site,self.site.account['email'])
        except Exception as error:
            self.capture_error=type(error).__name__+': native login session/account capture unavailable'

    def close(self):
        if not self.closed:
            if self.context is not None:self.context.remove_listener('response',self._response)
            super().close();self.closed=True

    def score_terminal(self,site,terminal,*,runtime_error=None):
        if site is not self.site or self.scored or not self.closed or self.terminal is None or terminal!=self.terminal:
            raise ValueError('One matching score after actor context closure required')
        self.scored=True;self.events.append('score_terminal');integrity=False;protection={}
        try:
            after=checked_state(json.loads(site.app_sql(STATE_SQL)));protection['guard']=after
            protection['persistent_files_unchanged']=persistent_files(site.state/'frontend/app')==self.files_before
            protection['all_users_unchanged']=protected_users(site)==self.users_before
            integrity=unchanged_login_state(self.guard_before,after,
                files_unchanged=protection['persistent_files_unchanged'],users_unchanged=protection['all_users_unchanged'])
        except Exception as error:
            protection['error']=type(error).__name__+': native login protection unavailable'
        judgment=evaluate_account(self.candidate['candidate_completion'],initial=self.before,final=self.after,
            session=self.session,origin=site.url,runtime_error=runtime_error,capture_error=self.capture_error,integrity=integrity)
        judgment=dict(judgment,version=VERSION)
        save(self.directory/'account-terminal.json',dict(events=self.events,terminal=terminal,initial=self.before,
            final=self.after,session=self.session,protection=protection,capture_error=self.capture_error,
            integrity=integrity,judgment=judgment,cold_reset_required=not integrity))
        return judgment,integrity
