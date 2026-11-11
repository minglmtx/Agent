"""Read-only native gallery evidence; never navigate on behalf of the actor."""
from urllib.parse import unquote, urlsplit

from .site_database import select_rows


READ = r'''() => {
  const visible=e=>!!e&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden'&&getComputedStyle(e).display!=='none';
  const inView=e=>{if(!visible(e))return false;const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.bottom>0&&r.right>0&&r.top<innerHeight&&r.left<innerWidth;};
  const f=window.jQuery&&jQuery('.fotorama').data('fotorama');
  const stage=document.querySelector('.fotorama__stage'),rect=stage?.getBoundingClientRect();
  return {capture_version:'native-gallery-v2',url:location.href,product_id:document.querySelector('#product_addtocart_form input[name="product"]')?.value||null,
    product_name:document.querySelector('h1.page-title')?.innerText.trim()||'',
    gallery_present:!!f,gallery_expected:!!document.querySelector('.gallery-placeholder,.fotorama'),
    gallery_in_view:inView(stage),gallery_layout_ready:!!rect&&rect.width>0&&rect.height>0,
    gallery_rect:rect?{x:rect.x,y:rect.y,width:rect.width,height:rect.height}:null,active_index:f?f.activeIndex:null,
    frames:f?f.data.map(x=>({img:x.img,full:x.full})):[],
    images:[...document.querySelectorAll('.fotorama__stage__frame.fotorama__active img')].map(e=>({
      src:e.currentSrc||e.src,loaded:e.complete&&e.naturalWidth>0,visible:visible(e),in_view:inView(e)}))};
}'''


def media_file(url, origin):
    """Map native resized URLs to catalog files; reject foreign image hosts."""
    u, base = urlsplit(url), urlsplit(origin)
    if (u.scheme, u.netloc) != (base.scheme, base.netloc):
        return None
    prefix = '/media/catalog/product/'
    path = unquote(u.path)
    if not path.startswith(prefix):
        return None
    value = path[len(prefix):]
    if value.startswith('cache/'):
        parts = value.split('/', 2)
        if len(parts) != 3 or not parts[1]:
            return None
        value = parts[2]
    if not value or any(x in ('', '.', '..') for x in value.split('/')):
        return None
    return '/' + value


def media_reference(site, product_id):
    return select_rows(site, 'SELECT g.value_id,g.value,g.media_type FROM catalog_product_entity_media_gallery g '
        'JOIN catalog_product_entity_media_gallery_value_to_entity e ON e.value_id=g.value_id '
        'WHERE e.entity_id=' + str(int(product_id)) + ' ORDER BY g.value_id')


def validate(spec):
    if spec.get('kind') not in ('all_images', 'previous_image'):
        raise ValueError('Unsupported gallery task')
    files = spec.get('frame_files')
    if not isinstance(files, list) or len(files) < 2 or len(set(files)) != len(files):
        raise ValueError('Gallery requires at least two distinct ordered native images')
    refs = spec.get('media_reference', [])
    if {r['value'] for r in refs if r['media_type'] == 'image'} != set(files):
        raise ValueError('Native frame list does not match independent catalog media')
    i = spec.get('initial_index')
    if type(i) is not int or not 0 <= i < len(files):
        raise ValueError('Missing native initial gallery state')
    if spec['kind'] == 'previous_image' and i == 0:
        raise ValueError('Native initial frame has no previous image')


def verify_reference(site, spec):
    validate(spec)
    if media_reference(site, spec['product_id']) != spec['media_reference']:
        raise ValueError('Product gallery reference changed')


def displayed_file(state):
    """Index changes and thumbnails are insufficient: require the loaded main image."""
    if not state.get('gallery_present'):
        return None
    frames, i = state.get('frames', []), state.get('active_index')
    if type(i) is not int or not 0 <= i < len(frames):
        return None
    target = media_file(frames[i].get('img', ''), state['url'])
    if not target:
        return None
    images = [x for x in state.get('images', []) if x.get('visible') is True and x.get('in_view') is True]
    # During animation multiple stage frames can coexist; accept only a stable
    # loaded display matching the native active frame.
    if not images or any(x.get('loaded') is not True or media_file(x.get('src', ''), state['url']) != target for x in images):
        return None
    return target


def read_gallery(page):
    return page.evaluate(READ)


def read_settled_gallery(page, timeout_ms=2000):
    """Bounded wait only for an on-screen gallery whose transition is unsettled."""
    import time
    end = time.monotonic() + timeout_ms / 1000
    while True:
        state = read_gallery(page)
        if ((not state['gallery_present'] and not state.get('gallery_expected')) or displayed_file(state) is not None
                or (state['gallery_present'] and state.get('gallery_layout_ready') is True and state.get('gallery_in_view') is False)
                or time.monotonic() >= end):
            return state
        page.wait_for_timeout(min(100, max(1, int((end-time.monotonic())*1000))))


def gallery_checks(spec, state, samples):
    validate(spec)
    if not isinstance(state, dict) or not isinstance(samples, list):
        raise ValueError('Missing gallery capture or observation history')
    def identity(s):
        return s.get('product_id') == str(spec['product_id']) and s.get('product_name') == spec['product_name']
    def frames_match(s):
        return [media_file(f.get('img', ''), s['url']) for f in s.get('frames', [])] == spec['frame_files']
    current = displayed_file(state)
    native_samples = [s for s in samples if identity(s) and frames_match(s)]
    observed = [displayed_file(s) for s in native_samples]
    observed = [s for s in observed if s is not None]
    checks = {'gallery_product_identity': identity(state),
              'gallery_native_frames': frames_match(state),
              'gallery_main_image_displayed': current in spec['frame_files']}
    if spec['kind'] == 'all_images':
        checks['all_product_images_observed'] = set(spec['frame_files']) <= set(observed)
    else:
        previous = spec['frame_files'][spec['initial_index']-1]
        # "Previous" is relative to the native initial frame, not the first
        # image that happened to fit inside the viewport. The target image
        # itself must have been loaded and shown; an offscreen baseline is fine.
        checks['previous_product_image_observed'] = bool(native_samples
            and native_samples[0].get('active_index') == spec['initial_index']
            and previous in observed and current == previous)
    return checks


def prepare_control(page):
    """CPU positive setup: scroll to the gallery before inspecting its main image."""
    stage=page.locator('.fotorama__stage')
    stage.wait_for(state='visible',timeout=10000)
    stage.scroll_into_view_if_needed(timeout=10000)
    state=read_settled_gallery(page,timeout_ms=10000)
    if displayed_file(state)is None:raise ValueError('Native gallery did not display a loaded main image after scrolling')
    return state


def move_control(page, direction):
    """Exercise a native control in CPU validation only."""
    if direction not in ('prev', 'next'):
        raise ValueError('Invalid native gallery direction')
    button = page.locator('.fotorama__arr--' + direction)
    before = read_settled_gallery(page)
    if not button.is_visible() or 'fotorama__arr--disabled' in (button.get_attribute('class') or ''):
        raise ValueError('Native gallery control unavailable')
    button.click(timeout=10000)
    page.wait_for_function('i=>jQuery(".fotorama").data("fotorama").activeIndex!==i', arg=before['active_index'], timeout=10000)
    after = read_settled_gallery(page)
    if displayed_file(after) is None:
        raise ValueError('Gallery control changed index without displaying a loaded image')
    return after


FEEDBACK = {
    'gallery_product_identity': 'The displayed image gallery belongs to the requested product.',
    'gallery_native_frames': 'The gallery contains the native images of the requested product.',
    'gallery_main_image_displayed': 'A loaded main product image is displayed in the viewport.',
    'all_product_images_observed': 'All requested product images have been displayed as loaded main images.',
    'previous_product_image_observed': 'The previous image relative to the initial gallery state has been displayed.',
}
