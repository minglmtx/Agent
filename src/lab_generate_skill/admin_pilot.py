"""Single-pass local actor pilot: adapted WebArena-style rules, no LLM judge.

These are pilot rules for Go-Browse goals, NOT official WebArena task configs.
Only read-only database probes and actual final browser state feed the evaluator.
"""
from __future__ import annotations
import ast
import hashlib
import html
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

VERSION = 'admin-single-pass-rules-v3'
SPECS = {
 '8db58162c0790f718086': {'kind':'navigation','product':'Blue T-Shirt','panel':'review'},
 '55102868e4425a2690aa': {'kind':'navigation','credit_memo':True,'panel':'history'},
 '47c36ebf4069de79d6d3': {'kind':'navigation','product':'Blue T-Shirt','panel':'crosssell'},
 'b27df1521a689351b66b': {'kind':'navigation','product':'Blue T-Shirt','panel':'content'},
 '284810473d5423137bd6': {'kind':'query','product':'Blue T-Shirt','field':'price'},
 '5bdea638324ccae37801': {'kind':'query','product':'Blue T-Shirt','field':'sku'},
 'e5bd171b0b1550f4d11d': {'kind':'query','order':True,'field':'status'},
 '83bdf10dfe02ee8aa9fc': {'kind':'update','product':'Blue T-Shirt','field':'price','expected':'29.99'},
 '589ffd7db76177dbaeaa': {'kind':'update','product':'Blue T-Shirt','field':'tax_class_id','expected':'0'},
 'f7f15b9942542a827638': {'kind':'update','product':'Blue T-Shirt','field':'visibility','expected':'4'},
 '5eddb585793c30159e97': {'kind':'comment','credit_memo':True,
     'expected':'Customer reported a product quality issue; review required.'},
 'fca8f1b4c4898b3b525e': {'kind':'update','product':'Example Product Deluxe 2023','field':'short_description',
     'expected':'Example Product Deluxe 2023 features a modular design, replaceable inserts, and a reusable case.','scope':'default',
     'protect_unrelated_state':True,
     'native_save_normalizations':[{'field':'gift_message_available','before_present':False,'before':None,'after':'0'}]},
}


# Explicit, reviewed page-navigation goals use a separate local scoring protocol.
PAGE_TASK_SPECS_PATH = Path(__file__).resolve().parents[2] / 'configs/admin-page-task-specs-v1.json'
if PAGE_TASK_SPECS_PATH.exists():
    _page_specs=json.loads(PAGE_TASK_SPECS_PATH.read_text())
    if set(_page_specs).intersection(SPECS):raise ValueError('Duplicate task specification')
    SPECS.update(_page_specs)


QUERY_TASK_SPECS_PATH = Path(__file__).resolve().parents[2] / 'configs/admin-query-task-specs-v1.json'
if QUERY_TASK_SPECS_PATH.exists():
    _query_specs=json.loads(QUERY_TASK_SPECS_PATH.read_text())
    if set(_query_specs).intersection(SPECS):raise ValueError('Duplicate query task specification')
    SPECS.update(_query_specs)


EXTENSION_SPECS_PATH = Path(__file__).resolve().parents[2] / 'configs/admin-navigation-extension-v1.json'
if EXTENSION_SPECS_PATH.exists():
    _extension=json.loads(EXTENSION_SPECS_PATH.read_text())
    if set(_extension).intersection(SPECS):raise ValueError('Duplicate extension task')
    SPECS.update(_extension)


CONTRACT_SPECS_PATH = Path(__file__).resolve().parents[2] / 'configs/admin-completion-contracts-v1.json'
if CONTRACT_SPECS_PATH.exists():
    _contracts=json.loads(CONTRACT_SPECS_PATH.read_text())
    if set(_contracts).intersection(SPECS):raise ValueError('Duplicate completion contract')
    SPECS.update(_contracts)


def page_navigation_checks(spec, page, site_netloc):
    path=urlsplit(page['url']).path
    # Magento may add index or an authentication key, but another object/detail
    # page must not pass by a loose prefix match.
    targets=[spec['target_path']]
    aliases=spec.get('target_path_aliases',[])
    if not isinstance(aliases,list) or any(
            not isinstance(p,str) or not p.startswith('/') or p.startswith('//')
            or any(c in p for c in ('?', '#', '\\')) or any(c.isspace() for c in p)
            or any(part in ('.','..') for part in p.split('/')) for p in aliases):
        raise ValueError('Invalid native page route aliases')
    targets.extend(aliases)
    # Explicit alternatives are independently proved native routes for this
    # page contract. They never grant a prefix match or alias another object.
    pattern='(?:'+'|'.join(re.escape('/admin'+p.rstrip('/')) for p in targets)+r')(?:/index)?(?:/key/[^/]+)?/?'
    heading=plain(page['heading'])
    heading_ok=(bool(re.fullmatch(spec['heading_pattern'],heading)) if spec.get('heading_pattern')
                else heading.casefold()==spec['heading'].casefold())
    checks={
        'same_local_deployment':urlsplit(page['url']).netloc==site_netloc,
        'valid_authenticated_page':not (page['login'] or page['page_error']),
        'target_page_url':bool(re.fullmatch(pattern,path)),
        'target_page_heading':heading_ok,
    }
    if 'page_title_suffix' in spec:
        # Category pages use the selected category as h1; section identity stays in the document title.
        suffix=spec['page_title_suffix']
        if not isinstance(suffix,list) or not suffix or any(not isinstance(x,str) or not x.strip() for x in suffix):
            raise ValueError('Invalid page title identity contract')
        title_parts=[part.strip().casefold() for part in plain(page.get('title','')).split(' / ')]
        checks['target_page_title']=title_parts[-len(suffix):]==[part.casefold() for part in suffix]
    if spec.get('required_listing_scope'):
        target = checks['same_local_deployment'] and checks['target_page_url']
        # A failed target document can also lose its heading. Classify that
        # evidence fault before applying business checks to the page shell.
        if urlsplit(page['url']).scheme == 'chrome-error' or (target and page['page_error']):
            raise ValueError('Requested listing document unavailable')
        if target and not page['login']:
            from .admin_listing_scope import checks as listing_checks
            checks.update(listing_checks(spec['required_listing_scope'], page.get('ui_contract', {}).get('unfiltered_listing')))
    return checks


class BindingError(ValueError):
    pass


def claim_attempt(directory, record):
    try:
        with (Path(directory)/'attempt-started.json').open('x') as f:
            json.dump(record,f)
        return True
    except FileExistsError:
        return False


def file_hash(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def get_attr(product, field, store=0, *, effective=False):
    if field == 'sku':return product['sku']
    values=product.get('attributes',{}).get(field,{})
    value=values.get(str(store))
    if value is None and effective:value=values.get('0')
    return value


def one(values, reason):
    if len(values)!=1:raise BindingError(reason)
    return values[0]


def plain(value):
    return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]*>',' ',str(value or '')))).strip()


def same_value(a,b,field):
    if a is None or b is None:return False
    if field in ('price','tax_class_id','visibility'):
        try:return Decimal(str(a))==Decimal(str(b))
        except InvalidOperation:return False
    return plain(a)==plain(b)


def actor_goal(binding):
    if binding['spec']['kind']=='admin_contract':
        from .admin_contract_rules import goal
        return goal(binding)
    if binding['spec']['kind']=='typed_query':
        from .admin_query_rules import query_goal
        return query_goal(binding)
    goal=binding['goal']
    if binding['spec']['kind']=='query':
        goal+='\nFor this query, use action=finish with answer as a plain number or string. The executor formats the answer. Use a number without a currency symbol for a price; use a string for other fields.'
    return goal


def _bind(row, state):
    from .deterministic_admin_policy import require_local_task
    require_local_task(row['source_task_id'])
    from .admin_category_operations import definition as category_definition, bind as bind_category
    category = category_definition(row['source_task_id'])
    if category is not None:return bind_category(row,state,category)
    from .admin_reviewed_operations import definition as reviewed_definition, bind as bind_reviewed
    reviewed = reviewed_definition(row['source_task_id'])
    if reviewed is not None:return bind_reviewed(row,state,reviewed)
    from .admin_native_mutation import definition as native_definition, bind as bind_native
    native = native_definition(row['source_task_id'])
    if native is not None:return bind_native(row,state,native)
    from .admin_material_creation import material_definition, bind_creation
    material = material_definition(row['source_task_id'])
    if material is not None:
        return bind_creation(row, state, material)
    spec=dict(SPECS[row['source_task_id']])
    if spec['kind']=='admin_contract':
        from .admin_contract_rules import bind_contract
        try:return bind_contract(row,state,spec)
        except (KeyError,ValueError,TypeError) as exc:raise BindingError('contract_binding:'+str(exc)) from exc
    if spec['kind']=='typed_query':
        from .admin_query_rules import bind_query
        try:return bind_query(row,state,spec)
        except (KeyError,ValueError,TypeError) as exc:raise BindingError('query_binding:'+str(exc)) from exc
    binding={'spec':spec,'source_task_id':row['source_task_id'],'goal':row['goal'],
             'kind':row['kind'],'scope_id':0,'status':'ready_for_single_attempt',
             'evaluator_version':VERSION,'not_formal_training_admission':True}
    if spec.get('protect_unrelated_state'):
        if row.get('kind') != 'derived' or not row.get('runtime_task_id'):
            raise BindingError('protected_material_revision_requires_derived_identity')
        binding['runtime_task_id'] = row['runtime_task_id']
    if spec['kind'] in ('page_navigation','menu_navigation'):
        binding.update(start_path=spec['start_path'],evaluator_version=spec['protocol'])
        if spec.get('start_kind')=='credit_memo_detail':
            memo=one(state['credit_memos'],'start_credit_memo_missing_or_not_unique')
            binding['start_path']=f"/sales/creditmemo/view/creditmemo_id/{int(memo['entity_id'])}/"
        return binding
    if spec.get('scope')=='default':
        store=one([s for s in state['stores'] if s['code']=='default' and int(s['store_id'])>0], 'default_store_not_unique')
        binding['scope_id']=int(store['store_id'])
    if spec.get('product'):
        product=one(state['products'].get(spec['product'],[]), 'target_product_missing_or_not_unique')
        binding['product_id']=int(product['entity_id'])
        binding['product_sku']=product['sku']
        binding['product_name']=product['name']
        if spec.get('panel')=='crosssell':
            binding['cross_sell_skus']=sorted(l['sku'] for l in product.get('links',[]) if int(l['link_type_id'])==5)
        binding['start_path']=f"/catalog/product/edit/id/{binding['product_id']}/store/{binding['scope_id']}/"
        if spec['kind'] in ('query','update'):
            value=get_attr(product,spec['field'],binding['scope_id'],effective=True)
            # Magento omits an empty optional text attribute from EAV storage.
            if value is None and spec['field']=='short_description':value=''
            if value is None:raise BindingError('target_attribute_missing')
            binding['initial_value']=value
            if spec['kind']=='query':binding['reference']=value
            elif same_value(value,spec['expected'],spec['field']):raise BindingError('goal_already_satisfied_at_reset')
    if spec.get('order') or spec.get('credit_memo'):
        order=one(state['orders'],'target_order_missing_or_not_unique')
        binding['order_id']=int(order['entity_id'])
        binding['order_increment_id']=order['increment_id']
        binding['start_path']=f"/sales/order/view/order_id/{binding['order_id']}/"
        if spec.get('order'):
            binding['reference']=order['status']
            binding['reference_aliases']=[x['label'] for x in state['order_status_labels'] if x['status']==order['status']]
        if spec.get('credit_memo'):
            memo=one(state['credit_memos'],'credit_memo_for_order_missing_or_not_unique')
            binding['memo_id']=int(memo['entity_id'])
            binding['memo_increment_id']=memo['increment_id']
            if spec['kind']!='navigation':binding['start_path']=f"/sales/creditmemo/view/creditmemo_id/{binding['memo_id']}/"
            if spec['kind']=='comment' and any(plain(c['comment'])==spec['expected'] for c in state['comments']):
                raise BindingError('requested_comment_already_exists')
    return binding



def verify_fixture_relationships(state, scenario):
    """Check source-observed links before model execution, not just UI availability."""
    for reference in scenario['products']:
        if 'cross_sell_skus' not in reference:continue
        product=one([p for p in state['products'].get(reference['name'],[]) if p['sku']==reference['sku']],
                    'fixture_product_identity_mismatch')
        actual=sorted(l['sku'] for l in product.get('links',[]) if int(l['link_type_id'])==5)
        if actual!=sorted(reference['cross_sell_skus']):raise BindingError('source_cross_sell_relationships_mismatch')


def read_state(site, project, root, *, source_task_id=None):
    state=Path(site.temp.name)/'webarena-admin'
    command=['apptainer','exec','--cleanenv','--containall','--no-home','--no-mount','bind-paths,hostfs,cwd',
             '--pwd','/','--bind',f'{state}:/state','--bind',f'{state}/app:/var/www/magento2',
             '--bind',f'{project}/cluster/admin-pilot-state.php:/pilot-state.php:ro',
             str(root/'containers/webarena/shopping-admin.sif'),'php','/pilot-state.php']
    result=subprocess.run(command,capture_output=True,text=True,timeout=60)
    if result.returncode:raise RuntimeError('isolated_read_only_state_probe_failed')
    value=json.loads(result.stdout)
    from .admin_mail import read_mail
    value.setdefault('records',{})['mail']=read_mail(state/'app/var/training-mail')
    fixture=state/'fixture-applied.json'
    ids={str(x['local_product_id']) for x in json.loads(fixture.read_text()).get('mapping',[])} if fixture.exists() else set()
    from lab_generate_skill.admin_media import hash_media
    hash_media(value.get('records',{}).get('media',[]),state/'app/pub/media/catalog/product',ids)
    if source_task_id is not None:
        from .admin_native_mutation import extend_capture
        value=extend_capture(value,site,project,root,source_task_id)
        from .admin_reviewed_operations import extend_capture as extend_reviewed_capture
        value=extend_reviewed_capture(value,site,project,root,source_task_id)
    return value


def page_probe(page):
    # Read current page only. No evaluator navigation, clicks, or browser mutation.
    result = page.evaluate('''() => {
      const visible = el => !!el && el.getClientRects().length > 0 && getComputedStyle(el).visibility !== 'hidden';
      const text = document.body ? document.body.innerText : '';
      const panels = {};
      for (const key of ['review','content','related','crosssell','upsell','search-engine-optimization','custom_options','gallery','design','schedule-design-update','gift-options','schedule_design_update']) {
        const containers = [...document.querySelectorAll('[data-index="'+key+'"]')];
        const opened = containers.some(el => {
          const pane = el.querySelector('.admin__fieldset-wrapper-content,.fieldset-wrapper-content,[data-role="content"]');
          return visible(el) && visible(pane || (key==='crosssell' ? el : null));
        });
        panels[key] = {present: containers.length>0, opened, text: containers.filter(visible).map(el=>el.innerText).join('\\n')};
      }
      const menus = {};
      for (const el of document.querySelectorAll('#nav > li.level-0')) {
        const sub=el.querySelector(':scope > .submenu');
        if (!sub) continue;
        menus[el.id]={label:el.querySelector(':scope > a')?.innerText.trim() || '',
          show_class:el.classList.contains('_show'),aria_expanded:sub.getAttribute('aria-expanded')==='true',
          visible:visible(sub) && getComputedStyle(sub).display!=='none'};
      }
      const size=[...document.querySelectorAll('input[aria-labelledby="per-page-text"],select[id$="_page-limit"]')].find(visible);
      let committedSize=null;
      if(size) {
        if(size.tagName==='SELECT') committedSize=Number(size.value);
        else try { const data=require('ko').contextFor(size).$data; committedSize=Number(typeof data.value==='function'?data.value():data.value); } catch(e) {}
      }
      const grid={view_menu_open:[...document.querySelectorAll('.admin__data-grid-action-bookmarks .admin__action-dropdown-menu')].some(visible),page_size:size?Number(size.value):null,committed_page_size:committedSize,
        columns:[...document.querySelectorAll('table.data-grid thead th,table.data thead th')].filter(visible).map(e=>e.innerText.trim()).filter(Boolean),
        row_count:[...document.querySelectorAll('table.data-grid tbody tr,table.data tbody tr')].filter(visible).length};
      const form_fields=[...document.querySelectorAll('input[name],select[name],textarea[name]')].map(e=>({name:e.name,value:e.value,visible:visible(e),required:e.closest('.admin__field')?.classList.contains('_required') || e.required || e.getAttribute('aria-required')==='true' || (()=>{try{return JSON.parse(e.getAttribute('data-validate')||'{}')['required-entry']===true;}catch{return false;}})() || /[*]/.test(e.closest('.admin__field')?.querySelector('.admin__field-label')?.innerText||'')}));
      const tabs=[...document.querySelectorAll('[role=tab]')].map(e=>({text:e.innerText.trim(),selected:e.getAttribute('aria-selected')==='true',controls:e.getAttribute('aria-controls')}));
      const partner_cards={};
      for (const heading of document.querySelectorAll('h2,h3,h4')) {
        const name=heading.innerText.trim();
        if (['dotmailer','Yotpo','Vertex'].includes(name)) {
          const card=heading.closest('li')||heading.parentElement;
          const description=[...card.querySelectorAll('p')].map(e=>{const c=e.cloneNode(true);c.querySelectorAll('a').forEach(a=>a.remove());return c.textContent.trim().replace(/\s+/g,' ');}).filter(Boolean).join(' ');
          if(description)partner_cards[name]=description;
        }
      }
      return {url:location.href,title:document.title,text,panels,menus,tabs,grid,form_fields,partner_cards,
        heading:document.querySelector('h1')?.innerText || '',
        login:!!document.querySelector('form#login-form input[type="password"],body.adminhtml-auth-login input[type="password"]'),
        page_error:location.protocol==='chrome-error:' || /^(404|Page not found|Whoops, our bad)/im.test(document.querySelector('main')?.innerText||text)};
    }''')

    from .admin_ui_contract import probe as probe_ui_contract
    result['ui_contract']=probe_ui_contract(page)
    result['downloads']=getattr(page,'_admin_downloads',[])
    from .admin_reviewed_operations import extend_page_probe
    result=extend_page_probe(page,result)
    from .admin_category_operations import extend_page_probe as category_page_probe
    return category_page_probe(page,result)


def final_answer(trace):
    for message in reversed(trace['messages']):
        action=message.get('action_payload')
        if not isinstance(action,str):continue
        try:
            call=ast.parse(action,mode='eval').body
            if call.func.id=='send_msg_to_user':
                if call.args:return str(ast.literal_eval(call.args[0]))
                return str(next(ast.literal_eval(k.value) for k in call.keywords if k.arg=='text'))
        except (SyntaxError,ValueError,AttributeError,StopIteration):continue
    return ''


def exact_query(answer, binding):
    # Explicit structured response avoids must_include accepting "not <answer>".
    try:value=json.loads(answer)
    except (ValueError,TypeError):return False, 'answer_not_requested_json'
    if not isinstance(value,dict) or set(value)!={'value'}:return False,'answer_schema_mismatch'
    got=value['value']
    if isinstance(got,(list,dict,bool)) or got is None:return False,'invalid_answer_value'
    field=binding['spec']['field']
    refs=[binding['reference']]+binding.get('reference_aliases',[])
    ok=any(same_value(got,x,field) if field=='price' else plain(got).casefold()==plain(x).casefold() for x in refs)
    return ok,'exact_field_value'


def evaluate(binding, before, after, page, answer, runtime_error=None):
    if binding['spec']['kind']=='native_category_operation':
        from .admin_category_operations import evaluate as evaluate_category
        return evaluate_category(binding,before,after,page,answer,runtime_error)
    if binding['spec']['kind']=='reviewed_admin_operation':
        from .admin_reviewed_operations import evaluate as evaluate_reviewed
        return evaluate_reviewed(binding,before,after,page,answer,runtime_error)
    if binding['spec']['kind']=='native_mutation':
        from .admin_native_mutation import evaluate as evaluate_native
        return evaluate_native(binding,before,after,page,answer,runtime_error)
    result={'version':VERSION,'status':'unknown','reward':None,'checks':{},'answer':answer,
            'official_webarena_score':False,'paid_judge_calls':0}
    if runtime_error:
        result['reason']='runtime_error';return result
    try:
        if after is None or page is None:raise ValueError('missing final evidence')
        spec=binding['spec'];checks=result['checks']
        checks['same_local_deployment']=urlsplit(page['url']).netloc==binding['site_netloc']
        result['final_page_warning']=bool(page['login'] or page['page_error'])
        if spec['kind']=='material_product_creation':
            from .admin_material_creation import creation_evaluation
            checks.update(creation_evaluation(binding,before,after,page))
            passed=all(checks.values());result.update(status='success' if passed else 'failure',reward=int(passed))
            return result
        if spec['kind']=='admin_contract':
            from .admin_contract_rules import checks as contract_checks,VERSION as contract_version
            result['version']=contract_version
            checks.update(contract_checks(binding,before,after,page,answer))
            passed=bool(checks) and all(checks.values())
            result.update(status='success' if passed else 'failure',reward=int(passed))
            return result
        if spec['kind']=='typed_query':
            from .admin_query_rules import query_checks
            result['version']=spec['protocol']
            checks['valid_authenticated_page']=not result['final_page_warning']
            checks.update(query_checks(binding,before,after,answer))
            passed=all(checks.values());result.update(status='success' if passed else 'failure',reward=int(passed))
            return result
        if spec['kind']=='menu_navigation':
            from .admin_navigation_rules import menu_checks
            result['version']=spec['protocol']
            checks.update(menu_checks(spec,page,binding['site_netloc']))
            passed=all(checks.values());result.update(status='success' if passed else 'failure',reward=int(passed))
            return result
        if spec['kind']=='page_navigation':
            result['version']=spec['protocol']
            checks.update(page_navigation_checks(spec,page,binding['site_netloc']))
            passed=all(checks.values());result.update(status='success' if passed else 'failure',reward=int(passed))
            return result
        if spec['kind'] in ('navigation', 'query'):checks['valid_authenticated_page']=not result['final_page_warning']
        path=urlsplit(page['url']).path
        if spec['kind']=='navigation':
            if not all(checks.values()):
                result.update(status='failure',reward=0);return result
            if binding.get('product_id'):
                checks['correct_object']=bool(re.search(r'/catalog/product/edit/id/'+str(binding['product_id'])+r'(?:/|$)',path))
                checks['product_identity']=binding['product_name'] in page['heading']
                if not checks['correct_object'] or not checks['product_identity']:
                    result.update(status='failure',reward=0);return result
                panel=spec['panel'];entry=page['panels'][panel]
                if not entry['present']:
                    if panel=='crosssell' and page['panels']['related']['present'] and not page['panels']['related']['opened']:
                        checks['requested_panel_open']=False
                        result.update(status='failure',reward=0);return result
                    result['reason']='panel_selector_unresolved';return result
                checks['requested_panel_open']=entry['opened']
                if panel=='crosssell':
                    checks['related_panel_open']=page['panels']['related']['opened']
                    if binding.get('cross_sell_skus'):
                        checks['cross_sell_products_visible']=all(sku in entry.get('text','') for sku in binding['cross_sell_skus'])
            else:
                checks['correct_object']=bool(re.search(r'/sales/creditmemo/view/creditmemo_id/'+str(binding['memo_id'])+r'(?:/|$)',path))
                checks['order_identity']=bool(re.search(r'Order\s*#\s*'+re.escape(binding['order_increment_id'])+r'\b',page['text']))
                checks['history_visible']='Credit Memo History' in page['text']
        elif spec['kind']=='query':
            checks['exact_reference_answer'],result['answer_check']=exact_query(answer,binding)
        elif spec['kind']=='update':
            product=one([p for p in after['products'].get(spec['product'],[]) if int(p['entity_id'])==binding['product_id']], 'final_product_unresolved')
            observed=get_attr(product,spec['field'],binding['scope_id'])
            result['persisted_value']=observed
            checks['persisted_requested_value']=same_value(observed,spec['expected'],spec['field'])
            if binding['scope_id']!=0:
                old=one(before['products'][spec['product']],'initial_product_unresolved')
                checks['global_scope_unchanged']=get_attr(old,spec['field'],0)==get_attr(product,spec['field'],0)
            if spec.get('protect_unrelated_state') is True:
                from .admin_product_update_guard import protected_update_checks
                checks.update(protected_update_checks(binding,before,after))
        elif spec['kind']=='comment':
            old_ids={int(c['entity_id']) for c in before['comments']}
            new=[c for c in after['comments'] if int(c['entity_id']) not in old_ids and int(c['parent_id'])==binding['memo_id']]
            matches=[c for c in new if plain(c['comment'])==spec['expected']]
            checks['new_exact_comment_on_correct_memo']=len(matches)==1
            checks['no_customer_notification']=bool(matches) and all(int(c['is_customer_notified'])==0 for c in matches)
            checks['not_visible_on_storefront']=bool(matches) and all(int(c['is_visible_on_front'])==0 for c in matches)
            checks['no_additional_refund']=before['orders']==after['orders'] and before['credit_memos']==after['credit_memos']
        else:raise ValueError('unsupported task')
        passed=bool(checks) and all(checks.values())
        result.update(status='success' if passed else 'failure',reward=int(passed))
    except (KeyError,ValueError,TypeError):result['reason']='evaluator_evidence_error'
    return result


def _md_text(value):
    text=html.escape(str(value),quote=False).replace('\n',' ')
    return re.sub(r'([\\`*_{}\[\]()#+.!|])',r'\\\1',text)


def _md_code(value, language='json'):
    text=value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,indent=2)
    fence='`'*max(3,max((len(x) for x in re.findall(r'`+',text)),default=0)+1)
    return f'{fence}{language}\n{text}\n{fence}'


def render_report(out):
    out=Path(out);entries=[]
    labels={'environment_blocked':'环境阻塞','unknown':'未判定／运行异常',
            'success':'成功','failure':'失败','environment_or_runtime_error':'运行异常'}
    for directory in sorted(out.glob('task-*')):
        p=directory/'result.json'
        if not p.exists():continue
        result=json.loads(p.read_text())
        status=result.get('evaluation',{}).get('status',result.get('status','unknown'))
        entries.append((directory,result,status))
    parts=['# 单次任务验证报告',
           '本地 actor；程序规则判定；截图仅供人工复核。此报告不代表正式训练准入。',
           f'已生成 {len(entries)} 份结果。点击任务名称查看逐题 Markdown 报告。',
           '| 任务 | 结果 | 模型步数 | 原因 |',
           '| --- | --- | ---: | --- |']
    for directory,result,status in entries:
        reason=result.get('reason') or result.get('evaluation',{}).get('reason','')
        goal=_md_text(result.get('goal',directory.name))
        steps=result.get('rounds',0 if result.get('actor_attempts')==0 else '—')
        parts.append(f'| [{goal}]({directory.name}/review.md) | {_md_text(labels.get(status,status))} | {steps} | {_md_text(reason)} |')
    parts+=['','在 VS Code 中打开本文件可直接阅读；按 **Ctrl+Shift+V** 打开 Markdown 预览，逐题报告中的截图可直接显示。',
            '原始 JSON、PNG 截图和日志保留在对应任务目录。若模型步数为 0，则没有模型交互轨迹，终止截图只代表初始化页面。']
    (out/'index.md').write_text('\n\n'.join(parts[:3])+'\n\n'+'\n'.join(parts[3:])+'\n')


def render_task(directory, result):
    directory=Path(directory)
    parts=['# 任务验证详情',_md_text(result['goal']),
           '[返回汇总](../index.md)', '## 判定结果',_md_code(result)]
    for p in sorted(directory.glob('step-*.json')):
        record=json.loads(p.read_text());obs=record.get('observation',{})
        parts+=['## '+p.stem, _md_code({k:v for k,v in record.items() if k!='observation'})]
        screenshot=p.with_suffix('.png')
        if screenshot.exists():parts+=['![当前页面截图]('+screenshot.name+')']
        parts+=['### 页面观察',_md_code(obs)]
    terminal=directory/'terminal-page.json'
    if terminal.exists():
        parts+=['## 终止页面（含初始化失败时保存的页面）',_md_code(json.loads(terminal.read_text()))]
    if (directory/'terminal-page.png').exists():
        parts+=['![实际终止页面截图](terminal-page.png)']
    trace=directory/'trajectory.json'
    if trace.exists():
        trajectory=json.loads(trace.read_text())
        parts+=['## 模型轨迹','[完整 trajectory.json](trajectory.json)']
        assistant_messages=[m for m in trajectory.get('messages',[]) if m.get('role')=='assistant']
        if not assistant_messages:parts+=['本次没有模型输出；未进入模型交互阶段。']
        for index,message in enumerate(assistant_messages,1):
            parts+=['### 模型输出 '+str(index),_md_code(message.get('content',''),'text')]
    else:
        parts+=['本次没有生成 trajectory.json。请结合上方状态和已有逐步记录查看原因。']
    links=[f'[{name}]({name})' for name in ('result.json','state-before.json','state-after.json','task-contract.json') if (directory/name).exists()]
    if links:parts+=['## 原始记录',' · '.join(links)]
    (directory/'review.md').write_text('\n\n'.join(parts)+'\n')


def bind(row, state):
    """Bind private checks separately from declared public completion criteria."""
    from .admin_public_contract import declare_completion
    return declare_completion(_bind(row, state))
