"""Independent saved-state references and UI observability checks for query families."""
import re
from .site_database import select_rows
from .site_query_rules import same_value


def one(rows):
    if len(rows)!=1:raise ValueError('Missing or ambiguous reference object')
    return rows[0]


def query_reference(site,contract):
    if contract.get('query',{}).get('family')=='gitlab_merge_request_completion_time':
        if contract.get('domain') != 'gitlab':
            raise ValueError('Merge-request completion reference requires GitLab')
        from .gitlab_completion_time_query import reference
        return reference(site,contract['query'])
    if contract.get('query',{}).get('family')=='shopping_complete_native_training':
        from .shopping_complete_training_query_runtime import normal_reference
        return normal_reference(site,contract)
    if contract.get('query',{}).get('family')=='gitlab_grouped_goal_query':
        from .gitlab_grouped_goal_runtime import reference
        return reference(site,contract)
    from .shopping_remaining_runtime import QUERY_FAMILIES
    if contract.get("domain")=="shopping" and contract["query"].get("family") in QUERY_FAMILIES:
        from .shopping_remaining_runtime import reference
        return reference(site,contract)
    if contract['query'].get('family')=='map_typed_native':
        from .map_typed_runtime import reference
        return reference(site,contract)
    if contract['query'].get('family')=='gitlab_release':
        from .gitlab_release_query import reference
        return reference(site,contract['query'])
    if contract['query'].get('family')=='gitlab_exact_issue_collection':
        from .gitlab_exact_collection_query import reference
        return reference(site,contract['query'])
    if contract['query'].get('family')=='shopping_policy':
        from .shopping_policy_query import reference
        return reference(site,contract['query'])
    if contract['query'].get('family')=='gitlab_tree_list':
        from .gitlab_tree_query import reference
        return reference(site,contract['query'])
    if contract['query'].get('family')=='map_documentation':
        from .map_document_query import reference
        return reference(site,contract['query'])
    if contract['query'].get('family')=='reddit_theme':
        from .reddit_theme_query import reference
        return reference(site,contract['query'])
    if contract['query'].get('family')=='gitlab_issuable_count':
        from .gitlab_issuable_query import reference
        return reference(site,contract['query'])
    if contract['query'].get('family')=='reddit_wiki_presence':
        from .reddit_wiki_presence import reference
        return reference(site,contract['query'])
    if contract['query'].get('family')=='shopping_review_counts':
        from .shopping_review_counts import reference
        return reference(site,contract['query'])
    if contract['query'].get('family')=='gitlab_directory_license':
        from .gitlab_license_query import reference
        return reference(site,contract['query'])
    if contract['query'].get('family')=='map_route_steps':
        from .map_steps_query import reference
        return reference(site,contract['query'])
    if contract['query'].get('family')=='map_share':
        from .map_share_query import reference
        return reference(site,contract['query'])
    if contract["query"].get("family")=="gitlab_document_list":
        from .gitlab_document_query import reference
        return reference(site,contract["query"])
    if contract['query'].get('family')=='gitlab_tree_directories':
        from .gitlab_tree_query import reference
        return reference(site,contract['query'])
    if contract['query'].get('family')=='map_metadata':
        from .map_metadata_query import reference
        return reference(site,contract['query'])
    if contract['query'].get('family')=='shopping_collection':
        from .shopping_collection_query import reference
        return reference(site,contract['query'])
    if contract['query'].get('family')=='shopping_catalog_facts':
        from .shopping_catalog_facts import reference
        return reference(site,contract['query'])
    if contract['query'].get('family')=='gitlab_collection':
        from .gitlab_collection_query import reference
        return reference(site,contract['query'])
    if contract['query'].get('family')=='shopping_checkout_values':
        from .shopping_checkout_query import reference
        return reference(site,contract['query'])
    if contract['query'].get('family')=='gitlab_project_updated':
        from .gitlab_project_date_query import reference
        return reference(site,contract['query'])
    if contract['query'].get('family')=='reddit_form_documentation':
        from .reddit_form_query import reference
        return reference(site,contract['query'])
    if contract['query'].get('family')=='map_route_summary':
        from .map_summary_query import reference
        return reference(site,contract['query'])
    q=contract['query'];ident=q['object_id']
    if type(ident) is not int or ident<=0:raise ValueError('Invalid reference identity')
    fields=q['fields'];family=q['family'];values={}
    if family=='gitlab_repo_metadata':
        from .gitlab_metadata_query import reference
        return reference(site,q)
    if family in ('reddit_post','reddit_account','reddit_forum_directory','reddit_post_page','reddit_forum_names'):
        from .reddit_query_reference import reference
        return reference(site,q)
    if family in ('shopping_cart','shopping_newsletter','shopping_order','shopping_address'):
        from .shopping_query_reference import reference
        return reference(site,q)
    if family in ('gitlab_account','gitlab_todo','gitlab_starred_projects'):
        from .gitlab_query_reference import reference
        return reference(site,q)
    if family=='shopping_product':
        obj=one(select_rows(site,f"SELECT entity_id,sku FROM catalog_product_entity WHERE entity_id={ident}"))
        for field in fields:
            if field=='sku':value=obj['sku']
            elif field=='manufacturer':
                from .product_description_fields import description_fact
                value=description_fact(site,ident,'Manufacturer')
            elif field=='price':
                value=one(select_rows(site,f"SELECT v.value FROM catalog_product_entity_decimal v JOIN eav_attribute a ON a.attribute_id=v.attribute_id WHERE v.entity_id={ident} AND v.store_id=0 AND a.attribute_code='price' AND a.entity_type_id=4"))['value']
            elif field=='stock_status':
                flag=one(select_rows(site,f"SELECT is_in_stock FROM cataloginventory_stock_item WHERE product_id={ident} AND stock_id=1"))['is_in_stock']
                if str(flag) not in ('0','1'):raise ValueError('Invalid stock flag')
                value='In Stock' if str(flag)=='1' else 'Out of Stock'
            elif field in ('rating_percent','review_count'):
                key={'rating_percent':'rating_summary','review_count':'reviews_count'}[field]
                value=one(select_rows(site,f"SELECT {key} AS value FROM review_entity_summary WHERE entity_pk_value={ident} AND store_id=1 AND entity_type=1"))['value']
            else:raise ValueError('Unsupported product field')
            values[field]=value
    elif family=='reddit_forum':
        obj=one(select_rows(site,f'SELECT id,name FROM forums WHERE id={ident}'))
        for field in fields:
            if field=='submission_count':values[field]=one(select_rows(site,f'SELECT count(*) AS count FROM submissions WHERE forum_id={ident}'))['count']
            elif field=='has_subscribers':values[field]='yes' if one(select_rows(site,f'SELECT count(*) AS count FROM forum_subscriptions WHERE forum_id={ident}'))['count'] else 'no'
            else:raise ValueError('Unsupported forum query')
    elif family=='gitlab_project':
        obj=one(select_rows(site,f'SELECT id,name,star_count,description FROM projects WHERE id={ident}'))
        for field in fields:
            if field=='star_count':values[field]=obj['star_count']
            elif field=='description':
                value=obj['description']
                if not isinstance(value,str) or not value.strip():raise ValueError('Missing project description')
                values[field]=value
            elif field=='open_issue_count':values[field]=one(select_rows(site,f'SELECT count(*) AS count FROM issues WHERE project_id={ident} AND state_id=1'))['count']
            elif field=='open_merge_request_count':values[field]=one(select_rows(site,f'SELECT count(*) AS count FROM merge_requests WHERE target_project_id={ident} AND state_id=1'))['count']
            elif field=='fork_count':values[field]=one(select_rows(site,f'SELECT count(*) AS count FROM fork_network_members WHERE forked_from_project_id={ident}'))['count']
            elif field=='commit_count':values[field]=one(select_rows(site,f'SELECT commit_count FROM project_statistics WHERE project_id={ident}'))['commit_count']
            elif field=='all_issue_count':values[field]=one(select_rows(site,f'SELECT count(*) AS count FROM issues WHERE project_id={ident}'))['count']
            elif field=='all_merge_request_count':values[field]=one(select_rows(site,f'SELECT count(*) AS count FROM merge_requests WHERE target_project_id={ident}'))['count']
            else:raise ValueError('Unsupported project field')
    else:raise ValueError('Unsupported query family')
    # Normalize DB-driver number types without changing reference meaning.
    values={k:(str(v) if fields[k]=='decimal' else int(v) if fields[k]=='integer' else v) for k,v in values.items()}
    return {'object_id':family+':'+str(ident),'values':values}


def first_match(pattern,text):
    found=re.findall(pattern,text,re.I)
    if len(found)!=1:raise ValueError('Requested UI field absent or ambiguous')
    return found[0].replace(',','').strip()


def map_query_ui_values(page,query,*,evidence=None):
    if query.get('family')=='map_documentation':
        from .map_document_query import ui_values
    elif query.get('family')=='map_route_steps':
        from .map_steps_query import ui_values
    elif query.get('family')=='map_share':
        from .map_share_query import ui_values
    elif query.get('family')=='map_route_summary':
        from .map_summary_query import ui_values
    elif query.get('family')=='map_metadata':
        from .map_metadata_query import ui_values
    else:
        raise ValueError('Unsupported Map query family')
    return ui_values(page,query,evidence=evidence)


def query_ui_values(page,contract,*,evidence=None):
    if contract['query'].get('family')=='gitlab_merge_request_completion_time':
        if contract.get('domain')!='gitlab':raise ValueError('Completion-time query requires GitLab')
        from .gitlab_completion_time_ui import ui_values
        return ui_values(page,contract['query'],evidence=evidence)
    from .shopping_remaining_runtime import QUERY_FAMILIES
    if contract.get("domain")=="shopping" and contract["query"].get("family") in QUERY_FAMILIES:
        from .shopping_remaining_runtime import ui_values
        return ui_values(page,contract)
    if contract['query'].get('family')=='gitlab_release':
        from .gitlab_release_query import ui_values
        return ui_values(page,contract['query'])
    if contract['query'].get('family')=='gitlab_exact_issue_collection':
        from .gitlab_exact_collection_query import ui_values
        return ui_values(page,contract['query'])
    if contract['query'].get('family')=='shopping_policy':
        from .shopping_policy_query import ui_values
        return ui_values(page,contract['query'])
    if contract['query'].get('family')=='gitlab_tree_list':
        from .gitlab_tree_query import ui_values
        return ui_values(page,contract['query'])
    if contract['query'].get('family')=='reddit_theme':
        from .reddit_theme_query import ui_values
        return ui_values(page,contract['query'])
    if contract['query'].get('family')=='gitlab_issuable_count':
        from .gitlab_issuable_query import ui_values
        return ui_values(page,contract['query'])
    if contract['query'].get('family')=='reddit_wiki_presence':
        from .reddit_wiki_presence import ui_values
        return ui_values(page,contract['query'])
    if contract['query'].get('family')=='shopping_review_counts':
        from .shopping_review_counts import ui_values
        return ui_values(page,contract['query'])
    if contract['query'].get('family')=='gitlab_directory_license':
        from .gitlab_license_query import ui_values
        return ui_values(page,contract['query'])
    if contract["query"].get("family")=="gitlab_document_list":
        from .gitlab_document_query import ui_values
        return ui_values(page,contract["query"])
    if contract['query'].get('family')=='gitlab_tree_directories':
        from .gitlab_tree_query import ui_values
        return ui_values(page,contract['query'])
    if contract['query'].get('family') in ('map_route_summary','map_metadata','map_share','map_route_steps','map_documentation'):
        return map_query_ui_values(page,contract['query'])
    if contract['query'].get('family')=='shopping_collection':
        from .shopping_collection_query import ui_values
        return ui_values(page,contract['query'])
    if contract['query'].get('family')=='shopping_catalog_facts':
        from .shopping_catalog_facts import ui_values
        return ui_values(page,contract['query'])
    if contract['query'].get('family')=='gitlab_collection':
        from .gitlab_collection_query import ui_values
        return ui_values(page,contract['query'])
    if contract['query'].get('family')=='shopping_checkout_values':
        from .shopping_checkout_query import ui_values
        return ui_values(page,contract['query'])
    """Read public rendered fields separately from the private database reference."""
    if contract['query'].get('family')=='gitlab_project_updated':
        from .gitlab_project_date_query import ui_values
        return ui_values(page,contract['query'])
    if contract['query'].get('family')=='reddit_form_documentation':
        from .reddit_form_query import ui_values
        return ui_values(page,contract['query'])
    q=contract['query'];f=q['family'];body=page.locator('body').inner_text(timeout=10000);values={}
    if f=='gitlab_repo_metadata':
        from .gitlab_metadata_query import ui_values
        return ui_values(page,q)
    if f in ('reddit_post','reddit_account','reddit_forum_directory','reddit_post_page','reddit_forum_names'):
        from .reddit_query_reference import ui_values
        return ui_values(page,q)
    if f in ('shopping_cart','shopping_newsletter','shopping_order','shopping_address'):
        from .shopping_query_reference import ui_values
        return ui_values(page,q)
    if f in ('gitlab_account','gitlab_todo','gitlab_starred_projects'):
        from .gitlab_query_reference import ui_values
        return ui_values(page,q)
    if f=='shopping_product':
        title=page.locator('h1 .base').inner_text(timeout=10000).strip()
        if title!=q['object_name']:raise ValueError('UI product identity mismatch')
        for key in q['fields']:
            if key=='sku':value=page.locator('.product-info-main .product.attribute.sku .value').inner_text().strip()
            elif key=='manufacturer':
                from .product_description_fields import clean_table_text
                rows=page.locator('.product.attribute.description tr').evaluate_all("rows=>rows.map(r=>Array.from(r.children).filter(c=>['TD','TH'].includes(c.tagName)).map(c=>c.innerText))")
                found=[clean_table_text(r[1]) for r in rows if len(r)==2 and clean_table_text(r[0]).rstrip(':').casefold()=='manufacturer' and clean_table_text(r[1])]
                if len(found)!=1:raise ValueError('Rendered manufacturer missing or ambiguous')
                value=found[0]
            elif key=='price':value=page.locator('.product-info-main [data-price-type="finalPrice"]').get_attribute('data-price-amount')
            elif key=='stock_status':
                raw=page.locator('.product-info-main .stock').inner_text().strip().lower()
                value={'in stock':'In Stock','out of stock':'Out of Stock'}.get(raw)
                if value is None:raise ValueError('Unknown rendered stock label')
            elif key=='rating_percent':value=first_match(r'(\d+(?:\.\d+)?)%',page.locator('.product-info-main .rating-result').get_attribute('title') or '')
            elif key=='review_count':value=first_match(r'(\d[\d,]*)\s+Reviews?',page.locator('.product-info-main .reviews-actions').inner_text())
            else:raise ValueError('Unsupported UI product field')
            values[key]=value
    elif f=='reddit_forum':
        name=re.escape(q['object_name'])
        if 'submission_count' in q['fields']:values['submission_count']=first_match(r'/f/'+name+r'\s+.*?([\d,]+) submissions',body.replace('\n',' '))
        if 'has_subscribers' in q['fields']:
            from urllib.parse import urlsplit
            heading=page.locator('h1.forum-title')
            section=page.locator('.sidebar__section').filter(has=heading)
            if heading.count()!=1 or section.count()!=1:raise ValueError('Wrong or ambiguous forum sidebar')
            link=heading.locator('a[href]')
            if link.count()!=1 or urlsplit(link.get_attribute('href') or '').path!='/f/'+q['object_name']:raise ValueError('Wrong forum identity link')
            count=section.locator('.subscribe-button__subscriber-count').inner_text().strip().replace(',','')
            values['has_subscribers']='yes' if int(count)>0 else 'no'
    elif f=='gitlab_project':
        # Project ID is independently rendered on the repository overview.
        if set(q['fields']) & {'all_issue_count','all_merge_request_count'}:
            from urllib.parse import urlsplit
            if urlsplit(page.url).path!=urlsplit(q['reference_path']).path:raise ValueError('Wrong project list URL')
            # Project identity comes from server-rendered project metadata, not a guessed name.
            current=page.locator('[data-project-id]').evaluate_all('es=>[...new Set(es.map(e=>e.getAttribute("data-project-id")))]')
            if str(q['object_id']) not in current or any(x!=str(q['object_id']) for x in current):raise ValueError('UI project list identity mismatch')
        elif not re.search(r'Project ID:\s*'+str(q['object_id'])+r'\b',body):raise ValueError('UI project identity mismatch')
        for key in q['fields']:
            if key=='description':
                node=page.locator('.home-panel-description-markdown[itemprop="description"]')
                if node.count()!=1:raise ValueError('Rendered project description missing or ambiguous')
                values[key]=node.inner_text().strip();continue
            if key in ('all_issue_count','all_merge_request_count'):
                from .gitlab_query_reference import tab_count
                values[key]=tab_count(page,'All');continue
            pattern={'star_count':r'(?:Unstar|Star)\s*\n([\d,]+)\s*\nFork',
                     'fork_count':r'Fork\s*\n([\d,]+)\s*\n',
                     'commit_count':r'([\d,]+)\s*\n\s*Commits?\b',
                     'open_issue_count':r'Issues\s*\n([\d,]+)\s*\nMerge requests',
                     'open_merge_request_count':r'Merge requests\s*\n([\d,]+)\s*\nCI/CD'}[key]
            values[key]=first_match(pattern,body)
    return values


def ui_matches(contract,values,reference,*,site_origin=None):
    # Independent UI/reference validation still covers the complete collection,
    # even when the task permits an actor to choose a correct subset.
    return set(values)==set(reference['values']) and all(same_value('record_set' if kind=='record_subset' else kind,values.get(key),reference['values'][key],record_fields=contract['query'].get('record_fields',{}).get(key),site_origin=site_origin) for key,kind in contract['query']['fields'].items())
