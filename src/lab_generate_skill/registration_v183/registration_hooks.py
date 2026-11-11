"""Keep ordinary source observations, write protection and mail checkpoints intact."""
from pathlib import Path
import hashlib,json
from lab_generate_skill.map_candidate_start import InitialStartHooks
from lab_generate_skill.map_account_readout import account_snapshot,session_identity
from lab_generate_skill.map_existing_account_observation import require_anonymous
from lab_generate_skill.signup_document_hooks import SignupDocumentHooks as ExistingHooks
from lab_generate_skill.io_utils import atomic_write_json as save
from .registration_terminal import evaluate_registration,SOURCE
class RegistrationHooks(ExistingHooks):
 def __init__(self,candidate,*args,**kwargs):
  if candidate.get('source_task_id')!=SOURCE or candidate.get('candidate_completion',{}).get('completion_semantics')!='register_confirm_account_v1':raise ValueError('Only the declared registration source may use this scope')
  super().__init__(candidate,*args,**kwargs)
  self.session_probe_error=None
 def observe_initial(self,page):
  super().observe_initial(page)
  self.initial_session=session_identity(self.context,self.site.url)
  require_anonymous(self.initial_session,self.site.url)
  save(self.directory/'registration-initial.json',dict(original_start=self.initial,initial_session=self.initial_session,account=self.before))
 def capture_terminal(self,page,terminal):
  if self.closed or self.scored or page is not self.page:raise ValueError('Bound registration terminal page required')
  InitialStartHooks.capture_terminal(self,page,terminal)
  try:self.after=account_snapshot(self.site,self.site.account['email'])
  except Exception as error:self.capture_error=type(error).__name__+': account capture unavailable'
  try:self.session=session_identity(self.context,self.site.url)
  except Exception as error:self.session_probe_error=type(error).__name__+': optional terminal session probe unavailable'

 def score_terminal(self,site,terminal,*,runtime_error=None):
  previous,integrity=super().score_terminal(site,terminal,runtime_error=runtime_error)
  raw=self.directory/'account-terminal.json';evidence=json.loads(raw.read_text());messages=[]
  try:
   for item in evidence['mail']:
    path=self.directory/item['artifact'];payload=path.read_bytes()
    if len(payload)!=item['bytes']or hashlib.sha256(payload).hexdigest()!=item['sha256']:raise ValueError('Archived native mail changed')
    messages.append(payload)
  except (OSError,ValueError,KeyError,TypeError)as error:self.capture_error=type(error).__name__+': native confirmation mail evidence unavailable'
  judgment=evaluate_registration(self.candidate['candidate_completion'],initial=self.before,final=self.after,runtime_error=runtime_error,capture_error=self.capture_error,integrity=integrity,confirmation_messages=messages,origin=site.url)
  save(self.directory/'registration-terminal.json',dict(scope='register_confirm_account_v1',source_task_id=SOURCE,judgment=judgment,legacy_session_sensitive_judgment=previous,native_evidence=dict(path=str(raw),sha256=hashlib.sha256(raw.read_bytes()).hexdigest()),session_scored=False,optional_session_probe_error=self.session_probe_error))
  return judgment,integrity
