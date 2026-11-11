"""Public provider task shapes; no imports of rendering or resource machinery."""
PROVIDER_CODES={'hot':'H','satellite':'S','cyclosm':'Y','opnv':'O'}
TILE_PROVIDER_CODES={**PROVIDER_CODES,'gps':'G'}
COMPARISON_FAMILY='base_layer_comparison'


def validate_comparison(spec):
    if (spec.get('family')!=COMPARISON_FAMILY or spec.get('provider')not in PROVIDER_CODES
            or spec.get('required_codes')!=['M',PROVIDER_CODES[spec['provider']]]
            or type(spec.get('retain_initial_route'))is not bool
            or spec.get('completion_boundary') not in ('view_both_declared_layers_same_initial_area',
                'view_both_declared_layers_then_select_target_same_initial_area')):
        raise ValueError('Explicit observed-pair completion required; subjective ranking is not inferred')


def validate_resource_family(spec):
    if spec.get('family')=='gps_overlay_enabled':
        from .map_gps_document_resources import validate_spec
        validate_spec(spec)
    elif spec.get('family')==COMPARISON_FAMILY:validate_comparison(spec)
    elif spec.get('family')=='provider_before_export':
        if (spec.get('provider')!='hot' or spec.get('required_code')!='H'
                or spec.get('completion_boundary')!='humanitarian_before_complete_osm_download'
                or spec.get('retain_initial_area')is not False
                or spec.get('retain_initial_route')is not False):
            raise ValueError('Explicit layer-before-export resource contract required')
    elif spec.get('family')=='gps_overlay':
        if (spec.get('provider')!='gps' or spec.get('required_code')!='G'
                or spec.get('completion_boundary')!='loaded_native_gps_overlay_same_initial_area'):
            raise ValueError('Explicit native GPS overlay completion required')
    elif spec.get('family')!='base_layer':raise ValueError('Unsupported provider task family')
    elif spec.get('provider') not in PROVIDER_CODES:
        raise ValueError('An overlay cannot be used as a base layer')
