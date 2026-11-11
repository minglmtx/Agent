"""Final native group-form selections, distinct from saved group creation.

Only explicit field-selection goals are supported. The reader never changes the
page, and expected field values are private to scoring, not actor input.
"""
FIELDS = {
    'visibility': ('group[visibility_level]', ('0', '10', '20')),
    'users': ('group[setup_for_company]', ('true', 'false')),
    'purpose': ('group[jobs_to_be_done]', ('', 'basics', 'move_repository', 'code_storage', 'exploring', 'ci', 'other')),
}
FEEDBACK = {
    'group_creation_form_visible': 'The group creation form is displayed.',
    'requested_group_control_present': 'The requested group setting is available on this form.',
    'requested_group_setting_selected': 'The group setting has the value requested by the task.',
}


def validate(reference):
    if set(reference) != {'field', 'value'} or reference['field'] not in FIELDS:
        raise ValueError('Unsupported group-form condition')
    if reference['value'] not in FIELDS[reference['field']][1] or reference['value']=='':
        raise ValueError('Unsupported target setting')


def read_group_form(page):
    return page.evaluate('''() => {
      const name = document.querySelector('input[name="group[name]"]');
      const visible = e => !!e && !!e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden';
      const form = name?.closest('form');
      const present = visible(name) && !!form && new URL(form.action, location.href).pathname === '/groups';
      const fields = {};
      if (present) for (const key of ['group[visibility_level]', 'group[setup_for_company]', 'group[jobs_to_be_done]']) {
        const controls = [...form.elements].filter(e => e.name === key && visible(e) && !e.disabled && e.type !== 'hidden');
        const select = controls.filter(e => e.tagName === 'SELECT');
        if (select.length === 1) fields[key] = {kind: 'select', values: [...select[0].options].filter(o => !o.disabled).map(o => o.value), selected: [...select[0].selectedOptions].map(o => o.value)};
        else if (controls.length && controls.every(e => e.type === 'radio')) fields[key] = {kind: 'radio', values: controls.map(e => e.value), selected: controls.filter(e => e.checked).map(e => e.value)};
      }
      return {form_visible: !!present, fields};
    }''')


def form_checks(reference, observed):
    validate(reference)
    if not isinstance(observed, dict) or type(observed.get('form_visible')) is not bool or not isinstance(observed.get('fields'),dict):
        raise ValueError('Missing or malformed group-form capture')
    checks={'group_creation_form_visible':observed['form_visible']}
    if not observed['form_visible']:return checks
    name, allowed=FIELDS[reference['field']]
    field=observed['fields'].get(name)
    if field is None:
        checks['requested_group_control_present']=False
        return checks
    if (field.get('kind') not in ('radio','select') or not isinstance(field.get('values'),list)
        or not isinstance(field.get('selected'),list) or any(v not in allowed for v in field['values'])
        or any(v not in field['values'] for v in field['selected']) or len(field['selected'])>1):
        raise ValueError('Malformed native group control')
    checks['requested_group_control_present']=reference['value'] in field['values']
    checks['requested_group_setting_selected']=field['selected']==[reference['value']]
    return checks


def set_control_for_probe(page, reference, *, wrong=False):
    """CPU fixture only: use native labels/options; never called by actor."""
    validate(reference)
    name=page.locator('input[name="group[name]"]:visible')
    if name.count()==0:
        page.locator('a[href="#create-group-pane"]').click()
        name.wait_for(state='visible')
    field, allowed=FIELDS[reference['field']]
    value=next(v for v in allowed if v!=reference['value']) if wrong else reference['value']
    if reference['field']=='purpose':
        page.locator('select[name="'+field+'"]:visible').select_option(value)
    else:
        control=page.locator('input[name="'+field+'"][value="'+value+'"]')
        label=page.locator('label[for="'+control.get_attribute('id')+'"]')
        label.click()
        if not control.is_checked():raise ValueError('Native label did not select group setting')
