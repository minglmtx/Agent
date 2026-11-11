"""Expose actual Magento collapsible controls missing roles/states in the AX tree.

Read-only DOM accessibility supplement; enumerates every section, never looks at a
benchmark goal, reference answer, binding, or evaluator result.
"""
import re

SECTION_SCRIPT = '''() => [...document.querySelectorAll('.admin__collapsible-block-wrapper > .fieldset-wrapper-title[data-state-collapsible]')].map(header => {
 const title=header.querySelector('.admin__collapsible-title[bid]');
 const label=title?.querySelector('span');
 const state=header.getAttribute('data-state-collapsible');
 return {bid:title?.getAttribute('bid'), name:label?.textContent?.trim(),
         expanded:state==='open', state_known:state==='open'||state==='closed',
         scope:'record section', control:'clickable collapsible heading'};
}).filter(x => x.bid && x.name && x.state_known)'''


def record_sections(page,obs):
    # Only advertise bids present in the CURRENT AX observation.
    ids=set(re.findall(r'^\s*\[([^\]\n]+)\]',obs.get('axtree_txt',''),re.MULTILINE))
    return [r for r in page.evaluate(SECTION_SCRIPT) if r['bid'] in ids]
