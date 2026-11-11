"""Narrow recovery gate for never-generated geo-URI reference layout repairs."""
import copy
import hashlib
import json
import re
from pathlib import Path
from .map_metadata_query import validate_query
from .map_share_layout import validated_layouts


def corrects_layout_only(revised, original):
    """No goal, start, field, object, or existing source hash may change."""
    try:
        if original.get('domain')!='map' or revised.get('domain')!='map': return False
        old=original['query']; new=revised['query']
        if old.get('family')!='map_metadata' or old.get('kind')!='geo_uri': return False
        extra={'share_geometry','reference_revision','share_layout_evidence'}
        if any(k in old for k in extra): return False
        proof=new['share_layout_evidence']; path=Path(proof['file'])
        if hashlib.sha256(path.read_bytes()).hexdigest()!=proof['sha256']: return False
        layouts=validated_layouts(json.loads(path.read_text()))
        if new['share_geometry']!=layouts[old['reference_path']]: return False
        def strip(q,previous):
            validate_query(q)
            if q['share_layout_evidence']!=proof or q['share_geometry']!=new['share_geometry']: raise ValueError('Changed layout')
            result=copy.deepcopy(q)
            for k in extra: result.pop(k)
            sources=result['source_evidence']; old_sources=previous['source_evidence']
            expected_new={'app/assets/javascripts/leaflet.sidebar.js','app/assets/stylesheets/common.scss'}
            additions=[s for s in sources if s not in old_sources]
            if ([s for s in sources if s in old_sources]!=old_sources or len(additions)!=2
                    or {s['path'] for s in additions}!=expected_new
                    or any(s.get('installed') is not False or not re.fullmatch('[0-9a-f]{64}',s['sha256']) for s in additions)):
                raise ValueError('Changed native source references')
            result['source_evidence']=copy.deepcopy(old_sources)
            return result
        canonical=strip(new,old)
        canonical['wrong_object_query']=strip(new['wrong_object_query'],old['wrong_object_query'])
        restored=copy.deepcopy(revised); restored['query']=canonical
        return restored==original
    except (KeyError,ValueError,TypeError,OSError): return False
