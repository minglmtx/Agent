"""Declared unsaved UI state, identical for positive controls and actor trials."""

def initialize(page,binding):
    spec=binding['spec']
    if spec.get('initial_ui_steps'):
        from admin_ui_controls import execute
        execute(page,spec['initial_ui_steps'])
    if spec.get('initial_hide_column'):
        binding['default_columns']=[' '.join(x.inner_text().split()) for x in page.locator('table.data-grid:visible thead th:visible').all()]
        toggle=page.locator('.admin__data-grid-action-columns > button:visible').first;toggle.click()
        label=page.locator('.admin__data-grid-action-columns-menu:visible').get_by_text(spec['initial_hide_column'],exact=True)
        ident=label.evaluate('(e)=>e.closest("label").htmlFor');page.locator('[id="'+ident+'"]:visible').uncheck();toggle.click()
    setup=spec.get('initial_form')
    if setup:
        fields={k:page.locator('[name="'+k+'"]') for k in setup}
        binding['form_defaults']={k:f.input_value() for k,f in fields.items()}
        for key,value in setup.items():fields[key].fill(str(value));fields[key].press('Tab')
    if spec.get('initial_visible_column'):
        toggle=page.locator('.admin__data-grid-action-columns > button:visible').first
        toggle.click()
        label=page.locator('.admin__data-grid-action-columns-menu:visible').get_by_text(spec['initial_visible_column'],exact=True)
        ident=label.evaluate('(e)=>e.closest("label").htmlFor')
        page.locator('[id="'+ident+'"]:visible').check();toggle.click()
