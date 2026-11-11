"""General terminal content controls. Private references never enter prompts.

Missing or wrong native content is a false completion flag, not a browser
runtime exception. Markdown verifies complete real content, profile identity
uses its own header, and image completion requires decoded actual pixels.
"""
import hashlib
from urllib.parse import unquote, urlsplit
from .gitlab_profile_identity import profile_checks
from .gitlab_rendered_markdown_v3 import rendered_markdown_checks


def document_completion_checks(reference, source, state, native_html):
    expected='/' + reference['project'] + '/-/blob/' + reference['ref'] + '/' + reference['path']
    actual=unquote(urlsplit(state.get('url','')).path).rstrip('/')
    equivalent={expected}
    if reference.get('head'):
        equivalent.add('/'+reference['project']+'/-/blob/'+reference['head']+'/'+reference['path'])
    identity=str(reference['project_id']) in state.get('project_ids',[])
    checks={'requested_repository_identity':identity,'requested_document_identity':actual in equivalent,
            'native_content_not_loading':state.get('loading') is False and state.get('wait_status')=='ready'}
    text=rendered_markdown_checks(source,native_html,project=reference['project'],ref=reference['ref'],path=reference['path'],capture_truncated=False)
    # A pinned commit permalink may render relative native references with its
    # SHA instead of the unchanged branch name. The immutable reference proves
    # both names identify the same repository revision, not any arbitrary ref.
    if actual in equivalent and actual!=expected and reference.get('head') and not all(text.values()):
        pinned=rendered_markdown_checks(source,native_html,project=reference['project'],ref=reference['head'],path=reference['path'],capture_truncated=False)
        if all(pinned.values()):text=pinned
    return {**checks,**text}


def public_profile_completion_checks(reference, state):
    try:
        return profile_checks(reference,state)
    except ValueError:
        return {'current_profile_user_identity':False,'current_profile_username':False,'current_profile_name':False}


def image_completion_checks(reference, state, native_images, served_bytes):
    expected='/' + reference['project'] + '/-/raw/' + reference['ref'] + '/' + reference['path']
    equivalent={expected}
    if reference.get('head'):
        equivalent.add('/'+reference['project']+'/-/raw/'+reference['head']+'/'+reference['path'])
    matching=[row for row in native_images if unquote(urlsplit(row.get('src','')).path)in equivalent]
    dimensions=reference['image']
    loaded=any(row.get('complete') is True and row.get('width')==dimensions['width'] and row.get('height')==dimensions['height'] for row in matching)
    return {'requested_repository_identity':str(reference['project_id']) in state.get('project_ids',[]),
            'native_image_reference_present':bool(matching),'native_image_loaded_and_decoded':loaded,
            'actual_served_bytes_match_reference':isinstance(served_bytes,bytes) and hashlib.sha256(served_bytes).hexdigest()==reference['bytes_sha256']}
