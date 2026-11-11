"""Terminal typed answers against private snapshot references, not actor plans."""
import hashlib,json,re
from decimal import Decimal,InvalidOperation
from .admin_query_rules import parse_answer
from .site_navigation_rules import valid_initial_page
from .browser_prompt_contract import query_finish_instruction

VERSION='site-query-v1'
ADMISSION_VERSION='site-query-admission-v1'


def same_value(kind,actual,expected,*,record_fields=None,site_origin=None,minimum_records=None):
    if kind=='record_subset':
        from .query_record_sets import record_subset_matches
        return record_subset_matches(actual,expected,record_fields,minimum_records)
    if kind=='local_url':
        from .local_url_query import same_local_url
        return same_local_url(actual,expected,site_origin)
    if kind=='record_set':
        from .query_record_sets import record_set_matches
        return record_set_matches(actual,expected,record_fields)
    if actual is None or isinstance(actual,(bool,list,dict)):return False
    if kind in ('integer','decimal'):
        # No units/prefix stripping, NaN, infinity, commas or arithmetic expressions.
        if not re.fullmatch(r'-?\d+(?:\.\d+)?',str(actual)):return False
        try:
            a,b=Decimal(str(actual)),Decimal(str(expected))
            return a.is_finite() and b.is_finite() and a==b and (kind!='integer' or a==a.to_integral_value())
        except InvalidOperation:return False
    if kind=='string':return isinstance(actual,str) and actual.strip()==str(expected).strip()
    if kind=='string_choice':
        return isinstance(actual,str) and isinstance(expected,list) and bool(expected) and all(isinstance(x,str) for x in expected) and actual.strip() in expected
    raise ValueError('Unsupported query field type: '+kind)


def reference_fingerprint(reference):
    return hashlib.sha256(json.dumps(reference,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def contract_fingerprint(contract):
    keys=('task_id','source_task_id','domain','goal','start_path','query','heldout_quarantine','start_revision')
    payload={k:contract.get(k) for k in keys}
    if 'initial_page_policy'in contract:payload['initial_page_policy']=contract['initial_page_policy']
    return reference_fingerprint(payload)


def valid_query_page(contract,page,reference,*,site_origin):
    if valid_initial_page(page,site_origin=site_origin):return True
    policy=contract['query'].get('terminal_missing_resource')
    if not policy:return False
    # Only a specific absent resource with a matching independent reference
    # can be an expected terminal error document. Other 404s still fail.
    if set(policy)!={'page_policy','field','absent_value'} or policy['field']not in contract['query']['fields']:
        raise ValueError('Malformed absent-resource query policy')
    if reference['values'].get(policy['field'])!=policy['absent_value']:return False
    from .site_start_state import valid_task_start
    return valid_task_start({'initial_page_policy':policy['page_policy']},page,site_origin=site_origin)


def query_goal(contract):
    if contract.get('query',{}).get('family')=='gitlab_grouped_goal_query':
        from .gitlab_grouped_goal_runtime import public_goal
        return public_goal(contract)
    if contract.get('query',{}).get('family')=='map_typed_native':
        from .map_typed_runtime import public_goal
        return public_goal(contract)
    fields=contract['query']['fields']
    labels=(' For stock_status, use exactly one of the two allowed labels: \"In Stock\" or \"Out of Stock\".' if 'stock_status' in fields else '')
    for key,options in contract['query'].get('answer_labels',{}).items():
        if key not in fields or not options or not all(isinstance(x,str) for x in options):raise ValueError('Invalid public answer label set')
        labels+=' For '+key+', use exactly one of: '+json.dumps(options)+'.'
    meanings=contract['query'].get('field_meanings',{})
    if meanings:labels+=' Field meanings: '+json.dumps(meanings)+'.'
    for key,kind in fields.items():
        if kind in ('record_set','record_subset'):
            from .query_record_sets import validate_fields
            shape=contract['query'].get('record_fields',{}).get(key);validate_fields(shape)
            labels+=' '+key+' must be a JSON array of record objects with exactly these fields and types: '+json.dumps(shape)+'.'
            if kind=='record_subset':
                minimum=contract['query'].get('minimum_records',{}).get(key)
                if type(minimum)is not int or minimum<1:raise ValueError('Explicit minimum records required')
                labels+=' Return at least '+str(minimum)+' distinct matching records of your choice; each returned record must be correct. Order is unrestricted.'
            else:labels+=' Include every requested record; order is unrestricted. Use [] only when no records match.'
    if 'string_choice' in fields.values():labels+=' If several items tie for the requested maximum, return any one tied item as a single string.'
    if 'local_url' in fields.values():labels+=' URL fields must be complete URLs on the current task website, including its actual port when present; do not replace the host with a public website or return only a relative path.'
    return contract['goal']+'\n'+query_finish_instruction(fields)+' Read the requested values without modifying site records. Field types: '+', '.join(k+'='+('string' if v in ('string_choice','local_url') else v) for k,v in fields.items())+'.'+labels


def evaluate_query(contract,page,answer,initial,final,*,site_origin,runtime_error=None,observations=None):
    if contract.get('query',{}).get('family')=='map_typed_native':
        from .map_typed_runtime import evaluate
        return evaluate(contract,page,answer,initial,final,site_origin=site_origin,runtime_error=runtime_error,observations=observations)
    def unknown(reason):return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':reason}
    if runtime_error:return unknown('Environment or inference error; not a task failure')
    fields=contract['query']['fields']
    if not isinstance(initial,dict) or not isinstance(final,dict) or any(set(r.get('values',{}))!=set(fields) or not r.get('object_id') for r in (initial,final)):
        return unknown('Missing or incomplete task reference')
    if any(v is None for r in (initial,final) for v in r['values'].values()):return unknown('Reference field unavailable')
    for key,kind in fields.items():
        if kind in ('record_set','record_subset'):
            from .query_record_sets import canonical_records
            try:
                for state in (initial,final):
                    shape=contract['query'].get('record_fields',{}).get(key)
                    if kind=='record_subset':
                        from .query_record_sets import subset_reference
                        subset_reference(state['values'][key],shape,contract['query'].get('minimum_records',{}).get(key))
                    else:canonical_records(state['values'][key],shape)
            except ValueError:return unknown('Record-set reference or field schema unavailable')
        if kind=='string_choice' and any(not isinstance(r['values'][key],list) or not r['values'][key] or not all(isinstance(x,str) for x in r['values'][key]) for r in (initial,final)):
            return unknown('Valid answer alternatives unavailable')
    if not isinstance(page,dict) or type(page.get('http_status')) is not int or not isinstance(page.get('url'),str) or any(type(page.get(k)) is not bool for k in ('login_page','error_page')):
        return unknown('Missing terminal page health')
    if page['http_status']<200 or page['http_status']>=500:return unknown('Transport or server failure')
    checks={'page_valid':valid_query_page(contract,page,initial,site_origin=site_origin),
            'requested_records_unchanged':initial==final}
    try:
        value=parse_answer(answer);checks['answer_schema']=set(value)==set(fields)
    except (TypeError,ValueError):
        value={};checks['answer_schema']=False
    for key,kind in fields.items():checks['answer_'+key]=same_value(kind,value.get(key),initial['values'][key],record_fields=contract['query'].get('record_fields',{}).get(key),site_origin=site_origin,minimum_records=contract['query'].get('minimum_records',{}).get(key))
    status='success' if all(checks.values()) else 'failure'
    return {'version':VERSION,'status':status,'reward':float(status=='success'),'checks':checks,'reason':None}


def negative_query_answer(query, values):
    """Evaluator-only negative: prefer a valid but incorrect categorical answer."""
    wrong={}
    for key,value in values.items():
        labels=query.get('answer_labels',{}).get(key)
        if labels is not None:
            if not isinstance(labels,list) or len(set(labels))!=len(labels) or len(labels)<2 or value not in labels:
                raise ValueError('A categorical control needs a valid reference and alternative labels')
            wrong[key]=next(label for label in labels if label!=value)
        else:
            wrong[key]=int(value)+1 if query['fields'][key]=='integer' else 'incorrect-value'
    return wrong


def query_feedback(judgment,*,contract=None):
    if contract is not None and contract.get('query',{}).get('family')=='map_typed_native':
        from .map_typed_runtime import feedback
        return feedback(judgment)
    meanings={'page_valid':'The final page is valid for the query, including an explicitly checked missing resource when applicable.',
              'requested_records_unchanged':'Requested source records remain unchanged.',
              'answer_schema':'The final answer has exactly the requested fields.'}
    return {'status':judgment['status'],'reward':judgment['reward'],'reason':judgment.get('reason'),
            'checks':[{'name':k,'passed':v,'condition':meanings.get(k,'The returned value matches the requested field.')} for k,v in judgment['checks'].items()],
            'action_sequence_provided':False,'reference_values_provided':False}


def require_query_admission(contract,proof):
    if contract.get('query',{}).get('family')=='shopping_complete_native_training':
        from .shopping_complete_training_query_runtime import require_admission
        return require_admission(contract,proof)
    from .shopping_remaining_runtime import uses_normal_proof, require_admission as require_shopping_normal
    if uses_normal_proof(contract,proof):
        return require_shopping_normal(contract,proof)
    if contract.get('query',{}).get('family')=='map_typed_native':
        from .map_typed_runtime import require_admission
        return require_admission(contract,proof)
    if contract.get('heldout_quarantine'):raise ValueError('Heldout task cannot enter development tests')
    if proof.get('admission_version')!=ADMISSION_VERSION or proof.get('contract_fingerprint')!=contract_fingerprint(contract):raise ValueError('Stale or mismatched query proof')
    cycles=proof.get('cycles',[])
    if not proof.get('passed') or len(cycles)!=2 or any(not c.get('passed') or not c.get('initial_valid') or not c.get('ui_reference_matches') or c.get('initial_reference')!=c.get('final_reference') for c in cycles):raise ValueError('Two real reference/control/reset cycles required')
    from .reddit_query_protection import expected as expected_query_baseline
    expected_query_baseline(contract,proof)
    checks={'positive':'success','no_answer':'failure','wrong_value':'failure','404':'failure','login':'failure'}
    if contract['query'].get('wrong_object_query'):checks['wrong_object']='failure'
    from .query_record_sets import negative_record_answers
    checks.update({key:'failure' for key in negative_record_answers(contract['query'],cycles[0]['initial_reference']['values'])})
    from .query_record_sets import positive_record_answers
    checks.update({key:'success' for key in positive_record_answers(contract['query'],cycles[0]['initial_reference']['values'])})
    from .local_url_query import negative_url_names
    checks.update({key:'failure'for key in negative_url_names(contract['query'])})
    if any(c.get('checks')!=checks for c in cycles):raise ValueError('Required query control outcomes missing')
    if cycles[0].get('initial_reference')!=cycles[1].get('initial_reference') or not cycles[0].get('initial_reference'):raise ValueError('Reference changed across resets')
    if contract['query'].get('family')=='shopping_checkout_values' and cycles[0]['initial_reference'].get('quote_cache_matches_default_address_and_native_rates') is not True:
        raise ValueError('Checkout query requires the admitted default delivery state')
    if contract.get('domain')=='map':
        if any(r.get('map_guard_verified') is not True or not r.get('map_geographic_baseline') for r in cycles):
            raise ValueError('Full Map geographic reset/write guard proof required')
        if cycles[0]['map_geographic_baseline']!=cycles[1]['map_geographic_baseline']:
            raise ValueError('Map geographic baseline changed across resets')
