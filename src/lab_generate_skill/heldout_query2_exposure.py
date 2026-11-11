"""Private DOM/AX provenance for two Query2 sources, after request verification.

This module never augments Actor input, navigates, or evaluates a native answer.
The caller must first verify the actual dispatch journal. Its issued AX is then
joined to the original observation snapshot, never a later AX recapture.
"""
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import re
from urllib.parse import unquote, urljoin, urlsplit

VERSION = 'query2-issued-exposure-v1'
PARSER_REVISION = 'query2-same-style-pseudo-fragments-v2'
OLDEST = '1452674220923c2805a6'
WIKI = '72dd889fe56c84cc0a62'
STYLE_PROPERTIES = ['display', 'visibility', 'opacity']
STYLE_MARKER = '_query2_private_computed_styles'


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


@contextmanager
def private_snapshot_styles():
    """Augment the original single DOMSnapshot call; no second DOM/AX capture.

    One Session per process, with the same narrow exclusive-hook contract as
    request binding. Existing website methods and public renderer are unchanged.
    """
    import browsergym.core.env as env_module
    original = env_module.extract_dom_snapshot
    require(not getattr(original, '_query2_private_style_hook', False), 'Nested private style hook')
    def augmented(page, *args, **kwargs):
        require(not args and kwargs.get('computed_styles', []) == [],
                'Unexpected original DOM snapshot style request')
        dom = original(page, **{**kwargs, 'computed_styles': list(STYLE_PROPERTIES)})
        require(STYLE_MARKER not in dom, 'Existing private snapshot marker')
        dom[STYLE_MARKER] = list(STYLE_PROPERTIES)
        return dom
    augmented._query2_private_style_hook = True
    env_module.extract_dom_snapshot = augmented
    try:
        yield
    finally:
        require(env_module.extract_dom_snapshot is augmented, 'Concurrent private style hook replacement')
        env_module.extract_dom_snapshot = original


def _without_styles(raw):
    dom = raw['dom_object']
    documents = []
    for doc in dom['documents']:
        layout = {key: value for key, value in doc['layout'].items() if key != 'styles'}
        documents.append({**doc, 'layout': layout})
    return {**raw, 'dom_object': {key: value for key, value in
        {**dom, 'documents': documents}.items() if key != STYLE_MARKER}}


def _render(raw, viewport):
    # Exact existing observation transforms and renderer, no alternate prompt.
    from browsergym.utils.obs import flatten_axtree_to_str
    from .ax_observation import (with_native_descriptions,
        with_keyboard_focusable_regions, with_native_drag_regions,
        with_rendered_inline_text)
    from .public_control_state import with_public_control_state
    tree = with_native_descriptions(raw['axtree_object'])
    tree = with_keyboard_focusable_regions(tree)
    tree = with_native_drag_regions(tree, raw['dom_object'], raw['extra_element_properties'])
    tree = with_public_control_state(tree, raw['dom_object'], raw['extra_element_properties'])
    tree = with_rendered_inline_text(tree, raw['dom_object'], raw['extra_element_properties'])
    full = flatten_axtree_to_str(tree, filter_visible_only=False,
                                extra_properties=raw['extra_element_properties'])
    visible = flatten_axtree_to_str(tree, filter_visible_only=True,
                                   extra_properties=raw['extra_element_properties']) if viewport else full
    return tree, full, visible


def capture_raw_snapshot(raw, public_observation):
    """Call from Session.observation with that call's raw input and output.

    Keep this result on the Session privately. The eventual record must use
    the last snapshot matching its returned observation (loading refreshes can
    replace an earlier observation). No screenshots or later page reads.
    """
    projection = {key: deepcopy(raw[key]) for key in
                  ('url', 'axtree_object', 'dom_object', 'extra_element_properties')}
    require(projection['dom_object'].get(STYLE_MARKER) == STYLE_PROPERTIES,
            'Private single-snapshot style hook was not active')
    public = {key: deepcopy(public_observation[key]) for key in
              ('url', 'axtree_txt', 'axtree_full_txt') if key in public_observation}
    require(public.get('url') == projection['url'], 'Raw/public document URL differs')
    _, full, visible = _render(projection, 'axtree_full_txt' in public)
    _, original_full, original_visible = _render(_without_styles(projection), 'axtree_full_txt' in public)
    require((full, visible) == (original_full, original_visible),
            'Private computed styles changed original public AX rendering')
    require(public.get('axtree_txt') == visible and
            ('axtree_full_txt' not in public or public['axtree_full_txt'] == full),
            'Raw snapshot does not reproduce this observation')
    return {'version': VERSION, 'raw': projection, 'public_projection': public}


def bind_snapshot_to_observation(snapshot, observation):
    """Call in Session.record after refresh/download handling, before hashing page."""
    public = {key: deepcopy(observation[key]) for key in
              ('url', 'axtree_txt', 'axtree_full_txt') if key in observation}
    require(snapshot['version'] == VERSION and snapshot['public_projection'] == public,
            'Last raw snapshot differs from final recorded observation')
    return {**deepcopy(snapshot), 'record_observation': deepcopy(observation)}


class Document:
    """Strict primary-document identity and ancestry from the same CDP snapshot."""
    def __init__(self, raw):
        dom = raw['dom_object']; strings = dom['strings']; docs = dom['documents']
        require(isinstance(docs, list) and docs, 'DOM document missing')
        require(dom.get(STYLE_MARKER) == STYLE_PROPERTIES, 'Same-snapshot computed style provenance missing')
        doc = docs[0]
        require(strings[doc['documentURL']] == raw['url'], 'DOM document URL differs')
        nodes = doc['nodes']; count = len(nodes['parentIndex'])
        require(all(len(nodes[k]) == count for k in
                    ('backendNodeId', 'nodeName', 'nodeValue', 'nodeType', 'attributes')),
                'DOM node columns incomplete')
        require(len(set(nodes['backendNodeId'])) == count, 'Duplicate DOM backend identity')
        self.nodes = []; self.children = [[] for _ in range(count)]
        for index in range(count):
            parent = nodes['parentIndex'][index]
            require(type(parent) is int and -1 <= parent < index, 'DOM parent order invalid')
            attrs = nodes['attributes'][index]
            require(len(attrs) % 2 == 0, 'Incomplete DOM attributes')
            pairs = [(strings[attrs[i]], strings[attrs[i + 1]]) for i in range(0, len(attrs), 2)]
            require(len(dict(pairs)) == len(pairs), 'Duplicate DOM attribute')
            self.nodes.append({'index': index, 'parent': parent,
                'backend': nodes['backendNodeId'][index], 'tag': strings[nodes['nodeName'][index]],
                'type': nodes['nodeType'][index], 'attrs': dict(pairs),
                'value': strings[nodes['nodeValue'][index]] if nodes['nodeValue'][index] >= 0 else ''})
            if parent >= 0:
                self.children[parent].append(index)
        roots = [n for n in self.nodes if n['parent'] == -1]
        require(len(roots) == 1 and roots[0]['type'] == 9, 'Primary Document root ambiguous')
        axroot = raw['axtree_object']['nodes'][0]
        require(axroot.get('role', {}).get('value') == 'RootWebArea' and
                axroot.get('backendDOMNodeId') == roots[0]['backend'],
                'DOM and AX Document identities differ')
        self.url = raw['url']
        layout = doc['layout']
        require(len(layout['nodeIndex']) == len(layout['styles']) == len(layout['bounds']),
                'Snapshot layout/style columns incomplete')
        self.layout = {}; self.pseudo_layout_fragments = {}
        for index, styles, bounds in zip(layout['nodeIndex'], layout['styles'], layout['bounds']):
            require(type(index) is int and 0 <= index < len(self.nodes), 'Snapshot layout node index invalid')
            node = self.nodes[index]
            require(len(styles) == len(STYLE_PROPERTIES) or node['type'] != 1 and not styles,
                    'Snapshot node style missing')
            require(all(type(s) is int and 0 <= s < len(strings) for s in styles), 'Snapshot style index invalid')
            item = {'styles': dict(zip(STYLE_PROPERTIES, (strings[s] for s in styles))), 'bounds': bounds}
            if index in self.layout:
                # Actual retained snapshots contain several layout fragments
                # for the SAME ::before/::after backend node. These are not
                # task controls or exposure witnesses. Preserve every fragment
                # without letting a later rectangle replace the first one.
                require(node['type'] == 1 and node['tag'] in ('::before', '::after')
                        and not node['attrs'].get('bid') and item['styles'] == self.layout[index]['styles'],
                        'Snapshot duplicate node layout ambiguous')
                self.pseudo_layout_fragments.setdefault(index, [self.layout[index]]).append(item)
                continue
            self.layout[index] = item

    def descendants(self, node):
        result = []; pending = [node['index']]
        while pending:
            index = pending.pop(); result.append(self.nodes[index])
            pending.extend(reversed(self.children[index]))
        return result

    def ancestors(self, node):
        result = []; parent = node['parent']
        while parent >= 0:
            result.append(self.nodes[parent]); parent = self.nodes[parent]['parent']
        return result

    def within(self, node, ancestor):
        return node == ancestor or ancestor in self.ancestors(node)

    def unique_id(self, identity):
        found = [n for n in self.nodes if n['attrs'].get('id') == identity]
        require(len(found) == 1, 'DOM id missing or ambiguous: ' + identity)
        return found[0]

    def text(self, node):
        return ' '.join(''.join(n['value'] for n in self.descendants(node) if n['type'] == 3).split())

    def visible(self, node):
        # Offscreen is allowed: viewport exposure is decided by the issued AX.
        # Generated pseudo content cannot act as a target/ancestor witness.
        # Its compatible duplicate fragments never grant exposure to a control.
        if any(n['tag'] in ('::before', '::after') for n in [node] + self.ancestors(node)):
            return False
        target = self.layout.get(node['index'])
        if target is None:
            return False
        bounds = target['bounds']
        require(len(bounds) == 4, 'Target layout bounds incomplete')
        if bounds[2] <= 0 or bounds[3] <= 0:
            return False
        for parent in [node] + self.ancestors(node):
            if parent['type'] != 1:
                continue
            if 'hidden' in parent['attrs'] or 'inert' in parent['attrs']:
                return False
            if parent['tag'] == 'DETAILS' and 'open' not in parent['attrs']:
                summaries = [self.nodes[i] for i in self.children[parent['index']]
                             if self.nodes[i]['tag'] == 'SUMMARY']
                if not summaries or not self.within(node, summaries[0]):
                    return False
            item = self.layout.get(parent['index'])
            require(item is not None, 'Ancestor lacks same-snapshot style/layout evidence')
            style = item['styles']
            if (style['display'] == 'none' or style['visibility'] in ('hidden', 'collapse')
                    or float(style['opacity']) <= 0):
                return False
        return True


class Lines:
    """Map a unique AX node to its exact original renderer line.

    Isolated rendering is used only to identify the node's complete line. A
    line also has to exist uniquely in the original full/viewport rendering;
    therefore skipped/filtered nodes cannot acquire invented exposure. A
    duplicate unaddressed StaticText anywhere in AX remains ambiguous.
    """
    def __init__(self, tree, raw, original, issued):
        from browsergym.utils.obs import flatten_axtree_to_str
        self.nodes = tree['nodes']; self.lines = {}; self.issued = issued.splitlines()
        self.original = original.splitlines(); self.raw = raw
        require(isinstance(issued, str), 'Issued AX missing')
        # The request verifier permits only original AX or a prefix plus its
        # own truncation notice. Here each matched target retains its position.
        for node in self.nodes:
            line = flatten_axtree_to_str({'nodes': [{**node, 'childIds': []}]},
                extra_properties=raw['extra_element_properties'], filter_visible_only=False,
                remove_redundant_static_text=False)
            if line:
                self.lines[node['nodeId']] = line
        self.counts = Counter(self.lines.values())

    def node_for(self, domnode, *, role=None, element=True):
        found = [n for n in self.nodes if n.get('backendDOMNodeId') == domnode['backend']
                 and not n.get('ignored') and (role is None or n.get('role', {}).get('value') == role)]
        require(len(found) == 1, 'DOM to AX backend mapping missing or ambiguous')
        node = found[0]
        if element:
            bid = domnode['attrs'].get('bid')
            require(isinstance(bid, str) and bid and node.get('browsergym_id') == bid,
                    'DOM and AX BrowserGym bid differ')
            require(sum(n.get('browsergym_id') == bid for n in self.nodes) == 1,
                    'AX BrowserGym bid ambiguous')
        return node

    def witness(self, node):
        line = self.lines.get(node['nodeId'])
        require(line is not None and self.counts[line] == 1, 'AX node line absent or ambiguous')
        positions = [i for i, row in enumerate(self.original) if row.lstrip('\t') == line]
        # Exact renderer suppression is known absence, not a guessed match.
        if not positions:
            return None
        require(len(positions) == 1, 'Original AX line ambiguous')
        index = positions[0]
        if index >= len(self.issued) or self.issued[index] != self.original[index]:
            return None
        return {'ax_node_id': node['nodeId'], 'backend_dom_node_id': node['backendDOMNodeId'],
                'browsergym_id': node.get('browsergym_id'), 'line_index': index,
                'line_sha256': hashlib.sha256(self.original[index].encode()).hexdigest()}


def _classes(node):
    return set(node['attrs'].get('class', '').split())


def _oldest(document, lines, page):
    state = page['query2']['forum_list']
    empty = {'forum_names': [], 'wiki_body_notice': False, 'witnesses': []}
    path = urlsplit(page['url']).path
    if not re.fullmatch(r'/forums/by_creation_date(?:/[1-9][0-9]*)?', path):
        return empty
    if state['active_tabs'] != ['Forums'] or state['sort_labels'] != ['Creation date']:
        return empty
    main = document.unique_id('main')
    controls = [n for n in document.descendants(main) if n['tag'] == 'BUTTON'
                and {'tab', 'dropdown__toggle'} <= _classes(n)]
    require(len(controls) == 1 and document.text(controls[0]) == 'Creation date',
            'Captured sort control differs from original DOM snapshot')
    tabs = [n for n in document.descendants(main) if n['tag'] == 'A' and 'tab--active' in _classes(n)]
    require(len(tabs) == 1 and document.text(tabs[0]) == 'Forums',
            'Captured active directory tab differs from original DOM snapshot')
    if not document.visible(controls[0]) or not document.visible(tabs[0]):
        return empty
    sort = lines.node_for(controls[0], role='button')
    require(sort.get('name', {}).get('value') == controls[0]['attrs'].get('aria-label')
            and re.search(r'\bCreation date\b', sort['name']['value']),
            'Creation sort context AX differs from its native control')
    sort_witness = lines.witness(sort)
    if sort_witness is None:
        return empty
    names = []; witnesses = [sort_witness]
    for entry in state['entries']:
        candidates = [n for n in document.descendants(main) if n['tag'] == 'A'
                      and urlsplit(urljoin(document.url, n['attrs'].get('href', ''))).path == entry['path']]
        require(len(candidates) == 1, 'Captured forum link missing or ambiguous in original DOM')
        link = candidates[0]
        require(document.text(link) == entry['label'], 'Captured forum label differs from original DOM')
        if not document.visible(link):
            continue
        node = lines.node_for(link, role='link')
        name = unquote(entry['path']).removeprefix('/f/')
        require(entry['path'].startswith('/f/') and '/' not in name and name and
                node.get('name', {}).get('value') == link['attrs'].get('aria-label')
                and node['name']['value'].startswith(name + ' — '),
                'Native forum name not retained in its actual AX link')
        witness = lines.witness(node)
        if witness:
            names.append(name); witnesses.append(witness)
    return {'forum_names': names, 'wiki_body_notice': False, 'witnesses': witnesses}


def _wiki(document, lines, page):
    from .heldout_reddit_query2 import wiki_checks, WIKI_NATIVE
    empty = {'forum_names': [], 'wiki_body_notice': False, 'witnesses': []}
    if urlsplit(page['url']).path != '/wiki/_create' or not wiki_checks(page['query2'], WIKI_NATIVE):
        return empty
    main = document.unique_id('main'); body = document.unique_id('wiki_body')
    require(body['tag'] == 'TEXTAREA' and body['attrs'].get('name') == 'wiki[body]'
            and document.within(body, main), 'Original DOM Wiki body identity differs')
    rows = [n for n in document.ancestors(body) if 'form__row' in _classes(n)]
    require(rows, 'Original DOM body row missing')
    row = rows[0]; owner = document.nodes[row['parent']]
    require('flow-slim' in _classes(owner), 'Original DOM body owner differs')
    help_node = document.unique_id('wiki_body_help')
    box = document.unique_id('wiki_body_markdown_help')
    require(help_node['parent'] == owner['index'] and box['parent'] == help_node['index']
            and box['tag'] == 'INPUT' and box['attrs'].get('type') == 'checkbox',
            'Original DOM help does not belong to this body')
    forms = [n for n in document.ancestors(body) if n['tag'] == 'FORM']
    require(forms and document.within(help_node, forms[0]), 'Original DOM body/help forms differ')
    described = body['attrs'].get('aria-describedby')
    require(not described or 'wiki_body_help' in described.split(), 'Original describedby differs')
    elements = [document.nodes[i] for i in document.children[help_node['index']]
                if document.nodes[i]['type'] == 1]
    pos = elements.index(box)
    require(pos + 1 < len(elements), 'Original notice sibling missing')
    notice = elements[pos + 1]
    require(notice['tag'] == 'SPAN' and {'fg-muted', 'text-sm'} <= _classes(notice)
            and document.text(notice) == WIKI_NATIVE['notice_text'],
            'Original body-bound permission notice differs')
    labels = [n for n in document.descendants(row) if n['tag'] == 'LABEL'
              and n['attrs'].get('for') == 'wiki_body']
    require(len(labels) == 1 and document.text(labels[0]) == 'Body *',
            'Original body field label differs from captured native widget')
    if not all(document.visible(n) for n in (body, labels[0], notice)):
        return empty
    # Native shipped notice has one literal text child. Complex/hidden subtree
    # rewrites are not guessed equivalent to that actual snapshot.
    texts = [n for n in document.descendants(notice) if n['type'] == 3 and n['value'].strip()]
    require(len(texts) == 1 and texts[0]['parent'] == notice['index'],
            'Notice text ownership is not the native direct text child')
    body_ax = lines.node_for(body, role='textbox')
    require(body_ax.get('name', {}).get('value', '').strip().startswith('Body'),
            'Actual body textbox lacks its public label')
    notice_ax = lines.node_for(texts[0], role='StaticText', element=False)
    require(notice_ax.get('name', {}).get('value') == WIKI_NATIVE['notice_text'],
            'Notice AX name differs from the body-bound DOM text')
    witnesses = [lines.witness(body_ax), lines.witness(notice_ax)]
    return {'forum_names': [], 'wiki_body_notice': all(w is not None for w in witnesses),
            'witnesses': [w for w in witnesses if w is not None]}


def verify_exposure(request_binding, private_records, *, source_task_id):
    """Consume verify_issued_requests' *verified* result and its original pages.

    Returns bound even on ordinary navigation pages or known budget omission.
    Only exact mapped lines yield names/body_notice. Malformed/missing mapping
    is unknown, never failure or inferred exposure. The caller independently
    evaluates native completion and checks the answer against these exposures.
    """
    result = {'version': VERSION, 'source_task_id': source_task_id,
              'task_completion_judged': False, 'eligible_for_training': False,
              'ordinary_actor_entry_qualified': False, 'exposures': []}
    try:
        require(source_task_id in (OLDEST, WIKI), 'Unsupported source')
        require(request_binding.get('status') == 'bound'
                and request_binding.get('source_task_id') == source_task_id,
                'Actual dispatch binding not verified')
        requests = request_binding['issued_requests']
        require(isinstance(requests, list) and requests, 'No issued requests')
        for issued in requests:
            require(issued['source_task_id'] == source_task_id, 'Issued source differs')
            index = issued['page_index']; record = private_records[index]
            require(record['source_task_id'] == source_task_id and record['step'] == index
                    and issued['step'] == index, 'Private source/step differs')
            page = record['page']
            require(digest(page) == record['page_sha256'] == issued['page_sha256'],
                    'Verified private page hash differs')
            snapshot = page['query2_raw_snapshot']
            require(snapshot['version'] == VERSION, 'Snapshot version differs')
            raw = snapshot['raw']; public = snapshot['public_projection']
            recorded = snapshot['record_observation']
            require(digest(recorded) == record['observation_sha256'] == issued['observation_sha256']
                    and public == {key: recorded[key] for key in
                        ('url', 'axtree_txt', 'axtree_full_txt') if key in recorded},
                    'Raw projection differs from verified final Session observation')
            require(raw['url'] == public['url'] == page['url'] == issued['url'],
                    'Private/raw/issued document URL differs')
            tree, full, viewport = _render(raw, 'axtree_full_txt' in public)
            _, no_style_full, no_style_viewport = _render(_without_styles(raw), 'axtree_full_txt' in public)
            require((full, viewport) == (no_style_full, no_style_viewport),
                    'Private styles changed public rendering')
            require(public['axtree_txt'] == viewport and
                    ('axtree_full_txt' not in public or public['axtree_full_txt'] == full),
                    'Raw snapshot no longer reproduces original observation')
            # Request binding already verifies which full/viewport AX was
            # selected. Match its exact prefix here, including line positions.
            actual = issued['observation']
            candidates = list(dict.fromkeys([public['axtree_txt'], public.get('axtree_full_txt', public['axtree_txt'])]))
            shortened = '\n[AX shortened at a complete line; scroll or use page filters to inspect more.]'
            originals = [text for text in candidates if actual == text or
                         (actual.endswith(shortened) and len(actual.splitlines()) > 1 and
                          text.splitlines()[:len(actual.splitlines()) - 1] == actual.splitlines()[:-1])]
            require(len(originals) >= 1, 'Issued AX has no original snapshot prefix')
            # If both share the truncated prefix, all actual target line
            # positions are identical; either preserves the same witness.
            original = originals[0]
            document = Document(raw); lines = Lines(tree, raw, original, actual)
            require(page['query2']['source_task_id'] == source_task_id, 'Query DOM source differs')
            if page.get('http_status') not in range(200, 300) or page.get('login_page') or page.get('error_page'):
                item = {'forum_names': [], 'wiki_body_notice': False, 'witnesses': []}
            else:
                item = _oldest(document, lines, page) if source_task_id == OLDEST else _wiki(document, lines, page)
            result['exposures'].append({'request_index': issued['request_index'],
                'generation_index': issued['generation_index'], 'step': index, 'page_index': index,
                'page_sha256': issued['page_sha256'],
                'request_messages_sha256': issued['request_messages_sha256'], **item})
        return dict(result, status='bound')
    except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
        return dict(result, status='unknown', reason=str(exc), exposures=[])
