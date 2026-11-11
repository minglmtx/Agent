"""Read native rendered document sections without selecting an expected target.

Section identity and viewport exposure are distinct. A document merely
containing the requested heading is not proof that its section is displayed.
"""
import hashlib

READ = r'''() => {
  const shown=e=>!!e.getClientRects().length && getComputedStyle(e).visibility!=='hidden';
  const inView=e=>{const r=e.getBoundingClientRect();return shown(e)&&r.bottom>0&&r.top<innerHeight&&r.right>0&&r.left<innerWidth;};
  const result=[];
  for(const file of document.querySelectorAll('.file-content')) {
    if(!shown(file))continue;
    for(const h of file.querySelectorAll('h1,h2,h3,h4,h5,h6')) {
      if(!shown(h))continue;
      const level=Number(h.tagName.slice(1));const nodes=[];
      for(let e=h.nextElementSibling;e;e=e.nextElementSibling) {
        if(/^H[1-6]$/.test(e.tagName)&&Number(e.tagName.slice(1))<=level)break;
        if(shown(e))nodes.push(e);
      }
      const anchor=h.querySelector('a[href^="#"]');
      result.push({heading:h.innerText.trim(),anchor:anchor?.getAttribute('href')||'',
        text:nodes.map(e=>e.innerText).join('\n').trim(),
        heading_in_view:inView(h),body_in_view:nodes.some(e=>e.innerText.trim()&&inView(e))});
    }
  }
  return result;
}'''


def digest(text):
    return hashlib.sha256(' '.join(text.split()).encode()).hexdigest()


def section_checks(spec, sections, *, issued_request=None, current_url=None):
    if (not isinstance(spec,dict) or not isinstance(spec.get('heading'),str)
        or not spec['heading'].strip() or not isinstance(spec.get('body_sha256'),str)):
        raise ValueError('Missing independently captured section identity')
    if not isinstance(sections,list):raise ValueError('Missing native document section capture')
    matches=[s for s in sections if s.get('heading')==spec['heading']]
    exposure_key='document_section_observed' if issued_request is not None else 'document_section_displayed'
    if len(matches)!=1:
        return {'requested_document_section':False,exposure_key:False}
    row=matches[0]
    if not isinstance(row.get('text'),str) or any(type(row.get(k))is not bool for k in ('heading_in_view','body_in_view')):
        raise ValueError('Malformed native section capture')
    # Reading farther down a long section can move its heading out of view.
    # The heading still establishes section identity in the native document;
    # do not force the actor to scroll back to the beginning before stopping.
    exposed=row['body_in_view']
    if issued_request is not None:
        from .document_observation import request_exposure
        if not isinstance(current_url,str):raise ValueError('Actual observation requires terminal document URL')
        # Recompute from the selected request; a precomputed success flag or
        # an unselected full DOM tree never proves actor exposure.
        exposed=exposed or request_exposure(issued_request,terminal_url=current_url,section=row)['observed']
    return {'requested_document_section':bool(row['text'].strip()) and digest(row['text'])==spec['body_sha256'],
            exposure_key:exposed}


FEEDBACK={
    'requested_document_section':'The requested section and its complete native content are present in the correct document.',
    'document_section_observed':'The requested document section is visible in the terminal viewport or its complete content was provided in the selected observation for this document.',
    'document_section_displayed':'Content from the requested document section is displayed in the current viewport.'}
