"""Public task boundaries, not reference answers or prescribed action sequences.

Adding a more specific terminal state creates a versioned local training variant.
The original frozen evaluator and historical scores are not changed.
"""
import hashlib
import json

VERSION = 'admin-public-completion-v1'


def append_public_clause(goal, text, marker, separator):
    """Do not duplicate an already published clause or accept a conflicting one."""
    count = goal.count(marker)
    if count:
        if count != 1 or text not in goal:
            raise ValueError('Public task clause conflicts with bound initial state')
        return goal
    return goal + separator + text


def completion_text(binding):
    spec = binding['spec']
    mode = spec.get('mode', spec['kind'])
    if mode in ('page', 'page_navigation'):
        name = spec.get('label') or spec.get('heading')
        if not name:
            return ''
        text = f'Finish on the {name} management page itself, with its heading visible. A different subpage or an open global menu alone is not sufficient.'
        if spec.get('required_listing_scope'):
            text += ' The list must finish loading without a keyword search or active filters. A genuinely empty list is acceptable. Any page size or pagination page is allowed; visiting every page or copying all records is not required.'
        if spec.get('target_path') == '/catalog/category/':
            text += 'For Categories, finish in the existing-category management view, with an existing category selected; do not finish on a new-category form.'
        return text
    if mode == 'navigate':
        return 'Finish on the requested existing record\'s detail or edit page, with the record identity visible. A list row, search result, or repeating the identifier in the answer alone is not sufficient. Do not modify the record.'
    if mode == 'navigation' and spec.get('credit_memo') and spec.get('panel') == 'history':
        return 'Finish on the single credit memo detail page for the requested order, with Credit Memo History visible. The order page\'s Credit Memos list tab alone is not the terminal state for this local task.'
    if mode in ('form_panel', 'panel'):
        labels = spec.get('panel_labels') or spec.get('panels', [])
        return 'Finish on the requested record or form with the requested section(s) expanded and their contents visible. Merely mentioning a section title is not sufficient.'
    return ''


def declare_completion(binding):
    text = completion_text(binding)
    if not text or binding.get('public_completion_version') == VERSION:
        return binding
    b = dict(binding)
    previous = dict(b.get('task_revision') or {})
    source_goal = previous.get('source_goal', b['goal'])
    clause = 'Local completion requirement: ' + text
    b['goal'] = append_public_clause(b['goal'], clause, 'Local completion requirement:', '\n')
    b['kind'] = 'derived'
    b['public_completion_version'] = VERSION
    b['public_completion_requirement'] = text
    digest = hashlib.sha256(json.dumps({'goal':b['goal'], 'spec':b['spec'], 'version':VERSION}, sort_keys=True).encode()).hexdigest()[:12]
    b['runtime_task_id'] = b['source_task_id'] + '@derived-' + digest
    b['task_revision'] = {'version':VERSION, 'source_task_id':b['source_task_id'],
                         'source_goal':source_goal, 'runtime_goal':b['goal'],
                         'previous_revision':previous or None,
                         'reason':'Declare the existing local evaluator terminal-state boundary before execution.',
                         'contains_reference_answer':False, 'contains_action_sequence':False}
    return b
