"""Passive complete local geocoder responses for freely selected locations.

No click/search is made. A field label and its exact submitted native point
identify which full OSM record should be independently looked up later. Neither
published later steps nor result rank supply an unstated fixed task target.
"""
from pathlib import Path
from urllib.parse import urlsplit
import hashlib,json
from .map_route_normal_capture import NativeRouteCapture,point,fingerprint
from .map_native_route_reference_inventory import require_native_origin
from lab_generate_skill.io_utils import atomic_write_json

class OpenChoiceRouteCapture(NativeRouteCapture):
    def __init__(self,context,origins,directory,search_origin):
        super().__init__(context,origins,directory)
        self.search_origin=require_native_origin(search_origin)
        self.geocodes=[];self.geocode_first_error=None;self.geocode_attached=True
        self.context.on('response',self._geocode)

    def _geocode(self,response):
        actual=urlsplit(response.url);origin=urlsplit(self.search_origin)
        if (actual.scheme,actual.netloc)!=(origin.scheme,origin.netloc)or actual.path not in('/search','/reverse'):
            return
        record=None
        try:
            if actual.username or actual.password or actual.fragment:
                raise ValueError('Malformed actual native geocoder request')
            raw=response.body();number=len(self.geocodes)
            name='native-geocode-response-'+str(number)+'.json.body'
            (self.directory/name).write_bytes(raw)
            record={'actual_url':response.url,'http_status':response.status,
                    'actual_public_language':response.request.headers.get('accept-language',''),
                    'raw_body_sha256':hashlib.sha256(raw).hexdigest(),'raw_body_bytes':len(raw),'artifact_file':name}
            self.geocodes.append(record)
            value=json.loads(raw)
            rows=value if isinstance(value,list)else[value]if isinstance(value,dict)else None
            if response.status!=200 or not isinstance(rows,list):
                raise ValueError('Native geocoder response is incomplete or not successful')
            for row in rows:
                if (not isinstance(row,dict)or type(row.get('osm_id'))is not int or row['osm_id']<=0
                        or row.get('osm_type')not in('node','way','relation')or not isinstance(row.get('display_name'),str)):
                    raise ValueError('Native geocoder full object identity is missing')
                point([row['lat'],row['lon']])
            record.update(full_native_records=rows,full_native_records_sha256=fingerprint(rows),complete_native_geocoder_response=True)
        except Exception as error:
            if self.geocode_first_error is None:self.geocode_first_error={'type':type(error).__name__,'message':str(error),'actual_url':response.url}
        finally:
            atomic_write_json(self.directory/'native-geocodes.json',{'complete_actual_response_history':self.geocodes,'first_error':self.geocode_first_error,'rank_not_used':True})

    def detach(self):
        first=None
        try:super().detach()
        except Exception as error:first=error
        if getattr(self,'geocode_attached',False):
            try:self.context.remove_listener('response',self._geocode)
            except Exception as error:
                if first is None:first=error
            else:self.geocode_attached=False
        if first is not None:raise first
