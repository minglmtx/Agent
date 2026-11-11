"""Observe a native form's presence; never equate opening it with saving it."""
FEEDBACK={'requested_form_visible':'The requested form and its required controls are displayed together.',
          'requested_form_values':'The requested text is entered in the corresponding visible form fields.'}

FORM_DESCRIPTIONS=r'''
  const visible=e=>!!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
  const describe=(f,wanted=[])=>({
    fields:[...f.elements].filter(e=>visible(e)&&e.name&&e.type!=='hidden').map(e=>e.name),
    submits:[...f.querySelectorAll('button[type=submit],input[type=submit]')].filter(visible).map(e=>(e.tagName==='INPUT'?e.value:e.innerText).trim()),
    ...(wanted.length ? {values:wanted.map(name=>({name, values:[...f.elements]
      .filter(e=>visible(e)&&e.name===name&&!e.disabled&&
        (e.tagName==='TEXTAREA'||(e.tagName==='INPUT'&&['text','search','url','email','tel','number'].includes(e.type))))
      .map(e=>e.value)}))} : {})
  });
'''


def validate(spec):
    if (set(spec) not in ({'fields','submit_text'},{'fields','submit_text','values'}) or not isinstance(spec['fields'],list) or not spec['fields']
        or len(spec['fields'])!=len(set(spec['fields']))
        or any(not isinstance(s,str) or not s for s in spec['fields'])
        or not isinstance(spec['submit_text'],str) or not spec['submit_text']):
        raise ValueError('Invalid form-presence contract')
    if 'values' in spec and (not isinstance(spec['values'],dict) or not spec['values']
            or not set(spec['values']) <= set(spec['fields'])
            or any(not isinstance(v,str) or not v for v in spec['values'].values())):
        raise ValueError('Explicit nonempty values must refer to required fields')


def read_visible_forms(page,spec=None):
    if spec is not None:validate(spec)
    wanted=list((spec or {}).get('values',{}))
    return page.evaluate('wanted => {'+FORM_DESCRIPTIONS+'''
      return [...document.forms].filter(visible).map(f=>describe(f,wanted));
    }''',wanted)


def form_checks(spec,state):
    validate(spec)
    if not isinstance(state,list):raise ValueError('Native form capture is missing')
    matches=[]
    for row in state:
        if not isinstance(row,dict) or not all(isinstance(row.get(k),list) and all(isinstance(s,str) for s in row[k]) for k in ('fields','submits')):
            raise ValueError('Malformed native form capture')
        matches.append(all(row['fields'].count(field)==1 for field in spec['fields'])
                       and row['submits'].count(spec['submit_text'])==1)
    checks={'requested_form_visible':sum(matches)==1}
    if 'values' in spec:
        checks['requested_form_values']=False
        if sum(matches)==1:
            row=state[matches.index(True)]
            if not isinstance(row.get('values'),list):raise ValueError('Requested field values were not captured')
            captured=row['values']
            if any(not isinstance(r,dict) or not isinstance(r.get('name'),str) or not isinstance(r.get('values'),list) for r in captured):
                raise ValueError('Malformed requested field capture')
            checks['requested_form_values']=(len(captured)==len(spec['values']) and
                all(sum(r['name']==name and r['values']==[value] for r in captured)==1 for name,value in spec['values'].items()))
    return checks


def fill_form_control(page,spec,*,wrong=False):
    """Private positive/negative control using native editable inputs, not actor advice."""
    validate(spec)
    if not spec.get('values'):raise ValueError('No requested form values')
    matches=[]
    for form in page.locator('form').all():
        if not form.is_visible():continue
        row=form.evaluate('(f)=>{'+FORM_DESCRIPTIONS+'return describe(f);}')
        if form_checks({k:spec[k] for k in ('fields','submit_text')},[row])['requested_form_visible']:
            matches.append(form)
    if len(matches)!=1:raise ValueError('Native input control is ambiguous')
    for i,(name,value) in enumerate(spec['values'].items()):
        # CSS string escaping: field names are data, never selectors or script.
        escaped=''.join('\\'+format(ord(c),'x')+' ' for c in name)
        matches[0].locator('[name="'+escaped+'"]:visible').fill('incorrect-control-value' if wrong and i==0 else value)


def hide_form_control(page,spec):
    """CPU negative fixture only. No selector or action sent to the actor."""
    validate(spec)
    changed=page.evaluate('spec=>{'+FORM_DESCRIPTIONS+'''
      // Hidden tabs may contain forms with the same field names. Match the
      // same visible controls and submit label used by the actual evaluator.
      const forms=[...document.forms].filter(visible).filter(f=>{
        const row=describe(f);
        return spec.fields.every(name=>row.fields.filter(n=>n===name).length===1)
          && row.submits.filter(t=>t===spec.submit_text).length===1;
      });
      if(forms.length!==1)return false;
      forms[0].style.display='none';return true;
    }''',spec)
    if not changed:raise ValueError('Native negative form fixture is ambiguous')
