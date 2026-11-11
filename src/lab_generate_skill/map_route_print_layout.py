"""Opt-in local print-layout adaptation; no route synthesis or navigation.

Native OSM print.css hides the sidebar. This profile prints existing directions
as a paginated document. It changes print media only, for any displayed route.
It is an environment extension, not original snapshot equivalence or admission.
"""
import hashlib

VERSION = 'local-native-directions-print-v1'
CSS = '''@media print {
  html:has(#sidebar_content tr.turn),
  body:has(#sidebar_content tr.turn) {
    height: auto !important; overflow: visible !important;
  }
  body:has(#sidebar_content tr.turn) #content,
  body:has(#sidebar_content tr.turn) #sidebar,
  body:has(#sidebar_content tr.turn) #sidebar_content {
    display: block !important; position: static !important;
    float: none !important; width: auto !important;
    height: auto !important; max-height: none !important;
    overflow: visible !important; inset: auto !important;
  }
  body:has(#sidebar_content tr.turn) #map,
  body:has(#sidebar_content tr.turn) #sidebar .search_forms,
  body:has(#sidebar_content tr.turn) #sidebar .welcome,
  body:has(#sidebar_content tr.turn) #sidebar #banner {
    display: none !important;
  }
  body:has(#sidebar_content tr.turn) #attribution {
    position: static !important; height: auto !important;
  }
  body:has(#sidebar_content tr.turn) #sidebar_content table {
    width: 100% !important; table-layout: auto !important;
  }
  body:has(#sidebar_content tr.turn) #sidebar_content tr.turn {
    break-inside: avoid !important; page-break-inside: avoid !important;
  }
}'''
SHA256 = hashlib.sha256(CSS.encode()).hexdigest()


def install(page):
    """Trusted opt-in caller only; DOM text, route and screen observation untouched."""
    style = page.add_style_tag(content=CSS)
    return style, dict(version=VERSION, css_sha256=SHA256,
                       print_media_only=True, original_snapshot_equivalence=False,
                       generated_route_content=False)
