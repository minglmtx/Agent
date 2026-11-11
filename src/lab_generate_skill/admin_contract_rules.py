"""Declarative completion contracts. References stay private; no actor action repair."""
from decimal import Decimal, InvalidOperation
import json,re,hashlib
from urllib.parse import urlsplit, parse_qs
from .admin_query_rules import parse_answer

VERSION='admin-declarative-contract-v3'
ROUTES={
 'config':('/admin/system_currencysymbol/','/admin/system_currencysymbol/'),
 'newsletter_queue':('/newsletter/queue/','/newsletter/queue/edit/id/{id}/'),
 'address':('/customer/index/','/customer/index/edit/id/{parent_id}/'),
 'memo_item':('/sales/creditmemo/','/sales/creditmemo/view/creditmemo_id/{id}/'),
 'subscriber':('/newsletter/subscriber/','/newsletter/subscriber/'),
 'url_rewrite':('/admin/url_rewrite/index/','/admin/url_rewrite/edit/id/{id}/'),
 'newsletter_template':('/newsletter/template/','/newsletter/template/edit/id/{id}/'),
 'email_template':('/admin/email_template/','/admin/email_template/edit/id/{id}/'),
 'cms_block':('/cms/block/','/cms/block/edit/block_id/{id}/'),
 'attribute':('/catalog/product_attribute/','/catalog/product_attribute/edit/attribute_id/{id}/'),
 'tax_class':('/customer/group/new/','/customer/group/new/'),
 'category':('/catalog/category/','/catalog/category/edit/id/{id}/'),
 'generic':('/catalog/product/','/catalog/product/'),
 'dashboard':('/admin/dashboard/','/admin/dashboard/'),
 'order':('/sales/order/','/sales/order/view/order_id/{id}/'),
 'shipment':('/sales/shipment/','/sales/shipment/view/shipment_id/{id}/'),
 'memo':('/sales/creditmemo/','/sales/creditmemo/view/creditmemo_id/{id}/'),
 'customer':('/customer/index/','/customer/index/edit/id/{id}/'),
 'group':('/customer/group/','/customer/group/edit/id/{id}/'),
 'product':('/catalog/product/','/catalog/product/edit/id/{id}/store/0/'),
 'cms_page':('/cms/page/','/cms/page/edit/page_id/{id}/'),
 'search_term':('/search/term/','/search/term/edit/id/{id}/'),
}
NUMERIC={'include_in_menu','count','price','special_price','qty','grand_total','total_qty','tax_class_id','group_id','website_id','status','state','gender','is_active','popularity','num_results','backorders','use_config_backorders','gift_message_available','position','parent_id','subscriber_status','redirect_type'}


def scalar(value):
    return '' if value is None else re.sub(r'\s+',' ',str(value)).strip()


def equivalent(field,a,b):
    if field=='created_at':
        from .admin_display_values import timestamp_value
        try:return timestamp_value(a)==timestamp_value(b)
        except (ValueError,TypeError):return False
    if field in ('name','customer_name','query_text'):
        from html import unescape
        return isinstance(a,str) and unescape(scalar(a))==unescape(scalar(b))
    if field.endswith('_date'):return isinstance(a,str) and bool(a.strip()) and scalar(a)[:10]==scalar(b)[:10]
    if field=='dob':return isinstance(a,str) and scalar(a)[:10]==scalar(b)[:10]
    if field=='excluded_websites':return isinstance(a,list) and len(a)==len(set(a)) and sorted(a)==sorted(b)
    if isinstance(a,(bool,list,dict)):return False
    if field.endswith('country_id'):
        labels={'US':'United States','GB':'United Kingdom','CA':'Canada'}
        return scalar(a).casefold() in {scalar(b).casefold(),labels.get(str(b),'').casefold()}
    if field in NUMERIC:
        try:
            x,y=Decimal(str(a)),Decimal(str(b))
            return x.is_finite() and y.is_finite() and x==y
        except InvalidOperation:pass
    return scalar(a)==scalar(b)


def matches(item,criteria):
    for field,expected in criteria.items():
        actual=item.get(field)
        if isinstance(expected,dict):
            op=expected['op'];v=expected.get('value')
            if op=='one_of':ok=any(equivalent(field,actual,x) for x in v)
            elif op=='contains':ok=scalar(v).casefold() in scalar(actual).casefold()
            elif op=='nonempty':ok=bool(scalar(actual))
            elif op=='month':ok=bool(actual) and str(actual)[5:7]==str(v).zfill(2)
            elif op=='prefix':ok=scalar(actual).startswith(str(v))
            elif op in ('lt','gt'):
                try:ok=(Decimal(str(actual))<Decimal(str(v))) if op=='lt' else (Decimal(str(actual))>Decimal(str(v)))
                except InvalidOperation:ok=False
            elif op=='between':ok=actual is not None and str(v[0])<=str(actual)<str(v[1])
            else:raise ValueError('unsupported_filter:'+op)
        else:ok=equivalent(field,actual,expected)
        if not ok:return False
    return True


def records(state,entity):
    if 'records_error' in state:raise ValueError('extended_state_probe_failed')
    if entity in state.get('record_errors',{}):raise ValueError('state_probe_failed:'+entity)
    return state['records'][entity]


def selected(spec,state):
    items=[r for r in records(state,spec['entity']) if matches(r,spec.get('match',{}))]
    if spec.get('order_by'):
        field=spec['order_by'];numeric=field in NUMERIC
        items=sorted(items,key=lambda r:Decimal(str(r[field])) if numeric else str(r[field]),reverse=spec.get('descending',False))
    if spec.get('limit') is not None:items=items[:spec['limit']]
    return items


def only(items):
    if len(items)!=1:raise ValueError('target_missing_or_ambiguous:'+str(len(items)))
    return items[0]


def reference(spec,state):
    items=selected(spec,state)
    if spec['mode']=='query':items=[only(items)]
    fields=spec['fields']
    if spec.get('aggregate')=='count':return {'count':len(items)}
    rows=[{f:r.get(f) for f in fields} for r in items]
    if 'created_at' in fields:
        from .admin_display_values import local_timestamp
        for row in rows:row['created_at']=local_timestamp(row['created_at'],state.get('display_timezone'))
    if spec['mode']=='query':return rows[0]
    return {'items':sorted(rows,key=lambda r:json.dumps(r,sort_keys=True))}


def bind_contract(row,state,spec):
    from .admin_public_contract import append_public_clause
    spec=dict(spec);revision=None
    if spec.get('resolve_ambiguous_customer'):
        matches_now=selected(spec,state)
        if len(matches_now)>1:
            target=sorted(matches_now,key=lambda r:(str(r['email']),int(r['entity_id'])))[0]
            if sum(r['email']==target['email'] for r in matches_now)!=1:raise ValueError('email_still_ambiguous')
            spec['match']={**spec['match'],'email':target['email']}
            revision={'version':'admin-email-disambiguation-v1','source_goal':row['goal'],'chosen_email':target['email'],
                'selection':'lexicographically_first_email_in_initial_local_snapshot','uses_later_actor_actions':False}
            clause='For this local training variant, the target account email is '+target['email']+'.'
            row={**row,'goal':append_public_clause(row['goal'],clause,'For this local training variant, the target account email is ',' '),'kind':'derived'}
    mode=spec['mode'];b={'spec':dict(spec),'source_task_id':row['source_task_id'],'goal':row['goal'],
       'kind':row['kind'],'scope_id':0,'status':'ready_for_single_attempt','evaluator_version':VERSION,
       'not_formal_training_admission':True,'start_path':spec.get('start_path',ROUTES[spec['entity']][0])}
    if revision:b['task_revision']=revision
    if spec.get('explicit_selected_order'):
        item=only(selected(spec,state))
        clause='For this local training variant, the selected order is #'+item['increment_id']+'.'
        b['goal']=append_public_clause(row['goal'],clause,'For this local training variant, the selected order is #',' ')
        b['kind']='derived'
        b['task_revision']={'version':'admin-selected-order-v1','source_goal':row['goal'],'order_increment_id':item['increment_id'],'selection':'initial_snapshot_matching_preconditions_then_lowest_entity_id','uses_later_actor_actions':False}
    if spec.get('start_category_name'):
        parent=only([r for r in records(state,'category') if r.get('name')==spec['start_category_name']])
        b['start_path']='/catalog/category/edit/id/'+str(parent['entity_id'])+'/'
    if mode=='page_text_query':b['answer_fields']=['description']
    if mode=='ui_query':b['answer_fields']=list(spec['ui_fields'])
    if mode in ('query','collection_query'):
        b['query_reference']=reference(spec,state)
        b['answer_fields']=list(b['query_reference'])
    if mode not in ('collection_query','create','tab','page','form_panel','grid','export','draft_reset','bulk_update','pdf','page_text_query','ui_contract','ui_query'):
        item=only(selected(spec,state));b['record_id']=int(item['entity_id']);b['initial_record']=item
        b['target_path']=ROUTES[spec['entity']][1].format(id=b['record_id'],**{k:v for k,v in item.items() if k!='id'})
        if mode in ('query','update','panel','links','media'):b['start_path']=b['target_path']
        if spec.get('record_start_path'):b['start_path']=spec['record_start_path'].format(id=b['record_id'],**{k:v for k,v in item.items() if k!='id'})
        if spec['entity']=='product' and mode in ('query','update','panel','links','media'):
            b['product_id']=b['record_id'];b['product_name']=item['name']
        if mode=='links' and spec['operation']=='remove':
            if not any(int(r['product_id'])==b['record_id'] and int(r['link_type_id'])==spec['link_type_id'] for r in records(state,'link')):raise ValueError('initial_link_to_remove_missing')
        if mode=='update' and update_matches(spec,item,item):raise ValueError('goal_already_satisfied_at_reset')
    if mode=='bulk_update':
        items=selected(spec,state)
        if not items:raise ValueError('bulk_target_set_empty')
        b['selected_record_ids']=[str(r['entity_id']) for r in items]
        if all(update_matches(spec,r,r) for r in items):raise ValueError('bulk_goal_already_satisfied')
    if mode=='create' and selected(spec,state):raise ValueError('target_record_already_exists')
    if b['kind']=='derived' or b['goal']!=row.get('source_goal',row['goal']):
        revision={**b.get('task_revision',{}),'version':b.get('task_revision',{}).get('version','admin-derived-contract-v1'),
                  'source_task_id':row['source_task_id'],'source_goal':row.get('source_goal',row['goal']),'runtime_goal':b['goal']}
        digest=hashlib.sha256(json.dumps({'goal':b['goal'],'spec':spec},sort_keys=True).encode()).hexdigest()[:12]
        b['runtime_task_id']=row['source_task_id']+'@derived-'+digest
        b['task_revision']=revision
    else:b['runtime_task_id']=row['source_task_id']
    return b


def update_matches(spec,item,initial):
    for field,condition in spec['conditions'].items():
        value=item.get(field);op=condition['op']
        if op=='eq':ok=equivalent(field,value,condition['value'])
        elif op=='json_member':
            try:ok=json.loads(value).get(condition['key'])==condition['value']
            except (ValueError,TypeError,AttributeError):ok=False
        elif op=='plain_text':
            from .admin_text_content import plain_text
            ok=plain_text(value)==plain_text(condition['value'])
        elif op=='changed_valid_number':
            try:
                n=Decimal(str(value));ok=n.is_finite() and n>=Decimal(str(condition.get('min',0))) and not equivalent(field,value,initial.get(field))
            except InvalidOperation:ok=False
        elif op=='discount':
            try:
                n=Decimal(str(value));ok=n.is_finite() and 0<n<Decimal(str(initial['price']))
            except InvalidOperation:ok=False
        elif op=='includes':ok=isinstance(value,list) and str(condition['value']) in list(map(str,value))
        elif op=='excludes':ok=isinstance(value,list) and str(condition['value']) not in list(map(str,value))
        elif op=='changed_choice':ok=str(value) in list(map(str,condition['choices'])) and not equivalent(field,value,initial.get(field))
        else:raise ValueError('unsupported_predicate:'+op)
        if not ok:return False
    return True


def goal(binding):
    spec=binding['spec']
    if spec['mode'] not in ('query','collection_query','page_text_query','ui_query'):return binding['goal']
    from .browser_prompt_contract import query_finish_instruction
    fields=binding['answer_fields']
    description=''
    if spec['mode']=='collection_query' and not spec.get('aggregate'):description=' Each items entry must contain exactly these fields: '+', '.join(spec['fields'])+'. Return every matching record, without duplicates. An empty result is {"items": []}.'
    return binding['goal']+'\n'+query_finish_instruction(fields, record_fields=spec.get('fields', ()), entity=spec.get('entity'))+description+' Do not modify saved records.'


def navigation_target_matches(binding, page):
    """Match an exact object route, including Magento's implicit default scope.

    An omitted /store/0 route is accepted only with the actual scope control
    proving store zero. Wrong objects, nondefault scopes and extra routes are
    never inferred equivalent from the page title alone.
    """
    parsed=urlsplit(page['url'])
    target='/admin'+binding['target_path'].rstrip('/')
    if binding['spec'].get('entity')=='product' and target.endswith('/store/0'):
        if any(value!='0' for value in parse_qs(parsed.query,keep_blank_values=True).get('store',[])):
            return False
        implicit=target[:-len('/store/0')]
        if re.fullmatch(re.escape(implicit)+r'(?:/key/[^/]+)?/?',parsed.path):
            scopes=[str(f.get('value')) for f in page.get('form_fields',[]) if f.get('name')=='store_switcher']
            return scopes==['0']
    return bool(re.fullmatch(re.escape(target)+r'(?:/key/[^/]+)?/?',parsed.path))


def checks(binding,before,after,page,answer):
    spec=binding['spec'];mode=spec['mode'];entity=spec['entity']
    common={'same_local_deployment':urlsplit(page['url']).netloc==binding['site_netloc'],
            'valid_authenticated_page':not(page['login'] or page['page_error'])}
    if spec.get('required_grid_operation'):
        final_path=spec.get('required_final_path')
        if final_path:
            common['correct_page']=urlsplit(page['url']).path.rstrip('/')==final_path.rstrip('/')
            if not all(common.values()):
                return common
        from .admin_grid_operation import checks as grid_operation_checks
        common.update(grid_operation_checks(spec['required_grid_operation'],page.get('ui_contract',{}).get('grid_operation')))
    if mode in ('ui_contract','ui_query'):
        from .admin_ui_contract import checks as ui_checks
        common.update(ui_checks(binding,before,after,page,answer))
    elif mode=='page_text_query':
        common['correct_page']=urlsplit(page['url']).path.rstrip('/')==('/admin'+binding['start_path']).rstrip('/')
        common['records_unchanged']=before['records']==after['records']
        try:got=parse_answer(answer)
        except (ValueError,TypeError):got={}
        expected=binding.get('query_reference')
        if not expected:raise ValueError('Missing initial page text reference')
        common['answer_schema']=set(got)=={'description'}
        common['correct_partner_description']=scalar(got.get('description'))==scalar(expected['description'])
        common['partner_still_available']=scalar(page.get('partner_cards',{}).get(spec['partner']))==scalar(expected['description'])
    elif mode=='pdf':
        from .admin_pdf import matches_pdf
        common['records_unchanged']=records(before,entity)==records(after,entity)
        common['downloaded_correct_documents']=any(matches_pdf(d,spec,selected(spec,before)) for d in page.get('downloads',[]))
    elif mode=='media':
        from .admin_media import checks as media_checks
        common.update(media_checks(spec,binding,before,after))
    elif mode=='mail':
        from .admin_mail import delivered
        common['new_matching_mail_delivered']=delivered(records(before,'mail'),records(after,'mail'),binding['initial_record']['customer_email'],[binding['initial_record']['increment_id']])
        common['order_unchanged']=records(before,'order')==records(after,'order')
    elif mode=='export':
        from .admin_downloads import csv_matches
        common['records_unchanged']=records(before,entity)==records(after,entity)
        common['downloaded_matching_csv']=any(csv_matches(d,spec,selected(spec,before)) for d in page.get('downloads',[]))
    elif mode=='links':
        def edges(state):return {str(r['linked_product_id']) for r in records(state,'link') if int(r['product_id'])==binding['record_id'] and int(r['link_type_id'])==spec['link_type_id']}
        initial,final=edges(before),edges(after)
        common['requested_relationship_change']=(bool(final-initial) and initial<=final) if spec['operation']=='add' else (bool(initial-final) and final<=initial)
        def unrelated(state):return [{k:v for k,v in r.items() if k!='entity_id'} for r in records(state,'link') if int(r['product_id'])!=binding['record_id'] or int(r['link_type_id'])!=spec['link_type_id']]
        common['other_relationships_unchanged']=unrelated(before)==unrelated(after)
    elif mode=='grid':
        common['correct_grid_page']=urlsplit(page['url']).path.rstrip('/')==('/admin'+binding['start_path']).rstrip('/')
        grid=page.get('grid',{})
        if spec['operation']=='page_size':
            current=grid.get('committed_page_size');initial=binding.get('initial_grid',{}).get('committed_page_size')
            if current is None or initial is None:raise ValueError('committed_grid_size_probe_unresolved')
            common['page_size_applied']=isinstance(current,(int,float)) and current>0 and current==grid.get('page_size')
            common['requested_page_size']=current==spec['expected'] if 'expected' in spec else current!=initial
            common['grid_fits_requested_size']=0<=grid.get('row_count',-1)<=current
        elif spec['operation']=='columns':
            actual={x.casefold() for x in grid.get('columns',[]) if x not in ('Actions','Action','Options','Select','Select All')}
            if not actual:raise ValueError('grid_columns_unresolved')
            common['requested_columns_visible']=actual==set(x.casefold() for x in spec['columns'])
        elif spec['operation']=='changed_columns':
            initial=set(binding.get('initial_grid',{}).get('columns',[]));actual=set(grid.get('columns',[]))
            if not initial or not actual:raise ValueError('grid_columns_unresolved')
            common['visible_columns_changed']=actual!=initial
            common['data_columns_remain']=bool(actual-{'Actions','Options','Select','Select All'})
        elif spec['operation']=='hide_column':
            actual=grid.get('columns',[])
            if not actual:raise ValueError('grid_columns_unresolved')
            common['column_initially_visible']=spec['column'] in binding.get('initial_grid',{}).get('columns',[])
            common['column_hidden']=spec['column'] not in actual
        elif spec['operation']=='view_menu':common['view_menu_open']=grid.get('view_menu_open') is True
        else:raise ValueError('unsupported_grid_operation')
    elif mode=='draft_reset':
        common['correct_form']=urlsplit(page['url']).path.rstrip('/')==('/admin'+binding['start_path']).rstrip('/')
        fields={f['name']:f for f in page.get('form_fields',[]) if f.get('visible')}
        common['form_reset']=all(k in fields and fields[k].get('value')==v for k,v in binding.get('form_defaults',{}).items()) and bool(binding.get('form_defaults'))
        common['no_record_created']=records(before,entity)==records(after,entity)
    elif mode=='page':
        from .admin_pilot import page_navigation_checks
        common.update(page_navigation_checks(spec,page,binding['site_netloc']))
        for name in spec.get('required_fields',[]):
            common['required_field_visible_'+name]=any(f.get('name')==name and f.get('visible') and f.get('required') for f in page.get('form_fields',[]))
    elif mode=='form_panel':
        common['correct_new_form']=urlsplit(page['url']).path.rstrip('/')==('/admin'+binding['start_path']).rstrip('/') and page['heading']==spec['heading']
        for key in spec['panels']:
            common['panel_open_'+key]=bool(page['panels'].get(key,{}).get('opened'))
    elif mode=='tab':
        common['correct_page']=urlsplit(page['url']).path.rstrip('/')==('/admin'+binding['start_path']).rstrip('/')
        common['requested_tab_selected']=any(t['selected'] and ' '.join(t['text'].split())==' '.join(spec['tab_label'].split()) for t in page.get('tabs',[]))
    elif mode=='panel':
        route='/catalog/'+entity+'/edit/id/'
        common['correct_object']=bool(re.search(re.escape(route)+str(binding['record_id'])+r'(?:/|$)',urlsplit(page['url']).path))
        common['record_heading_identity']=page['heading'].strip()==(binding['initial_record']['name']+(' (ID: '+str(binding['record_id'])+')' if entity=='category' else ''))
        for key in spec['panels']:
            if key not in page['panels']:raise ValueError('missing_panel_probe')
            common['panel_open_'+key]=page['panels'][key]['present'] and page['panels'][key]['opened']
    elif mode=='navigate':
        item=only([r for r in records(after,entity) if int(r['entity_id'])==binding['record_id']])
        common['correct_object']=navigation_target_matches(binding,page)
        identity=item.get('increment_id',item.get('name',item.get('query_text',scalar(item.get('firstname'))+' '+scalar(item.get('lastname')))))
        if entity=='memo':
            common['record_heading_identity']=page['heading'].strip()=='View Memo' and bool(re.search(r'Order\s*#\s*'+re.escape(item['order_increment_id'])+r'\b',page['text']))
        else:common['record_heading_identity']=bool(re.search(r'(?<!\w)'+re.escape(str(identity))+r'(?!\w)',page['heading'],re.I))
        common['record_unchanged']=records(before,entity)==records(after,entity)
    elif mode in ('query','collection_query'):
        common['records_unchanged']=records(before,entity)==records(after,entity)
        expected=reference(spec,before)
        if expected!=binding['query_reference']:raise ValueError('query_reference_changed')
        try:got=parse_answer(answer)
        except (ValueError,TypeError):common['answer_schema']=False;return common
        common['answer_schema']=set(got)==set(expected)
        if mode=='query' or spec.get('aggregate'):
            for f,v in expected.items():common['answer_'+f]=equivalent(f,got.get(f),v)
        else:
            gotrows=got.get('items');refs=expected['items']
            valid=isinstance(gotrows,list) and all(isinstance(r,dict) and set(r)==set(spec['fields']) for r in gotrows)
            common['answer_schema']=common['answer_schema'] and valid
            if valid:
                # Multiset matching rejects duplicates, omissions and extra records.
                unused=list(refs)
                for r in gotrows:
                    index=next((i for i,x in enumerate(unused) if all(equivalent(f,r[f],x[f]) for f in spec['fields'])),None)
                    if index is None:common['exact_result_set']=False;break
                    unused.pop(index)
                else:common['exact_result_set']=not unused
    elif mode=='update':
        old=only([r for r in records(before,entity) if int(r['entity_id'])==binding['record_id']])
        current=only([r for r in records(after,entity) if int(r['entity_id'])==binding['record_id']])
        common['persisted_requested_value']=update_matches(spec,current,old)
        common['other_records_unchanged']=[r for r in records(before,entity) if r['entity_id']!=old['entity_id']]==[r for r in records(after,entity) if r['entity_id']!=old['entity_id']]
    elif mode=='bulk_update':
        ids=set(binding['selected_record_ids'])
        old={str(r['entity_id']):r for r in records(before,entity)}
        current={str(r['entity_id']):r for r in records(after,entity)}
        common['all_selected_records_updated']=all(i in current and update_matches(spec,current[i],old[i]) for i in ids)
        common['other_records_unchanged']={k:v for k,v in old.items() if k not in ids}=={k:v for k,v in current.items() if k not in ids}
    elif mode=='create':
        old_ids={str(r['entity_id']) for r in records(before,entity)}
        new=[r for r in selected(spec,after) if str(r['entity_id']) not in old_ids]
        common['new_matching_record_saved']=len(new)==1
        if spec.get('create_conditions'):
            common['created_record_conditions']=len(new)==1 and update_matches({'conditions':spec['create_conditions']},new[0],{})
        common['existing_records_unchanged']=records(before,entity)==[r for r in records(after,entity) if str(r['entity_id']) in old_ids]
        if spec.get('required_mail'):
            from .admin_mail import delivered
            mail=spec['required_mail'];common['welcome_delivered_locally']=delivered(records(before,'mail'),records(after,'mail'),mail['recipient'],mail['required_text'])
    else:raise ValueError('unsupported_contract_mode')
    return common
