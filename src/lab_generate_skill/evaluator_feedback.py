"""Post-execution teacher feedback. Never changes rewards or supplies actor actions."""
from urllib.parse import urlsplit

CHECKS = {
    'record_heading_identity':('page_identity','The final page identifies the bound record and record type; a matching list row alone is insufficient.'),
    'record_unchanged':('persisted_state','A navigation task leaves the requested record data unchanged.'),
    'records_unchanged':('persisted_state','A read-only task leaves the referenced records unchanged.'),
    'other_records_unchanged':('persisted_state','Records outside the requested target remain unchanged.'),
    'new_matching_record_saved':('persisted_state','Exactly one new record matching the task parameters was saved.'),
    'created_record_conditions':('persisted_state','The created record satisfies all additional requested saved settings.'),
    'exact_result_set':('answer_comparison','Return all and only the matching records, without duplicates; reference values are withheld.'),
    'requested_relationship_change':('persisted_state','The requested relationship was newly added or removed and saved on the correct product.'),
    'other_relationships_unchanged':('persisted_state','Other products and relationship types remain unchanged.'),
    'downloaded_matching_csv':('download_artifact','A completed CSV download contains the complete expected record set and checked fields; clicking Export alone is insufficient.'),
    'page_size_applied':('page_state','The committed page size, not just the input box, matches the requested setting.'),
    'requested_page_size':('page_state','The applied page size satisfies the requested change or value.'),
    'requested_columns_visible':('page_state','The visible data columns match the requested column set.'),
    'requested_tab_selected':('page_state','The requested dashboard tab is selected.'),
    'target_menu_identity':('page_menu','The open menu identifies the requested section.'),
    'target_menu_open':('page_menu','The requested main-menu section is expanded, not merely highlighted as the current page category.'),
    'requested_values_unchanged': ('persisted_state', 'The query must not change the requested saved values.'),
    'answer_schema': ('answer_comparison', 'Return exactly the requested JSON keys, without duplicate keys.'),
    **{'answer_'+field: ('answer_comparison', 'The returned '+field+' matches the requested object at the initial saved state; the reference is withheld.') for field in ('sku','price','stock_status','grand_total','order_currency_code')},
    'target_page_url': ('page_url', 'The final URL identifies the requested destination page.'),
    'target_page_title': ('document_title', 'The document title identifies the requested page section, independently of the selected record heading.'),
    'target_page_heading': ('page_heading', 'The current page heading identifies the requested destination.'),
    'same_local_deployment': ('current_page', 'The final page belongs to this task deployment.'),
    'valid_authenticated_page': ('current_page', 'The final page is authenticated and is not an error page.'),
    'product_identity': ('page_heading', 'The page identifies the product requested in the task.'),
    'order_identity': ('page_text', 'The required order identity appears on the target page.'),
    'history_visible': ('page_text', 'The final page text contains the Credit Memo History heading. This check alone does not establish DOM visibility.'),
    'requested_panel_open': ('page_panel', 'The requested record section is open.'),
    'related_panel_open': ('page_panel', 'The parent related-products section is open.'),
    'cross_sell_products_visible': ('page_panel', 'The requested cross-sell records appear in the open section.'),
    'exact_reference_answer': ('answer_comparison', 'The returned answer matches the requested field and answer format; the private reference answer is withheld.'),
    'persisted_requested_value': ('persisted_state', 'The requested field has the requested saved value; an unsaved form change is insufficient.'),
    'global_scope_unchanged': ('persisted_state', 'Changing the requested store scope leaves the global scope unchanged.'),
    'new_exact_comment_on_correct_memo': ('persisted_state', 'The requested comment was newly saved on the correct credit memo.'),
    'no_customer_notification': ('persisted_state', 'The comment did not notify the customer.'),
    'not_visible_on_storefront': ('persisted_state', 'The comment is not visible on the storefront.'),
    'no_additional_refund': ('persisted_state', 'No additional refund or unrelated order change occurred.'),
}


def admin_feedback(binding, judgment, page):
    """Use actual evaluator checks; do not infer a causal missing action from reward."""
    spec = binding['spec']
    if spec.get('credit_memo') and spec['kind'] == 'navigation':
        object_condition = 'Reach the credit memo detail page associated with the requested order, not only the order-level Credit Memos list.'
    elif binding.get('product_id'):
        object_condition = 'Reach the product detail page for the product requested in the task.'
    else:
        object_condition = 'Reach the task-bound target record page.'
    conditions = dict(CHECKS, correct_object=('page_url', object_condition))
    checks = []
    for name, passed in judgment.get('checks', {}).items():
        source, expected = conditions.get(name, ('evaluator', name.replace('_', ' ')))
        checks.append({'name': name, 'passed': passed, 'checked_from': source,
                       'expected_condition': expected})
    state = None
    if page is not None:
        path = urlsplit(page.get('url', '')).path
        kind = ('credit_memo_detail' if '/sales/creditmemo/view/' in path else
                'order_page' if '/sales/order/view/' in path else
                'product_detail' if '/catalog/product/edit/' in path else 'other_page')
        state = {'page_kind': kind, 'url': page.get('url'), 'heading': page.get('heading'),
                 'title': page.get('title'), 'login_page': page.get('login'),
                 'page_error': page.get('page_error'),
                 'credit_memo_history_heading_present': 'Credit Memo History' in page.get('text', '')}
    status = judgment.get('status', 'unknown')
    return {'version': 'teacher-evaluator-feedback-v1', 'available': True,
            'evaluator_version': judgment.get('version'),
            'protocol': 'local admin task contract; not the upstream Go-Browse model judge',
            'status': status, 'reward': judgment.get('reward'),
            'usable_as_task_failure': status == 'failure' and bool(checks),
            'reason': judgment.get('reason'), 'checks': checks,
            'failed_checks': [c['name'] for c in checks if c['passed'] is False],
            'final_state': state,
            'interpretation': 'Checks describe the evaluated final state, not the unique failure cause. Infer next actions from the recorded live controls; no particular click is required merely because it is absent.'}


def teacher_evidence(start, refs, attempts, best):
    fields = ('title', 'principle', 'when_to_apply')
    return {'task': start['task'], 'initial_observation': start['initial_observation'],
            'retrieved_skills': [{k: r[k] for k in fields} for r in refs],
            'attempts': [{'skill': a['skill'], 'success': a['success'], 'steps': a['steps'],
                          'trajectory': a['trajectory']['messages'],
                          'reward': a['trajectory']['task_output']['reward'],
                          'evaluator_feedback': a['trajectory'].get('evaluation_feedback',
                              {'available': False, 'reason': 'This evaluator adapter did not provide structured check details; do not invent them.'})}
                         for a in attempts],
            'best_successful_attempt': None if best is None else {'skill': best['skill'], 'steps': best['steps']}}
