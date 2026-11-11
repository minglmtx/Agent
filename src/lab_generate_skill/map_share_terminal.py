"""Terminal-only rules for declared local Map share artifacts.

References originate before actor execution. Artifact reopening is independent
of the actor context; an unavailable renderer is never a negative reward.
"""
from urllib.parse import urlsplit
from .admin_query_rules import parse_answer
from .map_share_artifact_checks import route_link, short_route_link, view_link, embed_markup
from .map_share_roundtrip import reopened_route, reopened_view, reopened_embed

VERSION='native-map-share-terminal-v1'
FAMILIES={'share_panel_navigation','route_link','short_route_link','view_link','map_embed'}


def output_value(family,answer):
    if family=='share_panel_navigation':return None
    field='embed_html'if family=='map_embed'else'share_link'
    value=parse_answer(answer)
    if set(value)!={field}or not isinstance(value[field],str):raise ValueError('Declared share output field required')
    return value[field]


def declared_artifact(family,value,reference,origin):
    if family=='short_route_link':
        return short_route_link(value,origin=origin,expected_pair=reference['pair'],expected_mode=reference['mode'])
    if family=='route_link':
        return route_link(value,origin=origin,expected_pair=reference['pair'],expected_mode=reference['mode'])
    if family=='view_link':return view_link(value,origin=origin,expected_center=reference['center'])
    if family=='map_embed':return embed_markup(value,origin=origin,width=reference['width'],height=reference['height'],expected_bbox=reference['bbox'],expected_layer='mapnik')
    raise ValueError('An artifact family required')


def evaluate_share(spec,*,reference,answer,page,origin,tile_origin,share=None,terminal_route=None,reopened=None,runtime_error=None,integrity=True,capture_error=None):
    family=spec.get('family')
    if family not in FAMILIES:raise ValueError('Explicit native share family required')
    checks={}
    def result(status,reason):
        return dict(version=VERSION,status=status,reward={'success':1.,'failure':0.,'unknown':None}[status],checks=checks,reason=reason)
    if runtime_error or capture_error or integrity is not True:
        return result('unknown','Runtime, capture or state integrity unavailable.')
    if not isinstance(reference,dict):return result('unknown','Initial native reference unavailable.')
    if family=='share_panel_navigation':
        if not isinstance(page,dict)or type(page.get('http_status'))is not int or page['http_status']>=500:
            return result('unknown','Terminal document health unavailable.')
        u,b=urlsplit(page.get('url','')),urlsplit(origin)
        checks['valid_local_page']=(u.scheme,u.netloc)==(b.scheme,b.netloc)and 200<=page['http_status']<300 and page.get('login_page')is False and page.get('error_page')is False
        if not checks['valid_local_page']:return result('failure','Share panel is not displayed on a valid local map page.')
        if not isinstance(share,dict)or not isinstance(terminal_route,dict):return result('unknown','Terminal share/route capture unavailable.')
        checks['share_panel_visible']=share.get('visible')is True
        checks['usable_share_control']=share.get('long_visible')is True and bool(share.get('long_value'))
        try:
            route_checks=reopened_route(origin+reference['start_path'],terminal_route,reference['route'],origin=origin,expected_pair=reference['pair'],expected_mode=reference['mode'])
        except (KeyError,TypeError,ValueError):return result('unknown','Initial route reference incomplete.')
        if terminal_route.get('loading'):return result('unknown','Terminal route is still loading.')
        checks['original_route_retained']=all(route_checks.values())
        return result('success'if all(checks.values())else'failure','Native panel usability and original route checked.')
    try:
        value=output_value(family,answer)
    except (ValueError,TypeError):
        checks['answer_schema']=False
        return result('failure','Required sharing artifact was not returned.')
    checks['answer_schema']=True
    try:checks['declared_artifact']=declared_artifact(family,value,reference,origin)
    except (KeyError,TypeError,ValueError):return result('unknown','Initial artifact reference incomplete.')
    if not checks['declared_artifact']:return result('failure','Returned artifact differs from the declared initial route, view or dimensions.')
    if not isinstance(reopened,dict)or reopened.get('error'):
        return result('unknown','Independent native artifact rendering unavailable.')
    # Bind the proof to the exact artifact returned by the actor.
    if reopened.get('requested')!=value:return result('unknown','Reopened artifact does not match the actual answer.')
    if type(reopened.get('http_status'))is not int or not 200<=reopened['http_status']<300:
        return result('unknown','Declared artifact could not be served by the native environment.')
    try:
        if family in ('route_link','short_route_link'):
            if reopened['state'].get('loading'):return result('unknown','Reopened native route is still loading.')
            verified=reopened_route(reopened['url'],reopened['state'],reference['route'],origin=origin,expected_pair=reference['pair'],expected_mode=reference['mode'])
        elif family=='view_link':verified=reopened_view(reopened['url'],reopened['state'],origin=origin,expected_center=reference['center'],tile_origin=tile_origin)
        else:verified=reopened_embed(reopened['state'],bbox=reference['bbox'],width=reference['width'],height=reference['height'],tile_origin=tile_origin)
    except (KeyError,ValueError,TypeError):return result('unknown','Independent native observation incomplete.')
    checks.update(verified)
    if not all(verified.values()):
        # The declared output passed deterministic identity checks. A native
        # replay that cannot render it indicates a capability/capture problem.
        return result('unknown','Declared artifact passed identity checks but its native roundtrip was not verified.')
    return result('success','Returned native artifact independently reopened and verified.')


def feedback(judgment):
    if judgment.get('version')!=VERSION:raise ValueError('Native share judgment required')
    return dict(status=judgment['status'],reward=judgment['reward'],checks=[dict(condition=k,passed=v)for k,v in judgment['checks'].items()if type(v)is bool],private_reference_values_provided=False,action_sequence_provided=False)
