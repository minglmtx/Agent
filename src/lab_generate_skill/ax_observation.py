"""Preserve native accessibility descriptions when using BrowserGym's text renderer.

Chromium stores description beside name; BrowserGym renders properties but skips
that top-level description. BrowserGym's temporary aria-description also masks
title-derived descriptions. The original title remains in Chromium's name source
metadata: render it explicitly as title, never infer an absent label. No private
state or task labels enter this adapter. Visibility and token budgets still apply.
"""


def native_context(node):
    value=node.get('description',{}).get('value')
    if isinstance(value,str) and value.strip():return 'description',value
    titles=[]
    for source in node.get('name',{}).get('sources',[]):
        if source.get('type')!='attribute' or source.get('attribute')!='title':continue
        value=source.get('attributeValue',source.get('value',{})).get('value')
        if isinstance(value,str) and value.strip() and value not in titles:titles.append(value)
    if len(titles)==1:return 'title',titles[0]
    return None,None


def with_native_descriptions(tree):
    nodes=[]
    for node in tree.get('nodes',[]):
        key,value=native_context(node)
        name=node.get('name',{}).get('value')
        if isinstance(value,str) and value.strip() and value.strip()!=str(name or '').strip():
            props=[p for p in node.get('properties',[]) if p.get('name')!=key]
            node={**node,'properties':props+[{'name':key,'value':{'type':'string','value':value}}]}
        nodes.append(node)
    return {**tree,'nodes':nodes}


def with_keyboard_focusable_regions(tree):
    """Keep native focusable generic regions addressable in the text observation.

    BrowserGym ignores Chromium's ``focusable`` property and skips generic
    nodes with no remaining attributes. Preserve only a literal native True
    on a non-ignored generic node with its existing action ID. The additional
    property is a rendering alias, not a new role, label, ID or page action.
    Ordinary viewport filtering and input budgets still apply to this node.
    """
    output=[]
    for node in tree.get('nodes',[]):
        props=node.get('properties',[])
        focusable=[p.get('value',{}).get('value')for p in props if p.get('name')=='focusable']
        bid=node.get('browsergym_id')
        if (node.get('role',{}).get('value')=='generic' and not node.get('ignored')
                and isinstance(bid,str) and bid.strip() and focusable==[True]
                and type(focusable[0])is bool
                and not any(p.get('name')=='keyboard_focusable'for p in props)):
            node={**node,'properties':props+[{'name':'keyboard_focusable','value':{'type':'boolean','value':True}}]}
        output.append(node)
    return {**tree,'nodes':output}


def with_rendered_inline_text(tree,dom,extra_properties):
    """Preserve rendered spacing across inline nodes from the same DOM snapshot.

    AX separates inline emoji/emphasis from adjacent text and loses the spacing
    at those boundaries. Supplement small plain paragraphs with the browser's
    rendered text fragments, never textContent from hidden nodes or a database.
    Keep the original AX nodes and action IDs; ordinary visibility filtering and
    the model input budget still apply.
    """
    if not isinstance(dom,dict):return tree
    from collections import defaultdict
    strings=dom.get('strings',[]);candidates={};ambiguous=set()
    exposed_text={n.get('backendDOMNodeId') for n in tree.get('nodes',[]) if not n.get('ignored') and n.get('role',{}).get('value')=='StaticText'}
    safe_inline={'SPAN','A','B','STRONG','EM','I','SMALL','CODE','GL-EMOJI'}
    for doc in dom.get('documents',[]):
        nodes=doc.get('nodes',{});layout=doc.get('layout',{})
        required=('nodeName','parentIndex','nodeType','nodeValue','backendNodeId')
        if any(k not in nodes for k in required):continue
        children=defaultdict(list)
        for index,parent in enumerate(nodes['parentIndex']):children[parent].append(index)
        rendered={index:(strings[text] if text>=0 else '') for index,text in zip(layout.get('nodeIndex',[]),layout.get('text',[]))}
        for index,name in enumerate(nodes['nodeName']):
            if strings[name]!='P' or index not in rendered:continue
            stack=list(reversed(children[index]));fragments=[];allowed=True
            while stack:
                child=stack.pop();kind=nodes['nodeType'][child]
                if kind==3:
                    value=rendered.get(child)
                    # Whitespace-only DOM nodes omitted by layout are harmless;
                    # any hidden nonempty text makes supplementation unsafe.
                    native_index=nodes['nodeValue'][child]
                    native=strings[native_index] if native_index>=0 else ''
                    if native.strip() and (value is None or nodes['backendNodeId'][child] not in exposed_text):allowed=False;break
                    if value:fragments.append(value)
                elif kind==1 and strings[nodes['nodeName'][child]] in safe_inline:
                    stack.extend(reversed(children[child]))
                else:allowed=False;break
            if not allowed or len(fragments)<2:continue
            value=''.join(fragments)
            if not value.strip() or len(value)>512:continue
            backend=nodes['backendNodeId'][index]
            if backend in candidates:ambiguous.add(backend)
            candidates[backend]=value
    axnodes={n['nodeId']:n for n in tree.get('nodes',[])};output=[]
    for node in tree.get('nodes',[]):
        backend=node.get('backendDOMNodeId');value=candidates.get(backend)
        fully_visible=extra_properties.get(node.get('browsergym_id'),{}).get('visibility',0)>=1
        if value and fully_visible and backend not in ambiguous and node.get('role',{}).get('value')=='paragraph':
            # Do not expose a clipped/hidden descendant by attaching its text
            # to a visible ancestor. Leave such observations unchanged.
            pending=list(node.get('childIds',[]));hidden=False
            while pending:
                child=axnodes.get(pending.pop(),{});bid=child.get('browsergym_id')
                if bid and extra_properties.get(bid,{}).get('visibility',0)<0.5:hidden=True;break
                pending.extend(child.get('childIds',[]))
            if not hidden:
                props=[p for p in node.get('properties',[]) if p.get('name')!='rendered_text']
                node={**node,'properties':props+[{'name':'rendered_text','value':{'type':'string','value':value}}]}
        output.append(node)
    return {**tree,'nodes':output}


"""Preserve public native drag/drop affordances omitted by generic AX rendering.

Candidate only, not the published runtime. The attributes report native DOM
flags; they do not assert which item a region accepts or prescribe an action.
No page mutation, task IDs, private data, generated IDs or hidden text.
"""


def with_native_drag_regions(tree, dom, extra):
    if not isinstance(dom, dict):
        return tree
    strings = dom.get('strings', [])
    exposed = {n.get('backendDOMNodeId'): n for n in tree.get('nodes', [])
               if not n.get('ignored') and n.get('browsergym_id')}
    states = {}; ambiguous = set()
    for doc in dom.get('documents', []):
        nodes = doc.get('nodes', {})
        backends, attributes = nodes.get('backendNodeId', []), nodes.get('attributes', [])
        if len(backends) != len(attributes):
            continue
        layout = doc.get('layout', {})
        rendered = {idx for idx, bounds in zip(layout.get('nodeIndex', []), layout.get('bounds', []))
                    if len(bounds) == 4 and bounds[2] > 0 and bounds[3] > 0}
        for idx, backend in enumerate(backends):
            node = exposed.get(backend)
            if node is None or idx not in rendered:
                continue
            bid = node['browsergym_id']
            if extra.get(bid, {}).get('visibility', 0) < 0.5:
                continue
            native = attributes[idx]
            if len(native) % 2 or any(type(i) is not int or i < 0 or i >= len(strings) for i in native):
                continue
            attrs = {strings[native[i]]: strings[native[i+1]] for i in range(0, len(native), 2)}
            classes = attrs.get('class', '').split()
            flags = {}
            if attrs.get('draggable', '').lower() == 'true':
                flags['html_draggable'] = True
            for native_class, flag in [('ui-draggable', 'css_draggable'), ('ui-droppable', 'css_droppable')]:
                if native_class in classes:
                    flags[flag] = True
                    if native_class + '-disabled' in classes:
                        flags[flag + '_disabled'] = True
            dropeffect = attrs.get('aria-dropeffect', '').strip()
            if dropeffect and set(dropeffect.split()) <= {'copy', 'execute', 'link', 'move', 'none', 'popup'}:
                flags['aria_dropeffect'] = dropeffect
            if not flags:
                continue
            if backend in states:
                ambiguous.add(backend)
            states[backend] = flags
    output = []
    for node in tree.get('nodes', []):
        backend = node.get('backendDOMNodeId')
        flags = states.get(backend)
        if flags and backend not in ambiguous:
            props = [x for x in node.get('properties', []) if x.get('name') not in flags]
            props.extend({'name': k, 'value': {'type': 'boolean' if isinstance(v, bool) else 'string', 'value': v}}
                         for k, v in flags.items())
            node = {**node, 'properties': props}
        output.append(node)
    return with_native_option_text(with_native_clickable_regions(with_rendered_generic_text({**tree, 'nodes': output}, dom, extra), extra), dom, extra)


def with_rendered_generic_text(tree, dom, extra):
    """Keep a visible generic region's single directly rendered text label.

    Some editors implement a drop region as a plain div with an instructional
    text child, without HTML/ARIA drag attributes. Preserve that literal text
    and the region's existing bid; do not infer or assert drop semantics.
    Nested containers, hidden text and multi-part page summaries are excluded.
    """
    if not isinstance(dom, dict):return tree
    strings=dom.get('strings',[]);rendered={};ambiguous=set()
    for doc in dom.get('documents',[]):
        nodes=doc.get('nodes',{});layout=doc.get('layout',{})
        backends=nodes.get('backendNodeId',[]);types=nodes.get('nodeType',[])
        for idx,text_id in zip(layout.get('nodeIndex',[]),layout.get('text',[])):
            if not (0<=idx<len(backends) and idx<len(types) and types[idx]==3
                    and 0<=text_id<len(strings)):continue
            backend=backends[idx]
            if backend in rendered:ambiguous.add(backend)
            rendered[backend]=strings[text_id]
    by_id={n['nodeId']:n for n in tree.get('nodes',[])};output=[]
    for node in tree.get('nodes',[]):
        children=node.get('childIds',[]);child=by_id.get(children[0],{}) if len(children)==1 else {}
        backend=child.get('backendDOMNodeId');text=rendered.get(backend,'')
        if (node.get('role',{}).get('value')=='generic' and not node.get('ignored')
                and node.get('browsergym_id') and extra.get(node['browsergym_id'],{}).get('visibility',0)>=0.5
                and child.get('role',{}).get('value')=='StaticText' and not child.get('ignored')
                and backend not in ambiguous and text.strip() and len(text)<=256
                and text.strip()==str(child.get('name',{}).get('value','')).strip()):
            props=[p for p in node.get('properties',[]) if p.get('name')!='rendered_text']
            node={**node,'properties':props+[{'name':'rendered_text','value':{'type':'string','value':text}}]}
        output.append(node)
    return {**tree,'nodes':output}


def with_native_clickable_regions(tree, extra):
    """Preserve an existing visible generic control's native clickability.

    BrowserGym drops generic nodes before it renders its clickable metadata,
    even if Chromium supplies an accessible name. Keep the measured flag as
    an AX property; never infer clickability from names, CSS or task intent.
    """
    output = []
    for node in tree.get('nodes', []):
        bid = node.get('browsergym_id')
        state = extra.get(bid, {})
        bounds = state.get('bbox', [])
        if (node.get('role', {}).get('value') == 'generic' and not node.get('ignored')
                and isinstance(bid, str) and bid and state.get('clickable') is True
                and state.get('visibility', 0) >= 0.5 and len(bounds) == 4
                and bounds[2] > 0 and bounds[3] > 0):
            props = [x for x in node.get('properties', []) if x.get('name') != 'native_clickable']
            node = {**node, 'properties': props + [
                {'name': 'native_clickable', 'value': {'type': 'boolean', 'value': True}}]}
        output.append(node)
    return {**tree, 'nodes': output}


"""Preserve visible native listbox option text when Chromium's AX name is empty.

Read only the same captured public DOM/AX snapshot. Keep the computed AX name,
selection state, and action ID. No page mutation, labels from a database, task
IDs, hidden options, collapsed dropdown contents, or label inference.
"""


def with_native_option_text(tree, dom, extra):
    if not isinstance(dom, dict):
        return tree
    strings = dom.get('strings', [])
    candidates, ambiguous = {}, set()
    ax = {}
    for node in tree.get('nodes', []):
        backend = node.get('backendDOMNodeId')
        if backend in ax:
            ambiguous.add(backend)
        ax[backend] = node
    for doc in dom.get('documents', []):
        nodes, layout = doc.get('nodes', {}), doc.get('layout', {})
        ids = nodes.get('backendNodeId', [])
        names, attrs, parents = (nodes.get(k, []) for k in ('nodeName', 'attributes', 'parentIndex'))
        types, values = nodes.get('nodeType', []), nodes.get('nodeValue', [])
        if any(len(seq) != len(ids) for seq in (names, attrs, parents, types, values)):
            continue
        def string(index):
            if index == -1:
                return ''  # CDP's empty-string sentinel, including HTML boolean attributes.
            return strings[index] if type(index) is int and 0 <= index < len(strings) else None
        def attributes(index):
            row = attrs[index]
            if len(row) % 2 or any(string(i) is None for i in row):
                return None
            if any(not string(row[i]) for i in range(0, len(row), 2)):
                return None
            return {string(row[i]): string(row[i+1]) for i in range(0, len(row), 2)}
        bounds = {}
        for index, box in zip(layout.get('nodeIndex', []), layout.get('bounds', [])):
            if index in bounds:
                bounds[index] = None
            else:
                bounds[index] = box
        children = {}
        for i, parent in enumerate(parents):
            children.setdefault(parent, []).append(i)
        for index, backend in enumerate(ids):
            node = ax.get(backend, {})
            bid = node.get('browsergym_id')
            if (node.get('ignored') or node.get('role', {}).get('value') != 'option'
                    or str(node.get('name', {}).get('value', '')).strip()
                    or not bid or extra.get(bid, {}).get('visibility', 0) < 1
                    or string(names[index]) != 'OPTION'):
                continue
            parent = parents[index]
            if type(parent) is not int or not 0 <= parent < len(ids) or string(names[parent]) != 'SELECT':
                continue
            option_attrs, select_attrs = attributes(index), attributes(parent)
            if option_attrs is None or select_attrs is None or option_attrs.get('label', '').strip():
                continue
            try:
                listbox = 'multiple' in select_attrs or int(select_attrs.get('size', '1')) > 1
            except ValueError:
                continue
            if not listbox:
                continue
            option_box, select_box = bounds.get(index), bounds.get(parent)
            if (not option_box or not select_box or len(option_box) != 4 or len(select_box) != 4
                    or option_box[2] <= 0 or option_box[3] <= 0 or select_box[2] <= 0 or select_box[3] <= 0):
                continue
            x, y, width, height = option_box
            sx, sy, sw, sh = select_box
            # Do not expose options clipped by the listbox's internal scroll area.
            if not (sx <= x and sy <= y and x+width <= sx+sw and y+height <= sy+sh):
                continue
            child_ids = children.get(index, [])
            if not child_ids or any(types[i] != 3 or string(values[i]) is None for i in child_ids):
                continue
            text = ' '.join(''.join(strings[values[i]] for i in child_ids).split())
            contents = {source.get('value', {}).get('value') for source in node.get('name', {}).get('sources', [])
                        if source.get('type') == 'contents' and isinstance(source.get('value', {}).get('value'), str)}
            contents = {' '.join(value.split()) for value in contents if value.strip()}
            if not text or len(text) > 512 or contents != {text}:
                continue
            if backend in candidates:
                ambiguous.add(backend)
            candidates[backend] = text
    output = []
    for node in tree.get('nodes', []):
        backend = node.get('backendDOMNodeId')
        if backend in candidates and backend not in ambiguous:
            props = [p for p in node.get('properties', []) if p.get('name') != 'rendered_option_text']
            node = {**node, 'properties': props + [{'name': 'rendered_option_text',
                    'value': {'type': 'string', 'value': candidates[backend]}}]}
        output.append(node)
    return {**tree, 'nodes': output}
