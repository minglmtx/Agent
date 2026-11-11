"""Native GitLab code spans preserve source literals and line identities.

Public LC spans differ from visually transparent viewport placeholders. The
latter need scrolling, not a longer loading wait. This reader never scrolls,
waits for a private total count, strips numeric source lines, or navigates.
"""
from .gitlab_public_readiness import BLOB_SIGNALS

READ=r'''() => {
 const shown=e=>!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 const blocks=[...document.querySelectorAll('.file-content.code')].filter(shown);
 return {url:location.href,loading:('''+BLOB_SIGNALS+r''')().length>0,
   blocks:blocks.map(block=>{
     const nodes=[...block.querySelectorAll('span.line[id]')].filter(node=>/^LC[1-9][0-9]*$/.test(node.id)&&shown(node));
     const placeholders=[...block.querySelectorAll('.gl-text-transparent')].map(chunk=>({
       line_numbers:[...chunk.querySelectorAll('[data-testid="line-number"][id]')].filter(n=>/^L[1-9][0-9]*$/.test(n.id)).map(n=>Number(n.id.slice(1))),
       viewport_intersects:chunk.getBoundingClientRect().bottom>0&&chunk.getBoundingClientRect().top<innerHeight
     }));
     return {path:block.getAttribute('data-path'),data_type:block.getAttribute('data-type'),
       lines:nodes.slice(0,20000).map(node=>({number:Number(node.id.slice(2)),text:node.textContent,viewport_intersects:node.getBoundingClientRect().bottom>0&&node.getBoundingClientRect().top<innerHeight})),
       line_capture_truncated:nodes.length>20000,viewport_placeholder_chunks:placeholders};
   })};
}'''


def whole_source_text(state):
    """Complete current DOM code view only; a raw endpoint is a separate proof."""
    if not isinstance(state,dict)or state.get('loading')is not False:
        raise ValueError('Native source content still loading or absent')
    blocks=state.get('blocks')
    if not isinstance(blocks,list)or len(blocks)!=1:
        raise ValueError('Native code view absent or ambiguous')
    block=blocks[0]
    if block.get('line_capture_truncated')is not False or block.get('viewport_placeholder_chunks')!=[]:
        raise ValueError('Whole source is not rendered in the captured native view')
    lines=block.get('lines')
    if not isinstance(lines,list)or not lines or any(not isinstance(row,dict)or type(row.get('number'))is not int or row['number']!=index or not isinstance(row.get('text'),str)for index,row in enumerate(lines,1)):
        raise ValueError('Native source line identities are missing, duplicated or noncontiguous')
    return '\n'.join(row['text']for row in lines)


VIEWPORT_READY='''() => { const state = ('''+READ+''')(); return !state.loading && !state.blocks.some(block=>block.viewport_placeholder_chunks.some(chunk=>chunk.viewport_intersects)); }'''
