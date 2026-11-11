"""Shared final-state navigation checks; task bindings contain no actor actions.

This is a draft adapter for additional sites. Passing a synthetic rule test does
not admit a task: live positive/negative controls and reset proof are required.
"""
import re
from urllib.parse import urlsplit, unquote, parse_qs

VERSION = 'site-navigation-v3'


def _native_completion_adapter(contract):
    if contract.get('completion',{}).get('family')=='gitlab_native_content':
        from . import gitlab_native_content
        return gitlab_native_content
    from .map_navigation_runtime import family
    selected=family(contract)
    if selected=='map_editor':
        from . import map_editor_navigation
        return map_editor_navigation
    if selected=='map_native_navigation':
        from . import map_native_navigation
        return map_native_navigation
    return None


def evaluate_navigation(contract, page, *, site_origin):
    from . import shopping_native_three_runtime as native_three
    if native_three.enabled(contract):return native_three.evaluate_terminal(contract,page,site_origin=site_origin)
    adapter=_native_completion_adapter(contract)
    if adapter is not None:return adapter.evaluate(contract,page,site_origin=site_origin)
    # A browser-generated error after our explicit local-service block has no
    # HTTP response. The recorded block proves an out-of-scope terminal page;
    # it is different from missing capture or an unclassified network failure.
    if isinstance(page,dict):
        block=page.get('navigation_policy_block')
        if isinstance(block,dict) and isinstance(block.get('blocked_origin'),str):
            try:
                blocked=urlsplit(block['blocked_origin'])
            except ValueError:
                blocked=urlsplit('')
            origin=urlsplit(site_origin)
            if (page.get('url')=='chrome-error://chromewebdata/'
                and page.get('error_page') is True
                and page.get('login_page') is False
                and block.get('document_url')==page['url']
                and block.get('source')=='local_network_policy'
                and block.get('reason')=='outside_declared_local_services'
                and blocked.scheme in ('http','https') and blocked.netloc
                and (blocked.scheme,blocked.netloc)!=(origin.scheme,origin.netloc)):
                return {'version':VERSION,'status':'failure','reward':0.0,
                        'checks':{'correct_site':False,'page_valid':False,
                                  'local_navigation_block_recorded':True},
                        'reason':'Actor terminated on the browser error document after a recorded navigation outside declared local services.'}
    required=('url','http_status','heading_texts','title','login_page','error_page')
    if not isinstance(page,dict) or any(k not in page or page[k] is None for k in required):
        return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':'Incomplete final-page capture'}
    if not isinstance(page['http_status'],int) or isinstance(page['http_status'],bool) or not isinstance(page['heading_texts'],list) or any(not isinstance(v,str) for v in page['heading_texts']) or not isinstance(page['title'],str) or any(type(page[k]) is not bool for k in ('login_page','error_page')):
        return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':'Malformed final-page capture'}
    if not isinstance(page['url'],str) or page['http_status'] < 200 or page['http_status'] >= 500:
        return {'version':VERSION,'status':'unknown','reward':None,'checks':{},'reason':'Transport or server failure; not an actor failure'}
    expected=contract['completion']; actual=urlsplit(page['url']); origin=urlsplit(site_origin)
    from .authentication_page import login_document_allowed
    requested_login = login_document_allowed(contract)
    source=expected.get('identity_source','heading')
    if source not in ('heading','title'):raise ValueError('Unsupported page identity source')
    if not expected.get('path_regex') or not expected.get(source+'_regex'):
        raise ValueError('Navigation contract requires independent path and explicit page identity checks')
    checks={
        'correct_site':(actual.scheme,actual.netloc)==(origin.scheme,origin.netloc),
        'page_valid':200<=page['http_status']<300 and (not page['login_page'] or requested_login) and not page['error_page'],
        'target_path':bool(re.fullmatch(expected['path_regex'],unquote(actual.path))),
    }
    if expected.get('query_params'):
        query=parse_qs(actual.query,keep_blank_values=True)
        checks['target_query_parameters']=all(query.get(k)==[str(v)] for k,v in expected['query_params'].items())
    if source=='heading':checks['target_heading']=any(re.search(expected['heading_regex'],h,re.I) is not None for h in page['heading_texts'])
    if expected.get('title_regex'):checks['target_title']=bool(re.search(expected['title_regex'],page['title'],re.I))
    if expected.get('reddit_any_profile'):
        if contract.get('domain')!='reddit' or expected['reddit_any_profile'] is not True:
            raise ValueError('Free-choice user profiles require an explicit Reddit contract')
        match=re.fullmatch(r'/user/([^/]+)(?:/submissions)?/?',unquote(actual.path))
        checks['profile_address_matches_heading']=bool(match and match[1] in [h.strip() for h in page['heading_texts']])
    if expected.get('map_route') and checks['page_valid'] and (page.get('map_route') or {}).get('loading'):
        return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':'Native route still loading at termination.'}
    if expected.get('map_list',{}).get('kind')=='history' and all(checks.values()) and ((page.get('map_list') or {}).get('history') or {}).get('loading'):
        return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':'Native history still loading at termination.'}
    details=expected.get('product_details',{})
    if details.get('cart_options') and checks['correct_site'] and checks['page_valid']:
        from .shopping_cart_details import cart_details_checks
        try:alternative=cart_details_checks(details,(page.get('product_details') or {}).get('cart_details'),site_origin=site_origin)
        except ValueError as exc:
            if not all(checks.values()):
                return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':str(exc)}
        else:
            if all(alternative.values()):
                return {'version':VERSION,'status':'success','reward':1.,
                        'checks':{k:checks[k] for k in ('correct_site','page_valid')}|alternative,
                        'reason':'Native cart-item details satisfy the explicit alternative completion condition.'}
            if not all(checks.values()):
                return {'version':VERSION,'status':'failure','reward':0.,
                        'checks':{k:checks[k] for k in ('correct_site','page_valid')}|{'requested_item_details_displayed':False},
                        'reason':'Neither the requested product detail page nor its expanded native cart-item options are displayed.'}
    if expected.get('repository',{}).get('document_equivalence') and checks['correct_site'] and checks['page_valid']:
        from .gitlab_document_equivalence import equivalent_article
        if equivalent_article(expected['repository'],page.get('repository'),page['url']):
            return {'version':VERSION,'status':'success','reward':1.,
                    'checks':{k:checks[k] for k in ('correct_site','page_valid')}|{'complete_article_equivalent':True},
                    'reason':'The same complete article title and body are rendered in a native repository document view.'}
    if not all(checks.values()):
        # These are necessary completion conditions already captured from the
        # real terminal page. A wrong page/object cannot become successful by
        # filling in optional family metadata. Do not confuse a clearly wrong
        # terminal route with missing evidence on the correct target page.
        return {'version':VERSION,'status':'failure','reward':0.,'checks':checks,
                'reason':'A mandatory final-page identity or validity condition failed.'}
    if expected.get('navigation_control'):
        from .navigation_click_evidence import checks as navigation_click_checks
        try:checks.update(navigation_click_checks(expected['navigation_control'],page.get('navigation_clicks'),site_origin=site_origin))
        except (ValueError,TypeError,KeyError) as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':'Native navigation event capture error: '+str(exc)}
    if expected.get('gitlab_section'):
        from .gitlab_section import section_checks
        try:checks.update(section_checks(expected['gitlab_section'],page.get('gitlab_section')))
        except (ValueError,KeyError,TypeError) as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':'Native section capture error: '+str(exc)}
    if expected.get('map_place'):
        from .map_place_page import place_checks
        try:checks.update(place_checks(expected['map_place'],page.get('map_place')))
        except (ValueError,KeyError,TypeError) as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':'Native place capture error: '+str(exc)}
    if expected.get('map_list'):
        from .map_list_page import list_checks
        try:checks.update(list_checks(expected['map_list'],page.get('map_list')))
        except (ValueError,TypeError,KeyError) as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':str(exc)}
    if expected.get('map_diary'):
        from .map_diary_page import diary_checks
        try:
            state=page.get('map_diary')
            if isinstance(state,dict)and state.get('url')!=page['url']:raise ValueError('Diary capture and terminal URL differ')
            checks.update(diary_checks(expected['map_diary'],state))
        except (ValueError,TypeError,KeyError)as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':str(exc)}
    if expected.get('map_gps'):
        from .map_gps_page import checks as gps_checks
        try:
            state=page.get('map_gps')
            if isinstance(state,dict)and state.get('url')!=page['url']:raise ValueError('GPS capture and terminal URL differ')
            checks.update(gps_checks(expected['map_gps'],state))
        except (ValueError,TypeError,KeyError)as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':str(exc)}
    if expected.get('labeled_issues'):
        from .gitlab_label_filter import checks as labeled_checks
        try:
            state=page.get('labeled_issues')
            if isinstance(state,dict)and state.get('url')!=page['url']:raise ValueError('Labeled list and terminal URL differ')
            checks.update(labeled_checks(expected['labeled_issues'],state))
        except (ValueError,TypeError,KeyError)as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':str(exc)}
    if expected.get('recent_ordered_items'):
        from .shopping_recent_items import checks as recent_checks
        try:
            state=page.get('recent_ordered_items')
            if contract.get('domain')!='shopping':raise ValueError('Recent items require the Shopping domain')
            if isinstance(state,dict) and state.get('url')!=page['url']:raise ValueError('Recent-item capture and terminal URL differ')
            recent=recent_checks(expected['recent_ordered_items'],state,site_origin=site_origin)
            if not recent['recent_items_native_initialized']:
                return {'version':VERSION,'status':'unknown','reward':None,'checks':checks|recent,'reason':'Native recent-item initialization has not completed.'}
            checks.update(recent)
        except (ValueError,TypeError,KeyError) as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':'Native recent-item capture error: '+str(exc)}
    if expected.get('todo_target'):
        from .gitlab_todo_target import checks as todo_target_checks
        try:
            state=page.get('todo_target')
            if isinstance(state,dict) and state.get('url')!=page['url']:
                raise ValueError('To-do target capture and terminal URL differ')
            checks.update(todo_target_checks(expected['todo_target'],state))
        except (ValueError,TypeError,KeyError) as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':str(exc)}
    if expected.get('project_search'):
        from .gitlab_project_search import checks as project_search_checks
        try:
            state=page.get('project_search')
            if isinstance(state,dict)and state.get('url')!=page['url']:raise ValueError('Search capture and terminal URL differ')
            checks.update(project_search_checks(expected['project_search'],state))
        except (ValueError,TypeError,KeyError)as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':str(exc)}
    if expected.get('cms_section'):
        from .shopping_cms_section import checks as cms_checks
        try:
            state=page.get('cms_section')
            if isinstance(state,dict) and state.get('url')!=page['url']:raise ValueError('CMS section capture and terminal URL differ')
            checks.update(cms_checks(expected['cms_section'],state,issued_request=state.get('issued_section_request')if isinstance(state,dict)else None))
        except (ValueError,TypeError,KeyError)as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':str(exc)}
    if expected.get('starrer_collection'):
        from .gitlab_starrer_coverage import checks as starrer_checks
        try:
            state=page.get('starrer_collection')
            if isinstance(state,dict)and state.get('url')!=page['url']:raise ValueError('Starrer capture and terminal URL differ')
            checks.update(starrer_checks(expected['starrer_collection'],state,site_origin=site_origin))
        except (ValueError,TypeError,KeyError)as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':str(exc)}
    if expected.get('web_ide'):
        from .gitlab_ide import ide_checks
        try:
            state=page.get('web_ide')
            if isinstance(state,dict)and state.get('url')!=page['url']:raise ValueError('IDE capture and terminal URL differ')
            checks.update(ide_checks(expected['web_ide'],state))
        except (ValueError,TypeError,KeyError)as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':str(exc)}
    if expected.get('help_document'):
        from .gitlab_help_document import help_checks
        try:
            state=page.get('help_document')
            if isinstance(state,dict)and state.get('url')!=page['url']:raise ValueError('Help capture and terminal URL differ')
            checks.update(help_checks(expected['help_document'],state))
        except (ValueError,TypeError,KeyError)as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':str(exc)}
    if expected.get('repository'):
        from .gitlab_repository import repository_checks
        try:checks.update(repository_checks(expected['repository'],page.get('repository'),page['url']))
        except ValueError as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':str(exc)}
    if expected.get('order_detail'):
        from .shopping_order_detail import detail_checks
        try:checks.update(detail_checks(expected['order_detail'],page.get('order_detail')))
        except (ValueError,TypeError,KeyError) as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':str(exc)}
    if expected.get('reddit_native_navigation'):
        from .reddit_native_navigation import checks as native_navigation_checks
        try:
            spec=expected['reddit_native_navigation'];state=page.get('reddit_native_navigation')
            if contract.get('domain')!='reddit':raise ValueError('Native Reddit navigation requires the Reddit domain')
            if isinstance(state,dict) and state.get('url')!=page['url']:raise ValueError('Native navigation capture and terminal URL differ')
            if spec.get('kind') in ('skip_region','region_destination') and spec.get('initial_path')!=contract.get('start_path'):raise ValueError('Native region reference differs from original task start')
            checks.update(native_navigation_checks(spec,state,site_origin=site_origin,
                baseline=state.get('initial_state') if isinstance(state,dict) else None,
                navigation_clicks=page.get('navigation_clicks')))
        except (ValueError,TypeError,KeyError) as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':'Native Reddit navigation capture/reference error: '+str(exc)}
    if expected.get('reddit_ui'):
        from .reddit_ui_state import checks as ui_checks
        try:checks.update(ui_checks(expected['reddit_ui'],page.get('reddit_ui')))
        except (ValueError,TypeError,KeyError) as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':str(exc)}
    if expected.get('visible_form'):
        from .visible_form import form_checks
        try:checks.update(form_checks(expected['visible_form'],page.get('visible_form')))
        except (ValueError,TypeError,KeyError) as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':str(exc)}
    if expected.get('group_form'):
        from .gitlab_group_form import form_checks
        try:checks.update(form_checks(expected['group_form'],page.get('group_form')))
        except (ValueError,TypeError,KeyError) as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':str(exc)}
    if expected.get('project_directory'):
        from .gitlab_directory import directory_checks
        try:checks.update(directory_checks(expected['project_directory'],page.get('project_directory'),page['url']))
        except (ValueError,TypeError,KeyError) as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':'Project directory capture/reference error: '+str(exc)}
    if expected.get('issuable_list'):
        from .gitlab_issuable_list import list_checks
        try:checks.update(list_checks(expected['issuable_list'],page.get('issuable_list'),page['url']))
        except (ValueError,TypeError,KeyError) as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':'Issuable list capture/reference error: '+str(exc)}
    if expected.get('forum_list'):
        from .reddit_forum_list import forum_list_checks
        try:checks.update(forum_list_checks(expected['forum_list'],page.get('forum_list'),page['url']))
        except (ValueError,TypeError,KeyError) as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':'Forum directory capture/reference error: '+str(exc)}
    if expected.get('product_gallery'):
        from .shopping_gallery import gallery_checks
        try:checks.update(gallery_checks(expected['product_gallery'],page.get('product_gallery'),page.get('gallery_samples')))
        except (ValueError,TypeError,KeyError) as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':'Product gallery capture/reference error: '+str(exc)}
    if expected.get('product_panel'):
        from .shopping_product_panel import panel_checks
        try:checks.update(panel_checks(expected['product_panel'],page.get('product_panel')))
        except (ValueError,TypeError,KeyError) as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':'Product panel capture/reference error: '+str(exc)}
    if expected.get('post_list'):
        from .reddit_post_list import post_list_checks
        try:checks.update(post_list_checks(expected['post_list'],page.get('post_list'),page['url']))
        except (ValueError,TypeError,KeyError) as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':'Post list capture/reference error: '+str(exc)}
    if expected.get('product_details'):
        from .shopping_product_details import details_checks
        try:checks.update(details_checks(expected['product_details'],page.get('product_details')))
        except (ValueError,TypeError,KeyError) as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':'Product detail capture/reference error: '+str(exc)}
    if expected.get('map_route'):
        from .map_route import route_checks
        try:checks.update(route_checks(expected['map_route'],page.get('map_route'),page['url']))
        except (ValueError,KeyError,TypeError) as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':'Map route capture/reference error: '+str(exc)}
    if expected.get('map_panel'):
        from .map_panel import panel_checks
        try:checks.update(panel_checks(expected['map_panel'],page.get('map_panel')))
        except (ValueError,KeyError,TypeError) as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':'Map panel capture/reference error: '+str(exc)}
    if expected.get('reddit_search'):
        from .reddit_search import search_checks
        try:checks.update(search_checks(expected['reddit_search'],page.get('reddit_search'),page['url']))
        except (ValueError,KeyError,TypeError) as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':'Search capture/reference error: '+str(exc)}
    if expected.get('category'):

        from .shopping_category import category_checks
        try:checks.update(category_checks(expected['category'],page.get('category'),page['url']))
        except (ValueError,KeyError,TypeError) as exc:
            return {'version':VERSION,'status':'unknown','reward':None,'checks':checks,'reason':'Category capture/reference error: '+str(exc)}
    status='success' if all(checks.values()) else 'failure'
    return {'version':VERSION,'status':status,'reward':float(status=='success'),'checks':checks,'reason':None}


def navigation_feedback(judgment):
    """Expose failed conditions, never the hidden target URL, bids or action plan."""
    if judgment.get('version')=='gitlab-native-content-v1':
        from .gitlab_native_content import feedback as content_feedback
        return content_feedback(judgment)
    from . import shopping_native_three_runtime as native_three
    if judgment.get('version')==native_three.VERSION:return native_three.feedback(judgment)
    meanings={'target_query_parameters':'The final page has the requested page number or filter state.',
              'correct_site':'The final page belongs to the task website.',
              'page_valid':'The final page is valid for the requested task, without a browser or website error.',
              'target_path':'The final page is the requested type of page for the target object.',
              'target_heading':'The displayed page heading identifies the requested object or section.',
              'target_title':'The page title identifies the requested target.',
              'repository_identity':'The loaded repository belongs to the requested project.',
              'repository_content_loaded':'The native repository content has finished loading.',
              'repository_object_content':'The requested directory, file, or history is actually displayed.'}
    from .gitlab_section import FEEDBACK as section_feedback
    meanings.update(section_feedback)
    meanings['requested_navigation_control_used']='The navigation control explicitly requested in the task was used.'
    from .document_sections import FEEDBACK as document_section_feedback
    meanings.update(document_section_feedback)
    from .shopping_cms_section import FEEDBACK as cms_feedback
    meanings.update(cms_feedback)
    from .gitlab_todo_target import FEEDBACK as todo_target_feedback
    meanings.update(todo_target_feedback)
    from .shopping_recent_items import FEEDBACK as recent_feedback
    meanings.update(recent_feedback)
    from .gitlab_project_search import FEEDBACK as project_search_feedback
    meanings.update(project_search_feedback)
    from .gitlab_label_filter import FEEDBACK as label_feedback
    meanings.update(label_feedback)
    from .map_diary_page import FEEDBACK as diary_feedback
    from .map_gps_page import FEEDBACK as gps_feedback
    meanings.update(gps_feedback)
    from .gitlab_help_document import FEEDBACK as help_feedback
    from .gitlab_ide import FEEDBACK as ide_feedback
    meanings.update(diary_feedback)
    meanings.update(help_feedback)
    meanings.update(ide_feedback)
    from .gitlab_starrer_coverage import FEEDBACK as starrer_feedback
    meanings.update(starrer_feedback)
    from .shopping_product_details import FEEDBACK as product_details_feedback
    meanings.update(product_details_feedback)
    from .map_list_page import FEEDBACK as map_list_feedback
    meanings.update(map_list_feedback)
    from .map_place_page import FEEDBACK as map_place_feedback
    meanings.update(map_place_feedback)
    from .shopping_cart_details import FEEDBACK as cart_details_feedback
    meanings.update(cart_details_feedback)
    from .map_route import FEEDBACK as route_feedback
    meanings.update(route_feedback)
    from .map_panel import FEEDBACK as map_panel_feedback
    meanings.update(map_panel_feedback)
    from .map_editor_navigation import FEEDBACK as editor_feedback
    from .map_native_navigation import FEEDBACK as native_map_feedback
    meanings.update(editor_feedback)
    meanings.update(native_map_feedback)
    from .shopping_category import FEEDBACK as category_feedback
    meanings.update(category_feedback)
    from .reddit_search import FEEDBACK as reddit_search_feedback
    meanings.update(reddit_search_feedback)
    from .reddit_native_navigation import FEEDBACK as native_navigation_feedback
    meanings.update(native_navigation_feedback)
    from .reddit_ui_state import FEEDBACK as reddit_ui_feedback
    meanings.update(reddit_ui_feedback)
    meanings['profile_address_matches_heading']='The displayed user profile identifies the same user as its address.'
    meanings['complete_article_equivalent']='The complete requested article title and body are displayed in the correct repository.'
    meanings['requested_item_details_displayed']='The requested item details are displayed in a valid product page or its expanded native cart options.'
    meanings.update(requested_project_page='The project list displays the requested page and sorting mode.',
        requested_page_projects='The visible projects and their order match the requested list page.',
        project_directory_present='The native project directory is displayed.',
        directory_parameters_unambiguous='The applied list parameters are unambiguous.',
        rendered_project_identities='The displayed projects match existing unique repository objects.',
        rendered_project_values='Displayed project values agree with the stored project records.',
        directory_scope='The requested project collection is preserved.',
        requested_project_search='The requested project search has been applied.',
        requested_project_visibility='The requested visibility filter has been applied.',
        rendered_visibility_matches='Displayed projects have the selected visibility.',
        matching_project_results='The actual result list matches the applied criteria and pagination.',
        requested_project_sort='The requested sorting is active.',
        requested_project_trending='The native trending project collection is active.',
        project_values_in_order='The actual project values follow the requested ordering.',
        explore_tab_active='The project exploration view is active.')
    from .gitlab_issuable_list import FEEDBACK
    meanings.update(FEEDBACK)
    from .reddit_forum_list import FEEDBACK as FORUM_FEEDBACK
    meanings.update(FORUM_FEEDBACK)
    from .shopping_product_panel import FEEDBACK as PANEL_FEEDBACK
    meanings.update(PANEL_FEEDBACK)
    from .shopping_gallery import FEEDBACK as GALLERY_FEEDBACK
    meanings.update(GALLERY_FEEDBACK)
    from .reddit_post_list import FEEDBACK as POST_FEEDBACK
    meanings.update(POST_FEEDBACK)
    from .gitlab_group_form import FEEDBACK as GROUP_FORM_FEEDBACK
    meanings.update(GROUP_FORM_FEEDBACK)
    from .shopping_order_detail import FEEDBACK as ORDER_DETAIL_FEEDBACK
    meanings.update(ORDER_DETAIL_FEEDBACK)
    from .visible_form import FEEDBACK as VISIBLE_FORM_FEEDBACK
    meanings.update(VISIBLE_FORM_FEEDBACK)
    return {'status':judgment['status'],'reward':judgment['reward'],
            'checks':[{'name':k,'passed':v,'condition':meanings[k]} for k,v in judgment['checks'].items()],
            'reason':judgment.get('reason'),'action_sequence_provided':False}


ADMISSION_VERSION = 'navigation-admission-v3'


def valid_initial_page(page, *, site_origin):
    """Start-state health, independent of task success or the actor's actions."""
    if not isinstance(page, dict): return False
    status=page.get('http_status')
    actual=urlsplit(page.get('url') or '')
    expected=urlsplit(site_origin)
    return (type(status) is int and 200 <= status < 300
            and (actual.scheme, actual.netloc)==(expected.scheme, expected.netloc)
            and page.get('login_page') is False and page.get('error_page') is False)


def control_admission(contract, cases, *, site_origin):
    adapter=_native_completion_adapter(contract)
    if adapter is not None:return adapter.control_admission(contract,cases,site_origin=site_origin)
    allow_initial=contract.get('allow_initial_success',False)
    if type(allow_initial)is not bool:raise ValueError('Initial-goal policy must be explicit boolean')
    aliases=contract.get('control_positive_paths',[])
    if not isinstance(aliases,list) or any(not isinstance(v,str) or not v.startswith('/') or v.startswith('//') for v in aliases):
        raise ValueError('Positive aliases must be local absolute paths')
    names=('initial_no_op','positive','wrong_target','404','login')+tuple('positive_alias_'+str(i) for i in range(len(aliases)))
    if contract['completion'].get('repository'):names+=('wrong_repository','url_only')
    if contract['completion'].get('repository',{}).get('document_equivalence'):names+=('incomplete_document','wrong_document_diff')
    if contract['completion'].get('repository',{}).get('visible_section'):names+=('wrong_document_section','incomplete_section')
    if contract['completion'].get('labeled_issues'):names+=('unfiltered_issues','wrong_issue_label','blank_labeled_list','url_only')
    if contract['completion'].get('todo_target'):names+=('wrong_todo_identity','hidden_todo_title','url_only')
    if contract['completion'].get('recent_ordered_items'):names+=('hidden_recent_items','missing_recent_item','wrong_recent_identity','url_only')
    if contract['completion'].get('project_search'):names+=('unsubmitted_search','wrong_search_scope','blank_search_results','url_only')
    if contract['completion'].get('cms_section'):names+=('wrong_cms_section','incomplete_cms_section','url_only')
    if contract['completion'].get('navigation_control'):names+=('direct_navigation','wrong_navigation_control')
    if contract['completion'].get('group_form'):names+=('wrong_value',)
    if contract['completion'].get('order_detail'):names+=('missing_details',)
    if contract['completion'].get('visible_form'):names+=('hidden_form',)
    if contract['completion'].get('visible_form',{}).get('values'):names+=('wrong_form_value',)
    if contract['completion'].get('reddit_native_navigation'):
        from .reddit_native_navigation import required_negatives
        names+=required_negatives(contract['completion']['reddit_native_navigation'])
    if contract['completion'].get('reddit_ui'):names+=('closed_ui','state_only',)
    if contract['completion'].get('reddit_ui',{}).get('kind')=='comment_formatting_help':names+=('incomplete_comment_help','wrong_help_context')
    if contract.get('verify_url_only') and 'url_only' not in names:names+=('url_only',)
    if contract['completion'].get('map_list'):names+=('blank_list',)
    if contract['completion'].get('map_diary'):names+=('blank_diary','incomplete_diary','wrong_diary_identity')
    if contract['completion'].get('map_gps'):
        names+=('blank_gps','wrong_gps_identity','incomplete_gps')
        names+=tuple(f'{kind}_gps_detail_{i}'for i in range(len(contract['completion']['map_gps']['traces']))for kind in ('blank','wrong','incomplete'))
        gps=contract['completion']['map_gps']
        if gps.get('scope')=='all_public':
            names+=tuple(f'owner_gps_subset_{i}'for i in range(len({r['author']for r in gps['traces']})))
            names+=tuple(f'single_gps_detail_{i}'for i in range(len(gps['traces'])))
    if contract['completion'].get('map_diary',{}).get('allow_entry_page'):
        names+=tuple(f'{kind}_diary_detail_{i}'for i in range(len(contract['completion']['map_diary']['entries']))for kind in ('blank','incomplete','wrong'))
    if contract['completion'].get('help_document'):names+=('blank_help','incomplete_help')
    if contract['completion'].get('web_ide'):names+=('blank_ide','empty_ide_tree','wrong_ide_project')
    if contract['completion'].get('starrer_collection'):
        names+=('first_starrer_page_only','repeated_starrer_page','missing_starrer_identity','wrong_starrer_identity','blank_starrer_list')
    if contract['completion'].get('map_place'):names+=('wrong_place','missing_place_content')
    if contract['completion'].get('map_list',{}).get('initial_map'):names+=('wrong_history_area',)
    if contract['completion'].get('map_list',{}).get('native_area_reference'):names+=('native_history_navigation',)
    if contract['completion'].get('project_directory'):
        names+=('url_only',)
        if contract['completion']['project_directory']['kind']=='search':names+=('unsubmitted',)
    if contract['completion'].get('product_gallery'):
        names+=('unviewed_images','hidden_gallery','unloaded_image','index_only')
    if contract['completion'].get('product_panel'):
        names+=('closed_panel',)
        if contract['completion']['product_panel']['mode']=='description':names+=('incomplete_description',)
        names+=tuple('positive_review_page_'+str(k) for k in contract['completion']['product_panel'].get('review_pages',{}))
    if contract['completion'].get('post_list'):names+=('wrong_sort',)
    if contract['completion'].get('product_details',{}).get('cart_options'):
        names+=('cart_details_positive','cart_details_closed','cart_details_wrong_object')
    if contract['completion'].get('map_route'):
        names+=('unsubmitted_route',)
        if contract.get('wrong_mode_path'):names+=('wrong_mode',)
    if contract['completion'].get('map_panel'):
        names+=('closed_panel',)
        if contract['completion']['map_panel']['kind']=='image_format':names+=('wrong_format',)
        if contract['completion']['map_panel']['kind']=='export_form':names+=('invalid_bounds',)
    if any(k not in cases for k in names):
        return {'passed':False,'status':'missing_controls','checks':{}}
    judgments={k:evaluate_navigation(contract,cases[k],site_origin=site_origin) for k in names}
    from .site_start_state import valid_task_start
    initial_valid=valid_task_start(contract,cases['initial_no_op'],site_origin=site_origin)
    wrong_valid=valid_initial_page(cases['wrong_target'],site_origin=site_origin)
    positive_names=['positive']+['positive_alias_'+str(i) for i in range(len(aliases))]
    if allow_initial and judgments['initial_no_op']['status']=='success':positive_names+=['initial_no_op']
    if contract['completion'].get('map_list',{}).get('native_area_reference'):positive_names+=['native_history_navigation']
    from .authentication_page import login_is_target
    if login_is_target(contract):positive_names+=['login']
    positive_names+=['positive_review_page_'+str(k) for k in contract['completion'].get('product_panel',{}).get('review_pages',{})]
    if contract['completion'].get('product_details',{}).get('cart_options'):positive_names+=['cart_details_positive']
    expected=all(judgments[k]['status']=='success' for k in positive_names) and all(
        judgments[k]['status']=='failure' for k in names if k not in positive_names)
    if contract['completion'].get('repository'):wrong_valid=wrong_valid and valid_initial_page(cases['wrong_repository'],site_origin=site_origin)
    listing_valid=True
    pattern=contract['completion'].get('distinct_list_heading_regex')
    if pattern:
        positive_items={m.group(1) for h in cases['positive'].get('heading_texts',[]) for m in re.finditer(pattern,h)}
        wrong_items={m.group(1) for h in cases['wrong_target'].get('heading_texts',[]) for m in re.finditer(pattern,h)}
        listing_valid=bool(positive_items and wrong_items and positive_items.isdisjoint(wrong_items))
    status=('invalid_initial_page' if not initial_valid else
            'initial_goal_already_satisfied' if not allow_initial and judgments['initial_no_op']['status']=='success' else
            'passed' if expected and wrong_valid and listing_valid else 'contract_or_control_mismatch')
    return {'passed':status=='passed','status':status,'admission_version':ADMISSION_VERSION,
            'initial_goal_satisfied':judgments['initial_no_op']['status']=='success',
            'valid_initial_page':initial_valid,'valid_wrong_object_control':wrong_valid,'distinct_listing_control':listing_valid,
            'checks':{k:v['status'] for k,v in judgments.items()}}


def contract_fingerprint(contract):
    adapter=_native_completion_adapter(contract)
    if adapter is not None:return adapter.fingerprint(contract)
    import hashlib,json
    # Binding includes initialization and split; completion-only proofs are insufficient.
    payload={k:contract.get(k) for k in ('task_id','source_task_id','domain','goal',
             'start_path','completion','heldout_quarantine','start_revision')}
    # Preserve existing proofs without a policy; bind every explicit exception.
    if 'initial_page_policy'in contract:payload['initial_page_policy']=contract['initial_page_policy']
    if 'completion_revision'in contract:payload['completion_revision']=contract['completion_revision']
    if contract.get('control_positive_paths') is not None:payload['control_positive_paths']=contract['control_positive_paths']
    if 'allow_initial_success'in contract:payload['allow_initial_success']=contract['allow_initial_success']
    if contract.get('map_community_fixture') or contract['completion'].get('map_diary')or contract['completion'].get('map_gps'):
        payload['community_initialization']={k:contract.get(k)for k in ('map_community_fixture','environment_revision')}
    if contract['completion'].get('navigation_control'):payload['navigation_control_paths']={k:contract.get(k)for k in ('control_link_selector','wrong_control_path','wrong_control_link_selector')}
    if contract['completion'].get('repository'):
        payload['repository_negative_paths']=[contract.get('wrong_target_path'),contract.get('wrong_repository_path')]
    if contract['completion'].get('project_directory'):payload['directory_wrong_target']=contract.get('wrong_target_path')
    if contract['completion'].get('repository',{}).get('document_equivalence'):payload['document_negative_path']=contract.get('document_negative_path')
    if contract['completion'].get('labeled_issues'):payload.update({k:contract.get(k)for k in ('unfiltered_issues_path','wrong_issue_label_path')})
    if contract['completion'].get('project_search'):payload['wrong_search_scope_path']=contract.get('wrong_search_scope_path')
    if contract['completion'].get('repository',{}).get('visible_section'):payload['wrong_document_section_path']=contract.get('wrong_document_section_path')
    if contract.get('verify_url_only'):payload['url_only_control']={'required':True,'wrong_target_path':contract.get('wrong_target_path')}
    if contract['completion'].get('post_list'):payload['wrong_sort_path']=contract.get('wrong_sort_path')
    if contract['completion'].get('map_route'):payload['wrong_mode_path']=contract.get('wrong_mode_path')
    if contract['completion'].get('map_place'):payload['wrong_place_path']=contract.get('wrong_place_path')
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()


def require_admission(contract, proof):
    from . import map_native_layer_runtime as native_layers
    if native_layers.enabled(contract):return native_layers.require_admission(contract,proof)
    from . import gitlab_native_csv_runtime as native_csv
    if native_csv.enabled(contract):return native_csv.require_admission(contract,proof)
    from . import reddit_native_read_runtime as native_reddit_read
    if native_reddit_read.enabled(contract):return native_reddit_read.require_admission(contract,proof)
    from . import gitlab_native_read_runtime as native_gitlab_read
    if native_gitlab_read.enabled(contract):return native_gitlab_read.require_admission(contract,proof)
    from . import shopping_native_three_runtime as native_three
    if native_three.enabled(contract):return native_three.require_admission(contract,proof)
    adapter=_native_completion_adapter(contract)
    if adapter is not None:return adapter.require_admission(contract,proof)
    from .authentication_page import login_is_target
    if type(contract.get('allow_initial_success',False))is not bool:raise ValueError('Initial-goal policy must be explicit boolean')
    if contract.get('heldout_quarantine'):raise ValueError('Heldout task cannot enter development tests')
    if proof.get('admission_version')!=ADMISSION_VERSION or proof.get('contract_fingerprint')!=contract_fingerprint(contract):
        raise ValueError('Admission is missing, stale, or bound to a different task/start state')
    cycles=proof.get('cycles',[])
    if contract.get('domain')=='map' and (len(cycles)!=2 or not all(
        c.get('clean_reset_verified') is True and c.get('dirty_reuse_refused') is True for c in cycles)):
        raise ValueError('Map admission requires clean reset and dirty-state rejection in both deployments')
    if (not proof.get('passed') or len(cycles)!=2
        or len({c.get('initial_fingerprint') for c in cycles})!=1
        or any(not c.get('initial_fingerprint') or c.get('initial_fingerprint')!=c.get('final_fingerprint') for c in cycles)
        or not all(any(t.get('task_id')==contract['task_id'] and t.get('passed') and t.get('valid_initial_page') for t in c.get('tasks',[])) for c in cycles)):
        raise ValueError('Two valid initial-state/control/reset cycles are required')
    if contract.get('allow_initial_success') and any(not any(
        t.get('task_id')==contract['task_id'] and t.get('checks',{}).get('initial_no_op')in ('success','failure') and
        type(t.get('initial_goal_satisfied'))is bool and
        t['initial_goal_satisfied']==(t['checks']['initial_no_op']=='success') and
        all(t.get('checks',{}).get(k)=='failure'for k in ('wrong_target','404')) and
        t.get('checks',{}).get('login')==('success'if login_is_target(contract)else 'failure')
        for t in cycle.get('tasks',[]))for cycle in cycles):
        raise ValueError('Initial-goal policy requires actual initial verdict and independent negative controls')
    if contract['completion'].get('labeled_issues'):
        from .gitlab_label_filter import validate
        validate(contract['completion']['labeled_issues'])
        required={'positive':'success',**{k:'failure'for k in ('unfiltered_issues','wrong_issue_label','blank_labeled_list','url_only')}}
        required.update({'positive_alias_'+str(i):'success'for i in range(len(contract.get('control_positive_paths',[])))})
        if contract.get('domain')!='gitlab' or any(not any(t.get('task_id')==contract['task_id'] and
            all(t.get('checks',{}).get(k)==v for k,v in required.items()) for t in cycle.get('tasks',[])) for cycle in cycles):
            raise ValueError('Labeled issues require native status aliases and label/content negative controls')
    if contract['completion'].get('reddit_native_navigation'):
        from .reddit_native_navigation import validate,required_negatives
        spec=contract['completion']['reddit_native_navigation'];validate(spec)
        required={'positive':'success',**{k:'failure' for k in ('initial_no_op','wrong_target','404','login')+required_negatives(spec)}}
        rows=[next((t for t in cycle.get('tasks',[]) if t.get('task_id')==contract['task_id']),{}) for cycle in cycles]
        if (contract.get('domain')!='reddit' or not contract.get('verify_url_only')
                or any(t.get('reddit_native_reference_unchanged') is not True or
                       any(t.get('checks',{}).get(k)!=v for k,v in required.items()) for t in rows)):
            raise ValueError('Native Reddit navigation requires actual content/activation negatives and unchanged references in both resets')
        if spec['kind']=='region_destination':
            from .reddit_native_navigation import initial_fingerprint
            from .reddit_native_read_runtime import validate_complete_snapshot
            supplement=proof.get('region_destination_controls',{})
            actual=supplement.get('cycles',[])
            if (supplement.get('version')!='region-destination-supplement-v1'
                    or not re.fullmatch('[0-9a-f]{64}',supplement.get('raw_archive_sha256',''))
                    or len(actual)!=2 or [c.get('cycle')for c in actual]!=[0,1]):
                raise ValueError('Actual two-cold destination observations required')
            for index,cycle in enumerate(actual):
                before=validate_complete_snapshot(cycle.get('complete13_before'))
                if before!=validate_complete_snapshot(cycle.get('complete13_after')):
                    raise ValueError('Destination control state changed')
                if index and before!=actual[0]['complete13_before']:
                    raise ValueError('Destination control cold baselines differ')
                captures=cycle.get('controls',{})
                if set(captures)!={'no_op','keyboard','direct_fragment'}:
                    raise ValueError('Actual initial, keyboard and fragment captures required')
                for name,capture in captures.items():
                    page=capture['page'];state=page['reddit_native_navigation']
                    if initial_fingerprint(state['initial_state'])!=rows[index]['reddit_native_initial_fingerprint']:
                        raise ValueError('Supplemental original page/region differs from independent controls')
                    reproduced=evaluate_navigation(contract,page,site_origin=capture['site_origin'])
                    if reproduced['status']!=('failure'if name=='no_op'else'success'):
                        raise ValueError('Destination control cannot be reproduced: '+name)
        if spec['kind'] in ('skip_region','region_destination') and (spec['initial_path']!=contract.get('start_path') or
                any(not t.get('reddit_native_initial_fingerprint') for t in rows) or
                len({t.get('reddit_native_initial_fingerprint') for t in rows})!=1):
            raise ValueError('Native skip navigation requires identical original region baselines in both resets')
    if contract['completion'].get('recent_ordered_items'):
        from .shopping_recent_items import validate
        validate(contract['completion']['recent_ordered_items'])
        required={'positive':'success',**{'positive_alias_'+str(i):'success' for i in range(len(contract.get('control_positive_paths',[])))},
                  **{k:'failure' for k in ('hidden_recent_items','missing_recent_item','wrong_recent_identity','url_only','wrong_target','404','login','initial_no_op')}}
        if (contract.get('domain')!='shopping' or not contract.get('verify_url_only') or any(not any(
            t.get('task_id')==contract['task_id'] and t.get('recent_items_reference_unchanged') is True and
            all(t.get('checks',{}).get(k)==v for k,v in required.items())
            for t in cycle.get('tasks',[])) for cycle in cycles)):
            raise ValueError('Recent items require native content/identity negatives, all account aliases, and unchanged order references in both resets')
    if contract['completion'].get('todo_target'):
        from .gitlab_todo_target import validate
        spec=contract['completion']['todo_target'];validate(spec)
        paths=[contract.get('control_target_path')]+contract.get('control_positive_paths',[])
        required={'positive':'success',**{'positive_alias_'+str(i):'success' for i in range(len(paths)-1)},
                  **{k:'failure' for k in ('wrong_todo_identity','hidden_todo_title','url_only')}}
        if (contract.get('domain')!='gitlab' or len(paths)!=len(set(paths)) or set(paths)!=set(spec['targets'])
            or any(not any(t.get('task_id')==contract['task_id'] and all(t.get('checks',{}).get(k)==v for k,v in required.items())
                       for t in cycle.get('tasks',[])) for cycle in cycles)):
            raise ValueError('To-do navigation requires all target alternatives and native identity controls')
    if contract['completion'].get('project_search'):
        from .gitlab_project_search import validate
        validate(contract['completion']['project_search'])
        required={'positive':'success','positive_alias_0':'success','unsubmitted_search':'failure','wrong_search_scope':'failure','blank_search_results':'failure','url_only':'failure'}
        if contract.get('domain')!='gitlab' or not contract.get('control_positive_paths') or any(not any(t.get('task_id')==contract['task_id'] and
            all(t.get('checks',{}).get(k)==v for k,v in required.items()) for t in cycle.get('tasks',[])) for cycle in cycles):
            raise ValueError('Project search requires both native search surfaces and independent negative controls')
    if contract['completion'].get('cms_section'):
        from .shopping_cms_section import validate
        validate(contract['completion']['cms_section'])
        required={'positive':'success','wrong_cms_section':'failure','incomplete_cms_section':'failure','url_only':'failure'}
        if contract.get('domain')!='shopping' or any(not any(t.get('task_id')==contract['task_id'] and
            all(t.get('checks',{}).get(k)==v for k,v in required.items()) for t in cycle.get('tasks',[])) for cycle in cycles):
            raise ValueError('CMS section requires native visibility, incomplete-content and URL-only controls')
    if contract['completion'].get('navigation_control') and any(not any(
        t.get('task_id')==contract['task_id'] and t.get('checks',{}).get('positive')=='success' and
        all(t.get('checks',{}).get(k)=='failure' for k in ('direct_navigation','wrong_navigation_control'))
        for t in cycle.get('tasks',[])) for cycle in cycles):
        raise ValueError('Navigation-method admission requires actual click and wrong/direct-route controls')
    if contract['completion'].get('repository') and any(
        not any(t.get('task_id')==contract['task_id'] and all(t.get('checks',{}).get(k)=='failure' for k in ('wrong_repository','url_only')) for t in c.get('tasks',[])) for c in cycles):
        raise ValueError('Repository admission requires wrong-project and URL-only rejection')
    if contract['completion'].get('repository',{}).get('document_equivalence'):
        if not contract.get('control_positive_paths') or any(not any(t.get('task_id')==contract['task_id'] and
            all(t.get('checks',{}).get(k)=='failure' for k in ('incomplete_document','wrong_document_diff')) and
            all(t.get('checks',{}).get('positive_alias_'+str(i))=='success' for i in range(len(contract['control_positive_paths'])))
            for t in cycle.get('tasks',[])) for cycle in cycles):
            raise ValueError('Article equivalence requires complete/partial/wrong-document live controls')
    if contract['completion'].get('project_directory'):
        required=['url_only']+(['unsubmitted'] if contract['completion']['project_directory']['kind']=='search' else [])
        if any(not any(t.get('task_id')==contract['task_id'] and all(t.get('checks',{}).get(k)=='failure' for k in required) for t in c.get('tasks',[])) for c in cycles):
            raise ValueError('Project directory admission requires unchanged-content and unsubmitted-search rejection')
    if contract.get('verify_url_only') and any(not any(t.get('task_id')==contract['task_id'] and t.get('checks',{}).get('url_only')=='failure' for t in c.get('tasks',[])) for c in cycles):
        raise ValueError('Navigation admission requires unchanged-content rejection')
    if contract['completion'].get('map_diary'):
        from .map_diary_page import validate
        from .map_community_fixture import profile_for_contracts
        validate(contract['completion']['map_diary'])
        profile_for_contracts([contract],contract.get('domain'))
        if any(not any(t.get('task_id')==contract['task_id'] and t.get('checks',{}).get('positive')=='success' and
            all(t.get('checks',{}).get(k)=='failure'for k in ('blank_diary','incomplete_diary','wrong_diary_identity'))
            for t in cycle.get('tasks',[]))for cycle in cycles):
            raise ValueError('Populated diaries require native empty, incomplete, and wrong-identity controls')
        spec=contract['completion']['map_diary']
        if spec.get('allow_entry_page'):
            paths=['/user/'+r['author']+'/diary/'+str(r['id'])for r in spec['entries']]
            required=[f'{kind}_diary_detail_{i}'for i in range(len(paths))for kind in ('blank','incomplete','wrong')]
            if contract.get('control_positive_paths')!=paths or any(not any(
                t.get('task_id')==contract['task_id']and
                all(t.get('checks',{}).get(f'positive_alias_{i}')=='success'for i in range(len(paths)))and
                all(t.get('checks',{}).get(k)=='failure'for k in required)for t in cycle.get('tasks',[]))for cycle in cycles):
                raise ValueError('Diary details require native positive and negative controls for every admitted entry')
    if contract['completion'].get('map_gps'):
        from .map_gps_page import validate
        from .map_community_fixture import profile_for_contracts,GPS_PROFILE
        spec=contract['completion']['map_gps'];validate(spec)
        if profile_for_contracts([contract],contract.get('domain'))!=GPS_PROFILE:raise ValueError('Wrong GPS environment admission')
        paths=['/user/'+a+'/traces'for a in sorted({r['author']for r in spec['traces']})]
        paths+=['/user/'+r['author']+'/traces/'+str(r['id'])for r in spec['traces']]
        required=['blank_gps','wrong_gps_identity','incomplete_gps']
        required +=[f'{kind}_gps_detail_{i}'for i in range(len(spec['traces']))for kind in ('blank','wrong','incomplete')]
        if spec.get('scope')=='all_public':
            paths=['/traces?page=1']
            required +=[f'owner_gps_subset_{i}'for i in range(len({r['author']for r in spec['traces']}))]
            required +=[f'single_gps_detail_{i}'for i in range(len(spec['traces']))]
        if contract.get('control_positive_paths')!=paths or any(not any(t.get('task_id')==contract['task_id']
            and t.get('checks',{}).get('positive')=='success'and all(t.get('checks',{}).get(k)=='failure'for k in required)
            and all(t.get('checks',{}).get('positive_alias_'+str(i))=='success'for i in range(len(paths)))
            for t in cycle.get('tasks',[]))for cycle in cycles):
            raise ValueError('Populated GPS requires list/detail identity and content controls')
    if contract['completion'].get('starrer_collection'):
        from .gitlab_starrer_coverage import validate
        spec=contract['completion']['starrer_collection'];validate(spec)
        paths=['/'+spec['project']+'/-/starrers?page='+str(i)for i in range(2,len(spec['pages'])+1)]
        required=['first_starrer_page_only','repeated_starrer_page','missing_starrer_identity','wrong_starrer_identity','blank_starrer_list']
        if contract.get('domain')!='gitlab'or contract.get('control_positive_paths')!=paths or any(not any(
            t.get('task_id')==contract['task_id']and t.get('checks',{}).get('positive')=='success'
            and all(t.get('checks',{}).get(k)=='failure'for k in required)
            and all(t.get('checks',{}).get('positive_alias_'+str(i))=='success'for i in range(len(paths)))
            for t in cycle.get('tasks',[]))for cycle in cycles):
            raise ValueError('All-starrer admission requires native pagination and incomplete-exposure controls')
    if contract['completion'].get('web_ide'):
        from .gitlab_ide import validate
        validate(contract['completion']['web_ide'])
        if contract.get('domain')!='gitlab'or any(not any(t.get('task_id')==contract['task_id'] and
            t.get('checks',{}).get('positive')=='success'and
            all(t.get('checks',{}).get(k)=='failure'for k in ('blank_ide','empty_ide_tree','wrong_ide_project'))
            for t in cycle.get('tasks',[]))for cycle in cycles):
            raise ValueError('Web IDE requires native interface, tree and project controls')
    if contract['completion'].get('help_document'):
        from .gitlab_help_document import validate
        validate(contract['completion']['help_document'])
        if contract.get('domain')!='gitlab'or any(not any(t.get('task_id')==contract['task_id'] and
            all(t.get('checks',{}).get(k)=='failure'for k in ('blank_help','incomplete_help'))
            for t in cycle.get('tasks',[]))for cycle in cycles):
            raise ValueError('Help document requires native blank and incomplete-body controls')
    if contract['completion'].get('map_list') and any(not any(t.get('task_id')==contract['task_id'] and t.get('checks',{}).get('blank_list')=='failure' and t.get('native_map_list_reference_verified') is True for t in c.get('tasks',[])) for c in cycles):
        raise ValueError('Native list requires blank-page rejection and matching database state')
    if contract['completion'].get('map_place') and any(not any(t.get('task_id')==contract['task_id'] and t.get('native_map_place_reference_verified')is True and all(t.get('checks',{}).get(k)=='failure'for k in ('wrong_place','missing_place_content'))for t in c.get('tasks',[]))for c in cycles):
        raise ValueError('Native place requires wrong-identity and blank-content controls with unchanged reference')
    if contract['completion'].get('map_list',{}).get('initial_map') and any(not any(t.get('task_id')==contract['task_id'] and t.get('checks',{}).get('wrong_history_area')=='failure' for t in c.get('tasks',[])) for c in cycles):
        raise ValueError('History area requires wrong-area rejection in both deployments')
    if contract['completion'].get('map_list',{}).get('native_area_reference') and any(not any(t.get('task_id')==contract['task_id'] and t.get('checks',{}).get('native_history_navigation')=='success' for t in c.get('tasks',[])) for c in cycles):
        raise ValueError('History layout alternative requires actual native navigation in both deployments')
    if contract['completion'].get('map_route',{}).get('initial_route') and any(not any(t.get('task_id')==contract['task_id'] and t.get('initial_route_verified') is True for t in c.get('tasks',[])) for c in cycles):
        raise ValueError('Route transformation requires verified original route in both deployments')
    if contract['completion'].get('group_form'):
        from .gitlab_group_form import validate
        validate(contract['completion']['group_form'])
        if not contract.get('verify_url_only') or any(not any(t.get('task_id')==contract['task_id'] and
            t.get('checks',{}).get('wrong_value')=='failure' and t.get('group_form_state_unchanged') is True
            for t in c.get('tasks',[])) for c in cycles):
            raise ValueError('Group form requires wrong-setting controls and unchanged saved groups')
    if contract['completion'].get('order_detail'):
        from .shopping_order_detail import validate
        validate(contract['completion']['order_detail'])
        if not contract.get('verify_url_only') or any(not any(t.get('task_id')==contract['task_id'] and
            t.get('checks',{}).get('missing_details')=='failure' and t.get('order_reference_unchanged') is True
            for t in c.get('tasks',[])) for c in cycles):
            raise ValueError('Order details require incomplete-page controls and unchanged references')
    if contract['completion'].get('reddit_ui'):
        from .reddit_ui_state import validate
        validate(contract['completion']['reddit_ui'])
        if contract['completion']['reddit_ui']['kind']=='comment_formatting_help':
            if any(not any(t.get('task_id')==contract['task_id']and all(t.get('checks',{}).get(k)=='failure'
                for k in ('incomplete_comment_help','wrong_help_context'))for t in c.get('tasks',[]))for c in cycles):
                raise ValueError('Comment help context/content controls missing')
        if not contract.get('verify_url_only') or any(not any(t.get('task_id')==contract['task_id'] and
            all(t.get('checks',{}).get(k)=='failure' for k in ('closed_ui','state_only')) for t in c.get('tasks',[])) for c in cycles):
            raise ValueError('Native UI state requires closed and state-only negative controls')
    if contract['completion'].get('reddit_any_profile'):
        if contract.get('domain')!='reddit' or contract['completion']['reddit_any_profile'] is not True or not contract.get('verify_url_only'):
            raise ValueError('Free-choice profiles require an explicit Reddit scope and forged-address control')
    if contract['completion'].get('visible_form'):
        from .visible_form import validate
        validate(contract['completion']['visible_form'])
        if not contract.get('verify_url_only') or any(not any(t.get('task_id')==contract['task_id'] and
            t.get('checks',{}).get('hidden_form')=='failure' for t in c.get('tasks',[])) for c in cycles):
            raise ValueError('Visible form requires hidden-form and unchanged-content negatives')
        if contract['completion']['visible_form'].get('values') and any(not any(
            t.get('task_id')==contract['task_id'] and t.get('checks',{}).get('wrong_form_value')=='failure'
            for t in cycle.get('tasks',[])) for cycle in cycles):
            raise ValueError('Input-value tasks require wrong-value controls in both resets')
    if contract['completion'].get('authentication_page'):
        from .authentication_page import validate
        kind=validate(contract)
        expected_login='success' if kind=='login' else 'failure'
        if any(not any(t.get('task_id')==contract['task_id'] and
            t.get('checks',{}).get('login')==expected_login and
            all(t.get('checks',{}).get(k)=='failure' for k in ('wrong_target','404','hidden_form','url_only')+(()if contract.get('allow_initial_success')else ('initial_no_op',)))
            for t in cycle.get('tasks',[])) for cycle in cycles):
            raise ValueError('Authentication-page navigation requires independent native form controls')
    if contract['completion'].get('issuable_list'):
        if not contract.get('verify_url_only') or any(not any(t.get('task_id')==contract['task_id'] and t.get('issuable_reference_unchanged') is True for t in c.get('tasks',[])) for c in cycles):
            raise ValueError('Issuable list admission requires URL-only rejection and unchanged object references')
    if contract['completion'].get('forum_list'):
        from .reddit_forum_list import accepted_orders
        forum_spec=contract['completion']['forum_list']
        choices=accepted_orders(forum_spec)
        if forum_spec.get('mode')=='browse':
            paths={contract.get('control_target_path'),*contract.get('control_positive_paths',[])}
            if not {'/forums','/forums/all',*('/forums/by_'+s for s in choices)}<=paths:
                raise ValueError('Browse directory requires every native view positively controlled')
            if contract.get('wrong_target_path')in paths:
                raise ValueError('Browse negative must be outside all accepted native views')
            required={'positive':'success',**{'positive_alias_'+str(i):'success'for i in range(len(contract.get('control_positive_paths',[])))},
                      **{k:'failure'for k in ('initial_no_op','url_only','wrong_target','404','login')}}
            if any(not any(t.get('task_id')==contract['task_id'] and all(t.get('checks',{}).get(k)==v for k,v in required.items())
                           for t in cycle.get('tasks',[]))for cycle in cycles):
                raise ValueError('Browse directory requires actual positive views and independent negative controls in both cycles')
        if forum_spec.get('sort_choices'):
            paths={contract.get('control_target_path'),*contract.get('control_positive_paths',[])}
            if not {'/forums/by_'+s for s in choices}<=paths or contract.get('wrong_target_path')!='/forums':
                raise ValueError('Free forum ordering requires every alternative positive and the unchanged default negative')
        if not contract.get('verify_url_only') or any(not any(t.get('task_id')==contract['task_id'] and t.get('forum_reference_unchanged') is True for t in c.get('tasks',[])) for c in cycles):
            raise ValueError('Forum directory admission requires URL-only rejection and unchanged references')
    if contract['completion'].get('product_gallery'):
        from .shopping_gallery import validate
        validate(contract['completion']['product_gallery'])
        if not contract.get('verify_url_only') or any(not any(t.get('task_id')==contract['task_id'] and
            t.get('gallery_reference_unchanged') is True and t.get('gallery_initial_state_verified') is True and
            all(t.get('checks',{}).get(k)=='failure' for k in ('unviewed_images','hidden_gallery','unloaded_image','index_only','url_only'))
            for t in cycle.get('tasks',[])) for cycle in cycles):
            raise ValueError('Gallery admission requires native loaded-image controls and unchanged initial/reference state')
    if contract['completion'].get('product_panel'):
        if not contract.get('verify_url_only') or any(not any(t.get('task_id')==contract['task_id'] and t.get('checks',{}).get('closed_panel')=='failure' and t.get('product_panel_reference_unchanged') is True for t in c.get('tasks',[])) for c in cycles):
            raise ValueError('Product panel admission requires collapsed-panel rejection and unchanged native content')
        if contract['completion']['product_panel']['mode']=='description'and any(not any(t.get('task_id')==contract['task_id']and t.get('checks',{}).get('incomplete_description')=='failure'for t in cycle.get('tasks',[]))for cycle in cycles):
            raise ValueError('Description panel requires incomplete-content rejection in both cycles')
        page_keys=contract['completion']['product_panel'].get('review_pages',{})
        if page_keys and any(not any(t.get('task_id')==contract['task_id'] and all(
            t.get('checks',{}).get('positive_review_page_'+str(k))=='success' for k in page_keys)
            for t in c.get('tasks',[])) for c in cycles):
            raise ValueError('Paginated reviews require every native review page validated in both independent cycles')
    if contract['completion'].get('post_list'):
        if not contract.get('verify_url_only') or any(not any(t.get('task_id')==contract['task_id'] and t.get('checks',{}).get('wrong_sort')=='failure' and t.get('post_reference_unchanged') is True for t in c.get('tasks',[])) for c in cycles):
            raise ValueError('Post list admission requires wrong-sort rejection and unchanged account/submission references')
    if contract['completion'].get('product_details'):
        if not contract.get('verify_url_only') or any(not any(t.get('task_id')==contract['task_id'] and t.get('product_details_reference_unchanged') is True for t in c.get('tasks',[])) for c in cycles):
            raise ValueError('Product detail admission requires URL-only rejection and unchanged identity references')
        if contract['completion']['product_details'].get('cart_options') and any(not any(
            t.get('task_id')==contract['task_id'] and t.get('checks',{}).get('cart_details_positive')=='success'
            and all(t.get('checks',{}).get(k)=='failure' for k in ('cart_details_closed','cart_details_wrong_object'))
            for t in c.get('tasks',[])) for c in cycles):
            raise ValueError('Cart detail alternative requires native expanded/closed/wrong-object controls')
    if contract['completion'].get('map_route'):
        negatives=['url_only','unsubmitted_route']+(['wrong_mode'] if contract.get('wrong_mode_path') else [])
        if not contract.get('verify_url_only') or any(not any(t.get('task_id')==contract['task_id'] and
            t.get('route_reference_unchanged') is True and all(t.get('checks',{}).get(k)=='failure' for k in negatives)
            for t in c.get('tasks',[])) for c in cycles):
            raise ValueError('Route admission needs unchanged backend references, stale/unsubmitted route and wrong-mode rejection')
    if contract['completion'].get('category'):
        if not contract.get('verify_url_only') or any(not any(t.get('task_id')==contract['task_id'] and
            t.get('category_reference_unchanged') is True for t in c.get('tasks',[])) for c in cycles):
            raise ValueError('Category admission needs URL-only rejection and unchanged hierarchy/product membership')

    if contract['completion'].get('reddit_search'):
        if not contract.get('verify_url_only') or any(not any(t.get('task_id')==contract['task_id'] and
            t.get('reddit_search_reference_unchanged') is True for t in c.get('tasks',[])) for c in cycles):
            raise ValueError('Search admission needs URL-only rejection and unchanged native references')
    if contract['completion'].get('map_panel'):
        negative=['url_only','closed_panel']
        if contract['completion']['map_panel']['kind']=='image_format':negative+=['wrong_format']
        if contract['completion']['map_panel']['kind']=='export_form':negative+=['invalid_bounds']
        if not contract.get('verify_url_only') or any(not any(t.get('task_id')==contract['task_id'] and
            t.get('native_panel_reference_verified') is True and all(t.get('checks',{}).get(k)=='failure' for k in negative)
            for t in c.get('tasks',[])) for c in cycles):
            raise ValueError('Map panels need native-source, closed-panel and wrong-setting controls')
