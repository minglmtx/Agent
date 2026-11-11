"""Persisted account settings, independent of the actor's proposed actions."""
from .site_database import select_rows
from .site_navigation_rules import valid_initial_page
from .site_query_rules import reference_fingerprint
VERSION='site-preferences-v1'
ADMISSION_VERSION='site-preferences-admission-v1'
FIELDS={'locale':'locale','night_mode':'nightMode','show_custom_stylesheets':'showCustomStylesheets','front_page':'frontPage_filterBy','open_external_links_in_new_tab':'openExternalLinksInNewTab','auto_fetch_submission_titles':'autoFetchSubmissionTitles','enable_post_previews':'enablePostPreviews','show_thumbnails':'showThumbnails','notify_on_reply':'notifyOnReply','notify_on_mentions':'notifyOnMentions','preferred_fonts':'preferredFonts','front_page_sort_mode':'frontPage_sortBy','timezone':'timezone','allow_private_messages':'allowPrivateMessages','poppers_enabled':'poppersEnabled','full_width_display_enabled':'fullWidthDisplayEnabled','submission_link_destination':'submissionLinkDestination'}


def native_choices(controls):
    """Allowed values come from the native preferences form, not a chosen answer."""
    by_id={r['id']:r for r in controls if r.get('id')};out={}
    for field,suffix in FIELDS.items():
        row=by_id['user_settings_'+suffix]
        if row['type']=='checkbox':out[field]={'type':'boolean'}
        elif row['type']=='select-one':out[field]={'type':'enum','values':sorted({x['value'] for x in row['options']})}
        elif field=='preferred_fonts' and row['type']=='text':out[field]={'type':'text'}
        else:raise ValueError('Unsupported native preference control')
    return out


def valid_choices(values,choices):
    if not isinstance(values,dict) or set(values)!=set(FIELDS) or set(choices)!=set(FIELDS):return False
    for key,spec in choices.items():
        value=values[key];kind=spec.get('type')
        if kind=='boolean' and type(value) is bool:continue
        if kind=='enum' and isinstance(value,str) and value in spec.get('values',[]):continue
        if kind=='text' and key=='preferred_fonts' and isinstance(value,str):continue
        return False
    return True


def expected_controls(c):
    if c['preferences'].get('mode')=='change_any':
        return {'no_op':'failure','unsaved':'failure','wrong_account':'failure','positive':'success','alternative_positive':'success','404':'failure'}
    return {'no_op':'failure','unsaved':'failure','wrong_setting':'failure','positive':'success','404':'failure'}


def preference_state(site,username):
    if site.domain!='reddit':raise ValueError('Preferences adapter not implemented for this website')
    quoted="'"+username.replace("'","''")+"'"
    rows=select_rows(site,'SELECT id,username,'+','.join(FIELDS)+' FROM users WHERE username='+quoted)
    if len(rows)!=1:raise ValueError('Account missing or ambiguous')
    row=rows[0];values={k:row[k] for k in FIELDS}
    # The empty fonts input can save either NULL or an empty string; both mean no preference.
    values['preferred_fonts']=values['preferred_fonts'] or ''
    return {'user_id':row['id'],'username':row['username'],'values':values}


def evaluate_preferences(contract,page,initial,final,*,site_origin,runtime_error=None):
    def unknown(why):return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':why}
    if runtime_error:return unknown('Runtime failure')
    if not initial or not final or not isinstance(final.get('values'),dict):return unknown('Missing account snapshot')
    if not isinstance(page,dict) or type(page.get('http_status')) is not int or not 200<=page['http_status']<500:return unknown('Missing page capture or server failure')
    spec=contract['preferences'];targets=spec['targets']
    if spec.get('mode')=='change_any':
        choices=spec.get('allowed_choices',{})
        if targets or not valid_choices(initial.get('values'),choices):raise ValueError('Invalid any-change preference baseline or contract')
        checks={'page_valid':valid_initial_page(page,site_origin=site_origin),
          'account_identity':final.get('username')==spec['username']==initial.get('username') and initial.get('user_id')==final.get('user_id'),
          'saved_settings_valid':valid_choices(final['values'],choices),
          'settings_changed':final['values']!=initial['values']}
        passed=all(checks.values())
        return {'version':VERSION,'status':'success' if passed else 'failure','reward':float(passed),'checks':checks,'reason':None}
    if spec.get('mode','targets')!='targets':raise ValueError('Unsupported preference mode')
    if not targets or any(k not in FIELDS or type(v) not in (str,bool) for k,v in targets.items()):raise ValueError('Unsupported preference condition')
    checks={'page_valid':valid_initial_page(page,site_origin=site_origin),
      'account_identity':final.get('username')==spec['username']==initial.get('username') and initial.get('user_id')==final.get('user_id'),
      'requested_settings_saved':all(type(final['values'].get(k)) is type(v) and final['values'].get(k)==v for k,v in targets.items()),
      'unrelated_settings_unchanged':{k:v for k,v in initial['values'].items() if k not in targets}=={k:v for k,v in final['values'].items() if k not in targets}}
    status='success' if all(checks.values()) else 'failure'
    return {'version':VERSION,'status':status,'reward':float(status=='success'),'checks':checks,'reason':None}


def contract_fingerprint(c):
    return reference_fingerprint({k:c.get(k) for k in ('task_id','source_task_id','domain','goal','start_path','preferences','heldout_quarantine','start_revision')})


def require_preferences_admission(c,p):
    if c.get('heldout_quarantine'):raise ValueError('Heldout task cannot enter development tests')
    if p.get('admission_version')!=ADMISSION_VERSION or p.get('contract_fingerprint')!=contract_fingerprint(c):raise ValueError('Stale preference proof')
    cycles=p.get('cycles',[]);expected=expected_controls(c)
    if not p.get('passed') or len(cycles)!=2 or any(not r.get('passed') or not r.get('restored') or r.get('checks')!=expected for r in cycles):raise ValueError('Two preference control/reset cycles required')
    if not cycles[0].get('initial_state') or cycles[0]['initial_state']!=cycles[1].get('initial_state'):raise ValueError('Preference reset mismatch')
    if c['preferences'].get('mode')=='change_any' and any(
        r.get('native_choices')!=c['preferences'].get('allowed_choices') or not valid_choices(r['initial_state'].get('values'),r['native_choices'])
        for r in cycles):raise ValueError('Native preference range not verified')


def preferences_feedback(judgment):
    meanings={'page_valid':'The final page is valid on the task website.','account_identity':'The saved settings belong to the requested account.',
      'saved_settings_valid':'Saved preference values are valid choices in the native settings form.',
      'settings_changed':'At least one account preference has actually changed from its initial saved value.',
      'requested_settings_saved':'The requested account settings have been saved.','unrelated_settings_unchanged':'Unrelated account settings remain unchanged.'}
    return {'status':judgment['status'],'reward':judgment['reward'],'reason':judgment.get('reason'),
      'checks':[{'name':k,'passed':v,'condition':meanings[k]} for k,v in judgment['checks'].items()],'action_sequence_provided':False}
