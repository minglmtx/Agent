"""Native empty public-list navigation; never fabricate community content.

Only navigation goals enter this family. Reading an existing diary/trace or
creating/uploading one requires a different evaluator and a populated fixture.
"""
import hashlib
import math
from pathlib import Path
from urllib.parse import urlsplit,parse_qs

TABLES={'diary':'diary_entries','traces':'gpx_files','history':'changesets'}


def reference_count_sql(kind):
    if kind not in TABLES:raise ValueError('Unsupported public list')
    query='SELECT count(*) FROM public.'+TABLES[kind]
    if kind=='history':
        # changesets_controller.rb applies conditions_nonempty and, on the
        # map page, conditions_bbox. PBF import placeholder records need not
        # have a public change history or a geographic extent.
        query+=' WHERE num_changes > 0 AND min_lon IS NOT NULL AND max_lon IS NOT NULL AND min_lat IS NOT NULL AND max_lat IS NOT NULL'
    return query+';'


def verify_reference(site,spec):
    from .map_history_area import verify_reference as verify_area
    verify_area(spec)
    kind=spec.get('kind')
    if kind not in TABLES or spec.get('record_count')!=0:
        raise ValueError('Unvalidated public-list baseline')
    if int(site.app_sql(reference_count_sql(kind)))!=0:
        raise ValueError('Public list is populated; empty-list admission no longer applies')
    base=Path(site.root)/'datasets/webarena-map-frontend/openstreetmap-website'
    for row in spec['source_evidence']:
        p=Path(row['relative_path'])
        if p.is_absolute() or '..' in p.parts or hashlib.sha256((base/p).read_bytes()).hexdigest()!=row['sha256']:
            raise ValueError('Native public-list template changed')


def read_list_page(page):
    if urlsplit(page.url).path=='/history' and page.locator('#sidebar_content .changesets .loader:visible').count():
        from playwright.sync_api import TimeoutError
        try:
            page.wait_for_function("() => ![...document.querySelectorAll('#sidebar_content .changesets .loader')].some(e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden')",timeout=15000)
        except TimeoutError:pass  # Preserve loading evidence; never call it success.
    return page.evaluate(r'''() => {
      const visible=e=>!!e&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
      const texts=s=>[...document.querySelectorAll(s)].filter(visible).map(e=>e.innerText.trim());
      return {page_snapshot:{url:location.href,title:document.title,heading_texts:texts('h1,h2,h3'),page_text:document.body.innerText.slice(0,30000)},
        headings:texts('h1,h2'),empty_diary:texts('h4').includes('No diary entries'),
        empty_traces:texts('h2').includes('Nothing here yet'),
        diary_rows:[...document.querySelectorAll('.diary_entry')].filter(visible).length,
        trace_rows:[...document.querySelectorAll('#trace_list tbody tr')].filter(visible).length,
        active_tabs:texts('.nav-tabs .nav-link.active'),
        history:{paragraphs:texts('#sidebar_content .changesets p'),
          rows:document.querySelectorAll('#sidebar_content ol.changesets > li').length,
          loading:[...document.querySelectorAll('#sidebar_content .changesets .loader')].some(visible),
          active:!!document.querySelector('#history_tab.current'),
          feed:document.querySelector('link[type="application/atom+xml"]')?.getAttribute('href')||'',
          native_geo_uri:document.querySelector('#geo_uri')?.getAttribute('href')||'',
          native_long_link:document.querySelector('#long_link')?.getAttribute('href')||''},
        links:[...document.querySelectorAll('a[href]')].filter(visible).map(e=>({text:e.innerText.trim(),path:new URL(e.href,location.href).pathname}))};
    }''')


def list_checks(spec,state):
    if not isinstance(state,dict) or any(k not in state for k in ('headings','empty_diary','empty_traces','diary_rows','trace_rows','active_tabs','links')):
        raise ValueError('Missing native public-list state')
    kind=spec['kind']
    if spec.get('record_count')!=0 or kind not in TABLES:raise ValueError('Unsupported list reference')
    if kind=='history':
        h=state.get('history')
        if not isinstance(h,dict) or any(k not in h for k in ('paragraphs','rows','loading','active','feed','native_geo_uri','native_long_link')):
            raise ValueError('Missing native history list state')
        # Direct native navigation does not add the SPA's cosmetic .current
        # class. URL/title, loaded native list and geographic scope establish
        # identity; retain the class as a diagnostic only.
        checks={'native_public_list_identity':'Changesets' in state['headings'],
                'native_list_finished_loading':h['loading'] is False and h['rows']==0 and 'No changesets in this area.' in h['paragraphs'],
                'native_history_area_loaded':False}
        try:
            feed=urlsplit(h['feed']);values=parse_qs(feed.query)['bbox']
            if len(values)!=1:raise ValueError('Ambiguous history area')
            west,south,east,north=map(float,values[0].split(','))
            view=parse_qs(urlsplit(h['native_long_link']).fragment)['map']
            if len(view)!=1:raise ValueError('Ambiguous native view')
            zoom,lat,lon=map(float,view[0].split('/'))
            from .map_view import native_zoom
            native_zoom({'map_visible':True,**h})
            checks['native_history_area_loaded']=(feed.path=='/history/feed' and
                all(math.isfinite(v) for v in (west,south,east,north,zoom,lat,lon)) and
                -180<=west<east<=180 and -90<=south<north<=90 and west<=lon<=east and south<=lat<=north)
            if spec.get('initial_map'):
                from .map_history_area import area_matches
                checks['requested_history_area']=area_matches(spec,[zoom,lat,lon])
        except (ValueError,TypeError,KeyError):
            if spec.get('initial_map'):checks['requested_history_area']=False
        return checks
    if kind=='diary':
        return {'native_public_list_identity':"Users' Diaries" in state['headings'],
                'native_list_finished_loading':state['empty_diary'] is True and state['diary_rows']==0}
    return {'native_public_list_identity':'Public GPS Traces' in state['headings'] and 'All Traces' in state['active_tabs'],
            'native_list_finished_loading':state['empty_traces'] is True and state['trace_rows']==0,
            'native_trace_navigation_available':any(r['text']=='Upload a trace' and r['path']=='/traces/new' for r in state['links'])}


FEEDBACK={'native_public_list_identity':'The requested public community list is displayed.',
          'native_list_finished_loading':'The native list has finished loading and matches the stored empty baseline.',
          'native_history_area_loaded':'The history list has a valid native geographic scope matching the displayed map.',
          'requested_history_area':'The history is displayed for the originally requested map area.',
          'native_trace_navigation_available':'The public trace list contains its native navigation controls.'}
