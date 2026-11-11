"""Exact selected capsule passive readers, combined in one browser evaluation.

Literal parity is checked against the pinned capsule without importing its runtime.
This capture occurs after a unique public return; it is not that return itself.
"""

READ = r"""() => {
 const visible=e=>!!e&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden'&&getComputedStyle(e).display!=='none';
 const labels=scope=>[...document.querySelectorAll(scope+' label')].map(e=>{
  const input=e.querySelector('input');return {label:e.textContent.trim(),visible:visible(e),
    checked:input?input.checked:null,disabled:input?input.disabled:null,type:input?input.type:null};});
 const paths=[...document.querySelectorAll('.leaflet-overlay-pane svg path')].filter(visible).map(e=>({
  d:e.getAttribute('d')||'',stroke:e.getAttribute('stroke')||'',fill:e.getAttribute('fill')||'',
  class_name:e.getAttribute('class')||''}));
 return {url:location.href,map_visible:visible(document.querySelector('#map')),
  layers_visible:visible(document.querySelector('.layers-ui')),
  base:labels('.base-layers'),overlays:labels('.overlay-layers'),rendered_paths:paths,
  native_geo_uri:document.querySelector('#geo_uri')?.getAttribute('href')||null,
  native_long_link:document.querySelector('#long_link')?.getAttribute('href')||null,
  data_warning:visible(document.querySelector('#browse_status input[type=submit]')),
  async_loading:!!(window.jQuery&&jQuery.active>0),
  thunderforest_enabled:!!(window.OSM&&OSM.THUNDERFOREST_KEY),
  headings:[...document.querySelectorAll('h1,h2,h3,h4')].filter(visible).map(e=>e.innerText.trim())};
}"""

NOTE_MARKERS_READ = r"""() => {
 const visible=e=>!!e&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden'&&getComputedStyle(e).display!=='none';
 return {native_note_marker_icons: {
   open:window.OSM?.OPEN_NOTE_MARKER||null,closed:window.OSM?.CLOSED_NOTE_MARKER||null},
   native_active_overlays:typeof window.__labNativeLayerState==='function'?window.__labNativeLayerState():null,
   native_note_markers:[...document.querySelectorAll('.leaflet-marker-pane img.leaflet-marker-icon')]
    .filter(visible).map(e=>({title:e.getAttribute('title')||'',src:e.src,
      loaded:e.complete&&e.naturalWidth>0}))};
}"""

ROUTE_READ = r"""() => {
      const visible=e=>!!e && !!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
      const field=selector=>{
        const matches=[...document.querySelectorAll(selector)].filter(visible);
        if(matches.length>1) throw new Error('Ambiguous visible native route control: '+selector);
        return matches[0];
      };
      const sidebar=document.querySelector('#sidebar_content');
      return {origin:field('input[name="route_from"]')?.value || '',
        destination:field('input[name="route_to"]')?.value || '',
        engine:field('select.routing_engines')?.selectedOptions[0]?.text || '',
        route_form_visible:!!(field('input[name="route_from"]') || field('input[name="route_to"]') || field('select.routing_engines')),
        summary:sidebar?.innerText || '',
        rows:[...document.querySelectorAll('#sidebar_content tr.turn')].map(e=>e.innerText),
        route_visible:[...document.querySelectorAll('.leaflet-overlay-pane path[stroke="#03f"]')].some(e=>visible(e) && (e.getAttribute('d')||'').length>20),
        loading:[...document.querySelectorAll('#sidebar_loader,#sidebar_content .loader')].some(visible)};
    }"""

COMBINED_READ = (
    "() => { const surface = ("
    + READ
    + ")(); const layers = ("
    + NOTE_MARKERS_READ
    + ")(); const route = ("
    + ROUTE_READ
    + ")(); return {surface: {...surface, ...layers}, route}; }"
)
