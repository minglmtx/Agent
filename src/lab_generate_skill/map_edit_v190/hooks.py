"""Passive save receipts and actual issued page text; one terminal judgment."""
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlsplit
import json
from edit_capture import Capture
from edit_protection import capture,check
from edit_judge import evaluate
from lab_generate_skill.io_utils import atomic_write_json as save
from lab_generate_skill.map_account_initial import observe_account_start
from .profile import NativeEditSite

VERSION='native-node-note-save-readback-v190'

class NativeEditHooks:
 def __init__(self,candidate,directory,*,baseline):
  self.c=deepcopy(candidate);self.directory=Path(directory);self.expected=deepcopy(baseline)
  self.site=self.context=self.page=self.observer=None
  self.before=self.after=self.initial=self.terminal=None
  self.witness=None;self.issued=[];self.received={};self.capture_error=None
  self.closed=False;self.scored=False
 def prepare(self,site,user):
  if self.site is not None or not isinstance(site,NativeEditSite)or user is not None:
   raise ValueError('Exact dedicated native editor factory required')
  value=capture(site,self.c)
  if value!=self.expected:raise ValueError('Native editor baseline differs from qualified cold factories')
  self.site=site;self.before=value
  self.directory.mkdir(parents=True,exist_ok=True)
  save(self.directory/'edit-baseline.json',value)
 def attach(self,context):
  if self.site is None or self.context is not None:raise ValueError('One bound browser context required')
  self.context=context
  # Context supports the same passive request events as Page, retaining all
  # same-origin node documents even when the actor opens another tab.
  self.observer=Capture(context,self.site.url)
 def observe_initial(self,page):
  if self.initial is not None or page.context is not self.context:raise ValueError('One actual original start required')
  health=json.loads((self.directory/'initial-page-health.json').read_text())
  if health['url']!=page.url or health['http_status']!=200 or health['login_page']or health['error_page']:
   raise ValueError('Healthy original signed-out map start required')
  if page.get_by_role('link',name='Log In',exact=True).count()!=1:
   raise ValueError('Original signed-out account state required')
  self.initial=observe_account_start(page,self.c,self.site.url,health['http_status']);self.page=page
  save(self.directory/'edit-initial.json',dict(health=health,initial=self.initial,actor_actions=0,browser_authenticated_privately=False))
 def record(self,page):
  if page.context is not self.context:raise ValueError('Observed page belongs to another browser context')
  self.page=page
 def acknowledge_issued(self,actual_ax):
  if self.closed or self.page is None or self.initial is None or not isinstance(actual_ax,str):
   raise ValueError('Actual issued native page text required')
  u,root=urlsplit(self.page.url),urlsplit(self.site.url)
  if (u.scheme,u.netloc)!=(root.scheme,root.netloc)or u.path!='/node/666':return
  try:
   if len(self.issued)>=128:raise ValueError('Bounded public readback capture exceeded')
   self.observer.observed(dict(url=self.page.url,axtree_txt=actual_ax))
   event=next(e for e in reversed(self.observer.events)if e['kind']=='reopened')
   seq=event['sequence'];values=self.received.setdefault(seq,[])
   values.append(actual_ax)
   # Keep every actual issued observation for this request. Subsequent scrolling
   # cannot erase a completed public read. No expected text is inserted or used
   # to select which observations to retain; this is private evidence only.
   event['public_observation']='\n\n'.join(values)
   self.issued.append(dict(sequence=seq,url=self.page.url,actual_ax=actual_ax))
  except Exception as exc:self.capture_error=type(exc).__name__+': '+str(exc)
 def capture_terminal(self,page,terminal):
  if self.terminal is not None or page.context is not self.context or terminal.get('url')!=page.url:
   raise ValueError('One actual bound terminal page required')
  self.terminal=deepcopy(terminal)
  try:
   self.after=capture(self.site,self.c);self.witness=self.observer.witness()
  except Exception as exc:self.capture_error=type(exc).__name__+': '+str(exc)
  save(self.directory/'edit-terminal-capture.json',dict(baseline=self.before,state=self.after,witness=self.witness,
   initial=self.initial,terminal=self.terminal,actual_issued_readbacks=self.issued,capture_error=self.capture_error))
 def close(self):
  if self.observer is not None and not self.closed:self.observer.close()
  self.closed=True
 def score_terminal(self,site,terminal,*,runtime_error=None):
  if site is not self.site or self.scored or not self.closed or terminal!=self.terminal:
   raise ValueError('One closed native terminal lifecycle required')
  self.scored=True;integrity=False
  try:
   if self.after is None or self.witness is None or self.initial is None:
    raise ValueError('Incomplete native terminal capture')
   if capture(site,self.c)!=self.after:raise ValueError('Native state changed after terminal capture')
   integrity=check(self.before,self.after)['passed']
   judgment=evaluate(self.c,self.before,self.after,self.witness,capture_error=self.capture_error)
  except Exception as exc:
   judgment=dict(status='unknown',reward=None,checks={},reason=type(exc).__name__+': '+str(exc))
  judgment=dict(judgment,version=VERSION)
  save(self.directory/'edit-terminal-judgment.json',dict(judgment=judgment,native_protection_verified=integrity,
   runtime_error=runtime_error,actual_issued_readback_count=len(self.issued),terminal_only=True))
  return judgment,integrity
