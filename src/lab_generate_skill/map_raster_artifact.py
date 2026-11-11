"""Native PNG artifact checks, separate from task-specific area/route selection.

Receipts come from the owned renderer, never from actor-provided metadata. Exact
request identity enforces geographic bounds and route geometry. A separately
rendered reference checks image content, allowing only small channel noise, not
translation, resizing, perceptual similarity or missing features.
"""
import hashlib
import io

from PIL import Image, ImageChops, ImageStat

from .map_raster_request import MAX_PIXELS, normalize

MAX_CHANNEL_DELTA = 4
MAX_MEAN_CHANNEL_DELTA = .01


def decode(body):
    if not body or len(body) > 16 * 1024 * 1024:
        raise ValueError('Bounded nonempty PNG required')
    image = Image.open(io.BytesIO(body))
    if image.format != 'PNG' or image.width * image.height > MAX_PIXELS:
        raise ValueError('Bounded PNG required')
    image.load()
    if 'A' in image.getbands() and image.getchannel('A').getextrema() != (255, 255):
        raise ValueError('Opaque native map required')
    rgb = image.convert('RGB')
    if all(low == high for low, high in rgb.getextrema()):
        raise ValueError('Blank map export')
    return rgb


def compare(actual, reference):
    if actual.size != reference.size:
        return dict(passed=False, reason='dimensions_differ')
    delta = ImageChops.difference(actual, reference)
    maximum = max(high for _, high in delta.getextrema())
    means = ImageStat.Stat(delta).mean
    return dict(passed=maximum <= MAX_CHANNEL_DELTA and max(means) <= MAX_MEAN_CHANNEL_DELTA,
                exact_pixels=delta.getbbox() is None, max_channel_delta=maximum,
                mean_channel_delta=means, difference_box=delta.getbbox(),
                max_channel_limit=MAX_CHANNEL_DELTA, mean_channel_limit=MAX_MEAN_CHANNEL_DELTA)


def evaluate(body, receipt, expected_public_request, reference_body):
    """The caller independently establishes expected extent/current route.

Body and receipt alone are insufficient: the independent reference is required.
This does not treat a browser download event or PNG magic as task success.
"""
    checks = dict(actual_png=False, native_receipt_matches_file=False,
                  exact_required_render_request=False, correct_dimensions=False,
                  reference_content_matches=False)
    comparison = None
    # These inputs are evaluator-owned. Failure to obtain them is an
    # environment/capture problem, not evidence that the actor failed.
    try:
        expected = normalize(expected_public_request)
        reference = decode(reference_body)
        if reference.size != (expected['width'], expected['height']):
            raise ValueError('Reference dimensions do not match declared request')
    except (ValueError, TypeError, KeyError, OSError):
        return dict(version='native-png-artifact-v1', status='unknown', reward=None,
                    checks=checks, image_comparison=None,
                    reason='Independent render request or reference is unavailable or inconsistent.')
    try:
        actual = decode(body)
        checks['actual_png'] = True
        if not isinstance(receipt, dict):
            return dict(version='native-png-artifact-v1', status='unknown', reward=None,
                        checks=checks, image_comparison=None,
                        reason='Owned renderer receipt capture is unavailable.')
        checks['native_receipt_matches_file'] = (
            receipt.get('sha256') == hashlib.sha256(body).hexdigest()
            and receipt.get('bytes') == len(body)
            and type(receipt.get('native_layers')) is int
            and receipt['native_layers'] > 0)
        checks['exact_required_render_request'] = receipt.get('request') == expected
        checks['correct_dimensions'] = actual.size == (expected['width'], expected['height'])
        comparison = compare(actual, reference)
        checks['reference_content_matches'] = comparison['passed']
    except (ValueError, TypeError, KeyError, OSError):
        pass
    passed = all(checks.values())
    return dict(version='native-png-artifact-v1', status='success' if passed else 'failure',
                reward=float(passed), checks=checks, image_comparison=comparison)
