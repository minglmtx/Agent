"""One-source registration/confirmation goal; runtime integrity remains required."""
from lab_generate_skill.map_account_terminal import _record
from lab_generate_skill.map_account_profile import validate_account
from lab_generate_skill.map_account_mail import confirmation_from_message
VERSION='native-register-confirm-terminal-v183'
SOURCE='01ccdfd9a75d86f713e4'
def evaluate_registration(spec,*,initial,final,runtime_error=None,capture_error=None,integrity=True,confirmation_messages=None,origin=None):
 if spec.get('family')!='account_signup'or spec.get('completion_semantics')!='register_confirm_account_v1':raise ValueError('Explicit registration-confirmation contract required')
 target=validate_account(spec.get('public_account',{}))
 checks={}
 def result(status,reason):return dict(version=VERSION,status=status,reward={'success':1.,'failure':0.,'unknown':None}[status],checks=checks,reason=reason,terminal_session_scored=False)
 if runtime_error or capture_error or integrity is not True:return result('unknown','Runtime, capture or native integrity unavailable.')
 try:before,after=_record(initial),_record(final)
 except (ValueError,TypeError,KeyError):return result('unknown','Native account readout incomplete.')
 if before is not None:return result('unknown','Registration target was already present initially.')
 checks['new_target_account_saved']=after is not None
 checks['target_identity_matches']=after is not None and all(after[k]==target[k]for k in ('email','display_name'))
 checks['native_email_confirmation_complete']=after is not None and after['email_valid']is True and after['status']in('active','confirmed')
 if not all(checks.values()):return result('failure','Saved account identity and native confirmation checked.')
 if not isinstance(confirmation_messages,list)or len(confirmation_messages)>128 or any(not isinstance(b,bytes)or len(b)>1024*1024 for b in confirmation_messages):return result('unknown','Native confirmation mail evidence unavailable.')
 bound=[]
 for payload in confirmation_messages:
  try:bound.append(confirmation_from_message(payload,recipient=target['email'],display_name=target['display_name'],origin=origin))
  except (ValueError,TypeError,AttributeError,LookupError):continue
 if not bound:return result('unknown','No archived native confirmation message matches the saved account and origin.')
 checks['native_confirmation_mail_bound']=True
 return result('success','Saved identity, native confirmation and matching real mail checked.')
