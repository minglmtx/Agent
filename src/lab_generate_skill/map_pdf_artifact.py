"""Candidate PDF export checks; no task admission without native controls.

The owned renderer receipt binds the public extent and route. An independently
rendered PDF supplies the content reference. Parsing a PDF or observing a
download alone is insufficient. Run under the caller's evaluation deadline.
"""
import hashlib

from PIL import Image

from .map_raster_request import MAX_PIXELS, normalize, export_byte_limit
from .map_raster_artifact import compare


def decode(body):
    import pymupdf
    if not isinstance(body, bytes) or not body.startswith(b'%PDF-') or len(body)>export_byte_limit('pdf'):
        raise ValueError('Bounded actual PDF required')
    try:
        with pymupdf.open(stream=body, filetype='pdf') as document:
            if (document.is_encrypted or document.page_count != 1 or
                    document.embfile_count() or document.is_repaired):
                raise ValueError('One intact unencrypted PDF page required')
            page=document[0];rect=page.rect
            if (rect.width<=0 or rect.height<=0 or rect.width>4096 or rect.height>4096
                    or rect.width*rect.height>MAX_PIXELS):
                raise ValueError('PDF page exceeds native render dimensions')
            image=page.get_pixmap(matrix=pymupdf.Matrix(1,1),colorspace=pymupdf.csRGB,alpha=False)
            if image.width*image.height>MAX_PIXELS:
                raise ValueError('Decoded PDF exceeds pixel budget')
            rgb=Image.frombytes('RGB',(image.width,image.height),image.samples)
            if all(lo==hi for lo,hi in rgb.getextrema()):raise ValueError('Blank map PDF')
            return rgb
    except (RuntimeError,pymupdf.FileDataError) as error:
        raise ValueError('Unreadable PDF') from error


def evaluate(body,receipt,expected_public_request,reference_body):
    checks=dict(actual_pdf=False,native_receipt_matches_file=False,
                exact_required_render_request=False,correct_dimensions=False,
                reference_content_matches=False)
    comparison=None
    def result(status,reason=None):
        return dict(version='native-pdf-artifact-candidate-v1',status=status,
                    reward=None if status=='unknown' else float(status=='success'),
                    checks=checks,image_comparison=comparison,reason=reason)
    try:
        expected=normalize(expected_public_request,allow_pdf=True)
        if expected['format']!='pdf':raise ValueError('PDF reference required')
        reference=decode(reference_body)
        if reference.size!=(expected['width'],expected['height']):
            raise ValueError('Reference page dimensions mismatch')
    except ImportError:
        return result('unknown','PDF reader dependency unavailable')
    except (ValueError,TypeError,KeyError,OSError):
        return result('unknown','Independent PDF reference or request unavailable or inconsistent')
    try:
        actual=decode(body);checks['actual_pdf']=True
        if not isinstance(receipt,dict):return result('unknown','Owned renderer receipt unavailable')
        checks['native_receipt_matches_file']=(receipt.get('sha256')==hashlib.sha256(body).hexdigest()
            and receipt.get('bytes')==len(body) and type(receipt.get('native_layers')) is int
            and receipt['native_layers']>0)
        checks['exact_required_render_request']=receipt.get('request')==expected
        checks['correct_dimensions']=actual.size==(expected['width'],expected['height'])
        comparison=compare(actual,reference);checks['reference_content_matches']=comparison['passed']
    except (ValueError,TypeError,KeyError,OSError):pass
    return result('success' if all(checks.values()) else 'failure')
