"""Exact native Map community/navigation profiles qualified for shared startup.

This is dispatch eligibility, not a replacement for native admission/reset checks.
All optional mutating profiles remain outside this entry.
"""
EXTENSION = 'native-community-navigation-v1'
REVIEWED_COMMUNITY_PROFILES = [{'capture_mail': False,
  'community': 'synthetic-local-community-v1',
  'editor': None,
  'gitlab_cache': None,
  'gitlab_initial': None,
  'layers': False,
  'optional': {}},
 {'capture_mail': False,
  'community': 'synthetic-local-community-v1',
  'editor': {'community_fixture': 'synthetic-local-community-v1',
             'local_tiles': True,
             'native_source_sha256': {'CONFIGURE.md': '0916a4596c83bad8c59c378ef5b2d89ce80f97e21180134b055e383199a7e961',
                                      'app/assets/javascripts/edit/id.js.erb': 'ed19d44426edeeca86d0bff85627ab4d7a2824d6b03acb535936c1854d9ced26',
                                      'app/assets/javascripts/id.js': 'fd948f3c81584574c86b77b15a15c7f96f885cbffbb57d16d7013ee1621940bc',
                                      'app/assets/javascripts/index.js': '10dd34fa707fa45b795c07c1070bd38c368e4c37e63825ca1b5ec93101e74424',
                                      'app/models/user.rb': '46115fb1daa1a7888f68c25b009ab194c9959540669e9c70885101f08b6be8c5',
                                      'app/views/site/id.html.erb': '743d27b59080ee222e9b28bcad2935cf8121149c98e95a73d2e8a82b65a7bd16'},
             'presets_directory': '/home/atuin/r102bf/r102bf10/lmtx/datasets/map-editor-assets/id-tagging-schema-6.0.0',
             'presets_manifest_sha256': '3b5539733d91376c7d3bcb343b5218e70450d84ad87e092895cae24497556f05',
             'version': 'native-map-editor-navigation-v1'},
  'gitlab_cache': None,
  'gitlab_initial': None,
  'layers': False,
  'optional': {}},
 {'capture_mail': False,
  'community': 'synthetic-local-community-gps-v1',
  'editor': None,
  'gitlab_cache': None,
  'gitlab_initial': None,
  'layers': False,
  'optional': {}}]


def standard_profile(value):
    return (isinstance(value, dict) and not value.get('optional', True)
            and value.get('community') is None and value.get('editor') is None)


def supported_profile(value):
    return standard_profile(value) or value in REVIEWED_COMMUNITY_PROFILES or raster_profile(value)


def raster_profile(value):
    if not isinstance(value, dict):
        return False
    common = dict(capture_mail=False, community=None, editor=None, layers=False,
                  gitlab_cache=None, gitlab_initial=None)
    options = [dict(map_raster_export=True),
               dict(map_raster_export=True, map_raster_query_policy='stable-scan'),
               dict(map_raster_export=True, map_pdf_export=True, map_raster_query_policy='stable-scan')]
    return value in [dict(common, optional=option) for option in options]


def community_manifest_family(contract):
    """Retain the native navigation family's dedicated-manifest boundary.

    Environment profiles alone do not distinguish account navigation from
    community reading. Native profile validation still runs before claims.
    """
    completion = contract.get('completion', {})
    enabled = [key for key in ('map_editor', 'map_native_navigation') if completion.get(key)]
    if len(enabled) > 1 or (enabled and contract.get('domain') != 'map'):
        raise ValueError('One native navigation family per Map task is required')
    return enabled[0] if enabled else None
