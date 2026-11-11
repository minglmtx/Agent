"""Read-only menu checks; no actor policy or task-specific action repair."""
from urllib.parse import urlsplit

PROTOCOL='admin-menu-navigation-v1'


def menu_checks(spec,page,site_netloc):
    menus=page.get('menus')
    if not isinstance(menus,dict) or spec['menu_id'] not in menus:
        raise ValueError('menu_probe_unresolved')
    target=menus[spec['menu_id']]
    return {'same_local_deployment':urlsplit(page['url']).netloc==site_netloc,
            'valid_authenticated_page':not(page['login'] or page['page_error']),
            'target_menu_identity':target['label'].casefold()==spec['menu_label'].casefold(),
            'target_menu_open':target['show_class'] and target['aria_expanded'] and target['visible']}
