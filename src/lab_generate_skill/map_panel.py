"""Native map panel terminal evidence; no task navigation in the actor runtime."""
import hashlib
import math
from pathlib import Path
from urllib.parse import urlsplit


READ=r'''() => {
 const visible=e=>!!e && !!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
 const layers=document.querySelector('.layers-ui'), share=document.querySelector('.share-ui');
 const format=document.querySelector('#mapnik_format');
 const from=[...document.querySelectorAll('input[name="route_from"]')].find(visible);
 const to=[...document.querySelectorAll('input[name="route_to"]')].find(visible);
 const mode=[...document.querySelectorAll('select.routing_engines')].find(visible);
 const exportForm=[...document.querySelectorAll('form.export_form')].find(visible);
 return {map_visible:visible(document.querySelector('#map')),
   layers_visible:visible(layers),
   layer_labels:layers?[...layers.querySelectorAll('.base-layers label')].filter(visible).map(e=>e.innerText.trim()):[],
   share_visible:visible(share),format_visible:visible(format),format_value:format?.value||'',
   format_options:format?[...format.options].map(o=>({value:o.value,text:o.text})):[],
   directions_visible:!!from&&!!to&&!!mode,
   direction_modes:mode?[...mode.options].map(o=>o.text):[],
   export_form:exportForm?{visible:true,action:exportForm.getAttribute('action'),method:exportForm.method,
     format:exportForm.querySelector('input[name="format"]')?.value,
     bounds:Object.fromEntries(['minlon','minlat','maxlon','maxlat'].map(name=>{const e=exportForm.querySelector('[name="'+name+'"]');return [name,{visible:visible(e),value:e?.value??null}]})),
     selection_control:visible(exportForm.querySelector('#drag_box')),
     selection_active:visible(document.querySelector('.leaflet-locationfilter-handle')),
     too_large:visible(exportForm.querySelector('#export_osm_too_large')),
     submit_visible:visible(exportForm.querySelector('#export_commit input[type="submit"]'))}:null};
}'''


def read_map_panel(page):
    # Native export values are populated after the sidebar response. Do not
    # wait on error/login pages or on pages without the native form.
    if page.locator('form.export_form:visible').count():
        page.wait_for_function("() => ['minlon','minlat','maxlon','maxlat'].every(n=>{const e=document.querySelector('form.export_form [name=\"'+n+'\"]');return e&&e.value.trim()!==''&&Number.isFinite(Number(e.value))})",timeout=10000)
    return page.evaluate(READ)


def verify_panel_source(root,spec):
    base=Path(root)/'datasets/webarena-map-frontend/openstreetmap-website'
    for row in spec['source_evidence']:
        path=Path(row['relative_path'])
        if path.is_absolute() or '..' in path.parts:raise ValueError('Invalid native source path')
        if hashlib.sha256((base/path).read_bytes()).hexdigest()!=row['sha256']:
            raise ValueError('Native map panel source changed')


def panel_checks(spec,state):
    fields=('map_visible','layers_visible','share_visible','format_visible','directions_visible')
    if not isinstance(state,dict) or any(type(state.get(k)) is not bool for k in fields):
        raise ValueError('Missing native map panel capture')
    if any(not isinstance(state.get(k),list) for k in ('layer_labels','format_options','direction_modes')):
        raise ValueError('Malformed map panel content')
    checks={'map_view_present':state['map_visible']}
    kind=spec['kind']
    if kind=='layers_catalog':
        checks.update(requested_panel_visible=state['layers_visible'],
                      panel_content_matches=sorted(state['layer_labels'])==sorted(spec['layer_labels']) and bool(spec['layer_labels']))
    elif kind in ('download_formats','image_format'):
        checks.update(requested_panel_visible=state['share_visible'] and state['format_visible'],
                      panel_content_matches=state['format_options']==spec['format_options'])
        if kind=='image_format':checks['requested_format_selected']=state['format_value']==spec['value']
    elif kind=='directions_form':
        checks.update(requested_panel_visible=state['directions_visible'],
                      panel_content_matches=sorted(state['direction_modes'])==sorted(spec['direction_modes']) and bool(spec['direction_modes']))
    elif kind=='export_form':
        form=state.get('export_form')
        checks.update(requested_panel_visible=isinstance(form,dict) and form.get('visible') is True,
                      export_form_ready=False)
        if isinstance(form,dict):
            try:
                fields=form['bounds'];names=('minlon','minlat','maxlon','maxlat')
                values=[float(fields[n]['value']) for n in names]
                west,south,east,north=values
                action=urlsplit(form['action'])
                checks['export_form_ready']=(action.path=='/export/finish' and not action.scheme and not action.netloc
                    and form.get('method','').lower()=='post' and form.get('format')=='osm'
                    and all(fields[n].get('visible') is True for n in names)
                    and all(math.isfinite(v) for v in values) and -180<=west<east<=180 and -90<=south<north<=90
                    and (form.get('selection_control') is True or form.get('selection_active') is True)
                    and (form.get('too_large') is True or form.get('submit_visible') is True))
            except (KeyError,TypeError,ValueError):pass
    else:raise ValueError('Unsupported map panel completion')
    return checks


def open_panel_control(page,spec):
    """CPU positive control only. Never called during actor execution."""
    kind=spec['kind']
    if kind in ('directions_form','export_form'):return
    panel='layers' if kind=='layers_catalog' else 'share'
    page.locator('.control-'+panel+' .control-button').click()
    page.locator('.'+panel+'-ui:visible').wait_for(timeout=10000)
    if kind=='image_format':page.locator('#mapnik_format:visible').select_option(spec['value'])


FEEDBACK={
    'map_view_present':'The native map view is available.',
    'requested_panel_visible':'The requested native map controls are displayed.',
    'panel_content_matches':'The displayed controls contain the expected native options.',
    'requested_format_selected':'The requested image format is selected.',
    'export_form_ready':'The native export form displays initialized area fields and its available operation or area-size warning.',
}
