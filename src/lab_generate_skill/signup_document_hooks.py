"""Passive document-start support for native signup, preserving map-start behavior."""
from urllib.parse import urlsplit,urldefrag
from lab_generate_skill.map_account_observation import AccountObservationHooks
from lab_generate_skill.map_account_initial import observe_account_start
from lab_generate_skill.map_existing_account_observation import require_anonymous
from lab_generate_skill.map_account_readout import session_identity
from lab_generate_skill.io_utils import atomic_write_json as save

class SignupDocumentHooks(AccountObservationHooks):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.document_status={}

    def attach(self,context):
        super().attach(context)
        context.on('response',self._response)

    def _response(self,response):
        if response.request.is_navigation_request() and response.frame.parent_frame is None:
            self.document_status[urldefrag(response.url)[0]]=response.status

    def observe_initial(self,page):
        if self.site is None or self.page is not None or self.initial is not None or page.context is not self.context:
            raise ValueError('One bound signup initial page required')
        if urlsplit(self.candidate['start_path']).path in ('/','/search','/directions'):
            return super().observe_initial(page)
        state=observe_account_start(page,self.candidate,self.site.url,self.document_status.get(urldefrag(page.url)[0]))
        anonymous=session_identity(self.context,self.site.url)
        require_anonymous(anonymous,self.site.url)
        self.initial=state;self.initial_session=anonymous;self.page=page;self.events.append('observe_initial')
        save(self.directory/'account-initial.json',dict(original_start=state,account=self.before,session=anonymous,
            guard=self.guard_before,protected_users=self.users_before))

    def close(self):
        if not self.closed and self.context is not None:
            self.context.remove_listener('response',self._response)
        super().close()
